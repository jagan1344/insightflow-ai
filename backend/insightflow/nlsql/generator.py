"""Natural-language → SQL generation.

Rule-based path is the default (works fully offline). When an LLM is
available it is tried first, but the SQL is still passed through the
validator. If the LLM returns anything other than a single SELECT, we fall
back to the rule-based path.

Design (2026-09-23):
    Before emitting SQL we now extract a structured `QueryIntent` from the
    question — the metrics it needs, the dimensions (GROUP BYs) it names,
    filters like "loss-making" or "top N", and any explicit factors from
    an "(Analyze using: A, B, C)" clause. The intent then drives SQL
    generation and, in `reliability/confidence.py`, an `intent_coverage`
    signal that hard-caps confidence when the SQL doesn't actually cover
    what was asked. This stops bare aggregates like `SELECT SUM(revenue)`
    from scoring 0.97 on questions that clearly asked for a breakdown.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from ..knowledge.dataset_registry import ActiveDataset, get_active_dataset
from ..knowledge.kpi import KPI, KPIS, resolve_kpi
from ..knowledge.schema_agent import Schema, get_schema
from ..llm import LLMClient
from .adaptive import adaptive_generate


MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

DIMENSIONS = {
    "region":   ("region",   "regions",   "region_id",   "region_name"),
    "regions":  ("region",   "regions",   "region_id",   "region_name"),
    "category": ("category", "products",  "product_id",  "category"),
    "categories": ("category", "products", "product_id", "category"),
    "product":  ("product",  "products",  "product_id",  "product_name"),
    "products": ("product",  "products",  "product_id",  "product_name"),
    "segment":  ("segment",  "customers", "customer_id", "segment"),
    "segments": ("segment",  "customers", "customer_id", "segment"),
    "customer": ("customer", "customers", "customer_id", "customer_name"),
    "customers":("customer", "customers", "customer_id", "customer_name"),
}

DIAGNOSTIC_TERMS = ("why", "cause", "reason", "drop", "decrease", "decline",
                    "fell", "fall", "down", "dip", "lower")

DOMAIN_TERMS = {
    "revenue", "sales", "turnover",
    "order", "orders",
    "margin", "margins", "profitability", "profit",
    "region", "regions",
    "category", "categories",
    "subcategory", "subcategories", "sub_category",
    "product", "products",
    "customer", "customers",
    "unit", "units", "quantity", "volume",
    "count", "total", "average", "avg",
    "top", "bottom", "trend", "month", "monthly", "year",
    "segment", "segments",
    "discount", "discounts",
    "aov",
    # Analytical framing words that should count as domain terms:
    "draining", "losing", "unprofitable", "loss", "killing", "hurting",
    "cash", "money",
}

# Multi-word phrases → canonical metric key. Matched with str-in-str
# (longest-first) so "profit margins" beats "profit".
METRIC_PHRASES: list[tuple[str, str, dict | None]] = [
    # loss / cash-drain: signed profit AND a negative filter
    ("draining cash",     "profit", {"kind": "metric_lt_zero", "metric": "profit"}),
    ("losing money",      "profit", {"kind": "metric_lt_zero", "metric": "profit"}),
    ("not making money",  "profit", {"kind": "metric_lt_zero", "metric": "profit"}),
    ("loss-making",       "profit", {"kind": "metric_lt_zero", "metric": "profit"}),
    ("loss making",       "profit", {"kind": "metric_lt_zero", "metric": "profit"}),
    ("unprofitable",      "profit", {"kind": "metric_lt_zero", "metric": "profit"}),
    ("bleeding cash",     "profit", {"kind": "metric_lt_zero", "metric": "profit"}),
    ("in the red",        "profit", {"kind": "metric_lt_zero", "metric": "profit"}),
    # margin
    ("profit margins",    "gross_margin", None),
    ("profit margin",     "gross_margin", None),
    ("gross margin",      "gross_margin", None),
    ("margins",           "gross_margin", None),
    ("margin",            "gross_margin", None),
    ("profitability",     "gross_margin", None),
    # profit (bare)
    ("profit",            "profit", None),
    # discount
    ("discount rate",     "discount_rate", None),
    ("discounts",         "discount_rate", None),
    ("discount",          "discount_rate", None),
    # revenue
    ("total revenue",     "total_revenue", None),
    ("revenue",           "total_revenue", None),
    ("sales",             "total_revenue", None),
    ("turnover",          "total_revenue", None),
    # orders / units
    ("number of orders",  "order_count", None),
    ("order count",       "order_count", None),
    ("orders",            "order_count", None),
    ("units sold",        "units_sold", None),
    ("units",             "units_sold", None),
    # aov
    ("average order value", "avg_order_value", None),
    ("avg order value",   "avg_order_value", None),
    ("aov",               "avg_order_value", None),
]

# Dimension nouns → short dim name. Longest phrase first.
DIM_NOUNS: list[tuple[str, str]] = [
    ("product sub-categories", "sub_category"),
    ("product sub-category",   "sub_category"),
    ("product subcategories",  "sub_category"),
    ("sub-categories",         "sub_category"),
    ("sub categories",         "sub_category"),
    ("sub-category",           "sub_category"),
    ("sub category",           "sub_category"),
    ("subcategories",          "sub_category"),
    ("subcategory",            "sub_category"),
    ("in certain regions",     "region"),
    ("across regions",         "region"),
    ("across region",          "region"),
    ("by region",              "region"),
    ("regions",                "region"),
    ("region",                 "region"),
    ("categories",             "category"),
    ("category",               "category"),
    ("segments",               "segment"),
    ("segment",                "segment"),
    ("customers",              "customer"),
    ("customer",               "customer"),
    ("products",               "product"),
    ("by product",             "product"),
    ("product line",           "product"),
    ("monthly",                "month"),
    ("by month",               "month"),
    ("over months",            "month"),
    ("over time",              "month"),
    ("which month",            "month"),
    ("what month",             "month"),
    ("each month",             "month"),
    ("per month",              "month"),
    ("months",                 "month"),
    ("month",                  "month"),
    # dims some datasets have but the demo does not — surfaced as
    # unavailable in the schema check below so a "by state" question
    # CLARIFIES on demo rather than confidently returning a global total.
    ("by state",               "state"),
    ("states",                 "state"),
    ("by city",                "city"),
    ("cities",                 "city"),
    ("by country",             "country"),
    ("countries",              "country"),
]

CORRELATION_TRIGGERS = ("killing", "hurting", "driving", "relationship",
                        "correlat", "impact", "affect")

# Question shapes that are inherently too vague to answer confidently — they
# ask for judgement, recommendation, or narrative rather than a scalar/table.
# When one of these fires AND no concrete KPI+dimension was extracted, the
# generator emits no SQL and the orchestrator CLARIFYs.
VAGUE_TRIGGERS = (
    "how is my business",
    "how are we doing",
    "how's business",
    "how's it going",
    "tell me about the data",
    "tell me about the business",
    "what should i do",
    "what do you think",
    "give me insights",
    "give me a summary",
    "give me the numbers",
    "give me an overview",
    "what's happening",
    "anything interesting",
    "any thoughts",
    "the performance",
    "the situation",
    "the numbers",
    "the state of",
    "overall picture",
    "big picture",
)


@dataclass
class QueryIntent:
    """The structured intent extracted from the natural-language question.

    Everything here is derived from the text + the live DB schema; no LLM.
    Downstream:
        * `_sql_from_intent` uses this to generate schema-aware SQL.
        * `reliability.confidence.intent_coverage` computes what fraction
          of these required elements the actual SQL covers.
        * `orchestrator` surfaces `unavailable` in the CLARIFY explanation.
    """
    metrics: List[str] = field(default_factory=list)          # canonical KPI keys
    dimensions: List[str] = field(default_factory=list)       # short dim names
    filters: List[dict] = field(default_factory=list)         # e.g. {"kind":"metric_lt_zero","metric":"profit"}
    analysis_type: str = "aggregate"                          # aggregate|breakdown|ranking|correlation|diagnostic
    explicit_factors: List[str] = field(default_factory=list) # raw tokens from "(Analyze using: …)"
    required_columns: List[str] = field(default_factory=list) # union label used in coverage calc
    unavailable: List[str] = field(default_factory=list)      # asked-for but not in schema
    vague: bool = False                                       # matched a VAGUE_TRIGGER

    @property
    def is_bare_aggregate(self) -> bool:
        return not self.dimensions and not self.filters and not self.explicit_factors

    @property
    def is_empty(self) -> bool:
        """True if extraction found no metric, no dimension, no factor —
        i.e. we didn't recognise anything specific in the question."""
        return not (self.metrics or self.dimensions or self.explicit_factors
                    or self.filters)


@dataclass
class GenSQL:
    sql: str
    intent: str                    # legacy classification: aggregate / breakdown / trend / diagnostic
    kpi: Optional[KPI]
    dimension: Optional[str] = None
    month: Optional[int] = None
    diagnostic: bool = False
    notes: List[str] = field(default_factory=list)
    source: str = "rule"           # "rule" | "llm"
    out_of_scope: bool = False
    query_intent: Optional[QueryIntent] = None   # NEW — structured intent


# =============================================================================
# Detection helpers
# =============================================================================

def _detect_month(q: str) -> Optional[int]:
    ql = q.lower()
    # "in July compared to June" — the target month is the one after "in",
    # NOT the one after "compared to". Prefer that when the pattern is
    # unambiguous.
    m = re.search(r"\bin\s+([a-z]+)\b", ql)
    if m and m.group(1) in MONTHS:
        return MONTHS[m.group(1)]
    # Otherwise fall back to first-matched month name.
    hits: list[tuple[int, int]] = []
    for name, num in MONTHS.items():
        m2 = re.search(rf"\b{name}\b", ql)
        if m2:
            hits.append((m2.start(), num))
    if not hits:
        return None
    hits.sort()
    return hits[0][1]


def _detect_top_bottom(q: str) -> Optional[str]:
    ql = q.lower()
    if re.search(r"\b(top|best|highest)\b", ql):
        return "top"
    if re.search(r"\b(bottom|worst|lowest)\b", ql):
        return "bottom"
    return None


def _is_diagnostic(q: str) -> bool:
    ql = q.lower()
    return any(term in ql for term in DIAGNOSTIC_TERMS)


def _legacy_detect_dimension(q: str) -> Optional[str]:
    """Kept intact so the legacy tests / behaviours don't change."""
    ql = q.lower()
    if re.search(r"\bby\s+month\b", ql) or "trend" in ql or "monthly" in ql or "over time" in ql:
        return "month"
    m = re.search(r"\bby\s+([a-z_]+)\b", ql)
    if m and m.group(1) in DIMENSIONS:
        return DIMENSIONS[m.group(1)][0]
    m2 = re.search(r"\b(?:top|bottom|best|worst)\s+\d*\s*([a-z_]+)\b", ql)
    if m2 and m2.group(1) in DIMENSIONS:
        return DIMENSIONS[m2.group(1)][0]
    return None


def _is_in_domain(q: str, kpi: Optional[KPI], dim: Optional[str],
                  month: Optional[int]) -> bool:
    if kpi or dim or month is not None:
        return True
    ql = q.lower()
    tokens = re.findall(r"[a-zA-Z]+", ql)
    return any(t.lower() in DOMAIN_TERMS for t in tokens)


def _month_filter_sql(month: int) -> str:
    yy = 2026  # demo year
    mm = f"{month:02d}"
    return f"order_date >= '{yy}-{mm}-01' AND order_date < date('{yy}-{mm}-01','+1 month')"


# =============================================================================
# Schema-awareness helpers  (are the required columns actually available?)
# =============================================================================

def _dim_available(dim: str, schema: Schema) -> bool:
    tables = schema.tables
    if dim == "region":
        return "regions" in tables
    if dim == "category":
        return "products" in tables and "category" in tables.get("products", [])
    if dim == "sub_category":
        return "products" in tables and "sub_category" in tables.get("products", [])
    if dim == "product":
        return "products" in tables and "product_name" in tables.get("products", [])
    if dim in ("segment",):
        return "customers" in tables and "segment" in tables.get("customers", [])
    if dim == "customer":
        return "customers" in tables and "customer_name" in tables.get("customers", [])
    if dim == "month":
        return "orders" in tables and "order_date" in tables.get("orders", [])
    # Any other dim (state / city / country / arbitrary "by X" tokens) is
    # only available if a column of that exact name exists somewhere in
    # the schema. Otherwise it must be flagged unavailable.
    for cols in tables.values():
        if dim in cols:
            return True
    return False


def _metric_available(metric: str, schema: Schema) -> bool:
    cols = schema.tables.get("orders", [])
    if metric in ("total_revenue", "avg_order_value"):
        return "revenue" in cols
    if metric == "order_count":
        return "orders" in schema.tables
    if metric == "units_sold":
        return "quantity" in cols
    if metric in ("gross_margin", "profit"):
        return "revenue" in cols and "cost" in cols
    if metric == "discount_rate":
        return "discount" in cols and "revenue" in cols
    return False


def _dim_target(dim: str) -> tuple[str, str, str]:
    """Return (alias, group_col_expr, join_sql). Empty group_col means unhandled."""
    if dim == "region":
        return ("region", "regions.region_name",
                "JOIN regions ON regions.region_id = orders.region_id")
    if dim == "category":
        return ("category", "products.category",
                "JOIN products ON products.product_id = orders.product_id")
    if dim == "sub_category":
        return ("sub_category", "products.sub_category",
                "JOIN products ON products.product_id = orders.product_id")
    if dim == "product":
        return ("product", "products.product_name",
                "JOIN products ON products.product_id = orders.product_id")
    if dim == "segment":
        return ("segment", "customers.segment",
                "JOIN customers ON customers.customer_id = orders.customer_id")
    if dim == "customer":
        return ("customer", "customers.customer_name",
                "JOIN customers ON customers.customer_id = orders.customer_id")
    if dim == "month":
        return ("month", "substr(order_date,1,7)", "")
    return (dim, "", "")


# =============================================================================
# Intent extraction
# =============================================================================

def _parse_explicit_factors(q: str) -> list[str]:
    """Parse "(Analyze using: X, Y, Z)" or "using X, Y, Z" trailers."""
    factors: list[str] = []
    m = re.search(r"\(\s*analyze\s+using\s*[:\-]?\s*([^)]+)\)", q, flags=re.I)
    if m:
        for tok in re.split(r"[,;]|\band\b", m.group(1), flags=re.I):
            tok = tok.strip(" .")
            if tok:
                factors.append(tok.lower())
        return factors
    m = re.search(r"\busing\s+([A-Z][A-Za-z_ ,\-]+?)(?:\.|$|\?)", q)
    if m:
        for tok in re.split(r"[,;]|\band\b", m.group(1), flags=re.I):
            tok = tok.strip(" .")
            if tok and 1 < len(tok) < 40:
                factors.append(tok.lower())
    return factors


def _canon_from_factor(tok: str) -> tuple[str, str]:
    """Return ("metric"|"dim"|"", canonical_key) for a raw factor token."""
    t = tok.strip().lower()
    # metric first — longest match
    for phrase, metric, _ in METRIC_PHRASES:
        if phrase in t:
            return ("metric", metric)
    for phrase, dim in DIM_NOUNS:
        if phrase in t:
            return ("dim", dim)
    return ("", "")


def _extract_intent(question: str, schema: Schema) -> QueryIntent:
    ql = " " + question.lower() + " "
    intent = QueryIntent()

    # 1. Metrics + implicit filters from framing phrases (longest-first).
    used_spans: list[tuple[int, int]] = []
    for phrase, metric, extra_filter in METRIC_PHRASES:
        needle = f" {phrase} " if len(phrase) > 2 else f" {phrase}"
        idx = ql.find(needle)
        if idx < 0:
            # try boundary-less for single-word phrases with punctuation
            idx = ql.find(phrase)
            if idx < 0:
                continue
        # skip if this substring was already claimed by a longer phrase
        end = idx + len(phrase)
        if any(s <= idx < e or s < end <= e for s, e in used_spans):
            continue
        used_spans.append((idx, end))
        if metric not in intent.metrics:
            intent.metrics.append(metric)
        if extra_filter and extra_filter not in intent.filters:
            intent.filters.append(dict(extra_filter))

    # 2. Dimensions from nouns (longest-first, skip already-claimed spans).
    dim_spans: list[tuple[int, int]] = []
    for phrase, dim in DIM_NOUNS:
        idx = ql.find(f" {phrase}")
        if idx < 0:
            continue
        end = idx + 1 + len(phrase)
        if any(s <= idx < e or s < end <= e for s, e in dim_spans):
            continue
        dim_spans.append((idx, end))
        if dim not in intent.dimensions:
            intent.dimensions.append(dim)

    # 2b. Catch-all "by <noun>" — protects against every dimension we
    # forgot to enumerate. If none of the known dim_spans covers the
    # match, treat the noun as a requested dimension. It'll be flagged
    # unavailable when the schema check runs.
    for m in re.finditer(r"\bby\s+([a-z_][a-z_]{2,20})\b", ql):
        idx, end = m.start(), m.end()
        if any(s <= idx < e or s < end <= e for s, e in dim_spans):
            continue
        noun = m.group(1)
        # skip common English stopwords that follow "by" but aren't a
        # dimension noun ("by looking", "by doing", "by using")
        if noun in {"looking", "doing", "using", "the", "a", "an", "my",
                    "our", "that", "which", "what", "some", "many"}:
            continue
        if noun not in intent.dimensions:
            intent.dimensions.append(noun)
        dim_spans.append((idx, end))

    # 3. Explicit factors (from "(Analyze using: …)" or "using X, Y")
    intent.explicit_factors = _parse_explicit_factors(question)
    for tok in intent.explicit_factors:
        kind, canon = _canon_from_factor(tok)
        if kind == "metric" and canon not in intent.metrics:
            intent.metrics.append(canon)
        elif kind == "dim" and canon not in intent.dimensions:
            intent.dimensions.append(canon)

    # 4. Ranking / top-bottom
    m = re.search(r"\b(top|bottom|worst|best|highest|lowest)\s+(\d+)?\b", ql)
    if m:
        n = int(m.group(2) or 5)
        direction = "asc" if m.group(1) in ("bottom", "worst", "lowest") else "desc"
        intent.filters.append({"kind": "limit", "n": n, "order": direction})

    # 5. Analysis type
    if any(f["kind"] == "metric_lt_zero" for f in intent.filters):
        intent.analysis_type = "ranking"
    elif re.search(r"\b(why|reason|cause|because|led to|drove)\b", ql):
        intent.analysis_type = "diagnostic"
    elif any(t in ql for t in CORRELATION_TRIGGERS):
        intent.analysis_type = "correlation"
        # Correlation needs BOTH metrics named; ensure discount is included
        # when the question is about discount×margin
        if "discount" in ql and "discount_rate" not in intent.metrics:
            intent.metrics.append("discount_rate")
    elif intent.dimensions:
        intent.analysis_type = "breakdown"
    elif re.search(r"\b(which|what|list|show|rank)\b", ql) and intent.metrics:
        intent.analysis_type = "breakdown"
    else:
        intent.analysis_type = "aggregate"

    # 6. required_columns (used only as a label bag; the coverage function
    #    computes present-vs-required from the fields above).
    intent.required_columns = list(intent.metrics) + list(intent.dimensions)

    # 7. What was asked for but isn't in the current schema?
    for m in intent.metrics:
        if not _metric_available(m, schema):
            intent.unavailable.append(f"metric:{m}")
    for d in intent.dimensions:
        if not _dim_available(d, schema):
            intent.unavailable.append(f"dim:{d}")

    # 8. Vague-form detection — questions asking for judgement / narrative
    #    rather than a specific value. Matched only after the concrete
    #    metric/dim extraction so "what is the total revenue" (specific)
    #    is never flagged even if it contained the word "the numbers".
    if intent.is_empty:
        stripped = ql.strip()
        for trigger in VAGUE_TRIGGERS:
            if trigger in ql:
                intent.vague = True
                break
        # Also flag if the question is very short and lacks any KPI/dim word
        # ("summary?", "insights?", "?", etc.)
        alpha = re.sub(r"[^a-z ]", " ", stripped)
        tokens = [t for t in alpha.split() if len(t) > 1]
        if not intent.vague and len(tokens) <= 3 and \
                not any(t in DOMAIN_TERMS for t in tokens):
            intent.vague = True
    return intent


# =============================================================================
# SQL generation from intent
# =============================================================================

def _sql_from_intent(intent: QueryIntent) -> Optional[str]:
    """Build SQL that actually satisfies the intent. Returns None if
    the intent is bare-aggregate (let the legacy path handle it) or if
    required columns are unavailable (caller CLARIFIES)."""
    if intent.unavailable:
        return None
    if intent.is_bare_aggregate:
        return None

    # SELECT clauses
    select_parts: list[str] = []
    group_by_parts: list[str] = []
    joins: list[str] = []
    seen_joins: set[str] = set()

    for d in intent.dimensions:
        alias, col, join = _dim_target(d)
        if not col:
            continue
        select_parts.append(f"{col} AS {alias}")
        group_by_parts.append(col)
        if join and join not in seen_joins:
            joins.append(join)
            seen_joins.add(join)

    # Ensure profit is present (for HAVING and ordering) if there is a
    # loss filter on it, even when it wasn't explicitly named as a metric
    for f in intent.filters:
        if f["kind"] == "metric_lt_zero" and f["metric"] == "profit" \
                and "profit" not in intent.metrics:
            intent.metrics.insert(0, "profit")

    # Decide which metric will be the SELECT-list tail — the downstream
    # analyzer picks the LAST result column as the headline, so we want the
    # metric that drives ORDER BY (or the loss filter) to sit last.
    primary_metric = None
    for f in intent.filters:
        if f["kind"] == "metric_lt_zero":
            primary_metric = f["metric"]
            break
    if primary_metric is None:
        if intent.analysis_type == "correlation" and "gross_margin" in intent.metrics:
            primary_metric = "gross_margin"
        elif intent.metrics:
            primary_metric = intent.metrics[0]
    ordered_metrics = [m for m in intent.metrics if m != primary_metric] + \
                      ([primary_metric] if primary_metric else [])

    for m in ordered_metrics:
        kpi = KPIS.get(m)
        if kpi is None:
            continue
        # For discount inside a *correlation-style* query on a breakdown, prefer
        # AVG(discount) rather than the fraction-of-gross ratio — it's what a
        # BI analyst actually wants to inspect per-region.
        if m == "discount_rate" and intent.dimensions and \
                intent.analysis_type in ("correlation", "breakdown"):
            select_parts.append("AVG(discount) AS avg_discount")
        else:
            select_parts.append(f"{kpi.sql_expr} AS {m}")

    if not select_parts:
        return None

    # HAVING and ORDER BY
    having_clause = ""
    order_by = ""
    order_dir = "DESC"
    limit_clause = ""

    for f in intent.filters:
        if f["kind"] == "metric_lt_zero":
            kpi = KPIS.get(f["metric"])
            if kpi is not None:
                having_clause = f" HAVING {kpi.sql_expr} < 0"
                order_by = f["metric"]
                order_dir = "ASC"
        elif f["kind"] == "limit":
            limit_clause = f" LIMIT {f['n']}"
            order_dir = "ASC" if f["order"] == "asc" else "DESC"
            if not order_by and intent.metrics:
                order_by = intent.metrics[0]

    if not order_by and intent.metrics:
        order_by = intent.metrics[0]

    sql = "SELECT " + ", ".join(select_parts) + " FROM orders"
    if joins:
        sql += " " + " ".join(joins)
    if group_by_parts:
        sql += " GROUP BY " + ", ".join(group_by_parts)
    sql += having_clause
    # Time-series trend queries want chronological order, not metric order.
    if "month" in intent.dimensions and intent.analysis_type in ("breakdown", "aggregate") \
            and not any(f["kind"] == "limit" for f in intent.filters):
        sql += " ORDER BY month"
    elif order_by:
        # Correlation ordering: rank by the *problem* metric (margin ASC when
        # asking about killed margins).
        if intent.analysis_type == "correlation" and "gross_margin" in intent.metrics:
            order_by = "gross_margin"
            order_dir = "ASC"
        sql += f" ORDER BY {order_by} {order_dir}"
    sql += limit_clause
    return sql


# =============================================================================
# The rule-based generator (extended with intent, otherwise legacy)
# =============================================================================

def _rule_generate(question: str) -> GenSQL:
    schema = get_schema()
    active_ds = get_active_dataset()

    kpi = resolve_kpi(question)
    dim = _legacy_detect_dimension(question)
    month = _detect_month(question)
    diagnostic = _is_diagnostic(question)
    top_bottom = _detect_top_bottom(question)

    intent = _extract_intent(question, schema)

    # -----------------------------------------------------------------
    # If the active dataset is an uploaded one, emit SQL against its
    # actual columns rather than the demo star schema. This is the
    # bug-fix for "NL→SQL keeps returning demo results even after upload".
    # -----------------------------------------------------------------
    if active_ds.kind == "uploaded":
        result = adaptive_generate(intent, question, ds=active_ds)
        if result is not None:
            # The adaptive path's schema check is authoritative for
            # uploaded datasets; overwrite the demo-based unavailable
            # list.
            intent.unavailable = list(result.get("unavailable") or [])
            if not result["sql"] or result["unavailable"]:
                # Nothing mappable → CLARIFY via the out_of_scope flag.
                return GenSQL(
                    sql="", intent="unknown", kpi=None, dimension=None,
                    month=month, diagnostic=False,
                    notes=[f"active dataset {active_ds.name!r} is missing: "
                           f"{result.get('unavailable')}"],
                    source="rule", out_of_scope=True, query_intent=intent,
                )
            # Build a KPI object dynamically for downstream analyzer/
            # validator so it doesn't try to enforce demo-schema rules.
            primary_key = result.get("metric") or "total_revenue"
            headline_kpi = KPI(
                key=primary_key,
                name=primary_key.replace("_", " ").title(),
                sql_expr="ADAPTIVE",
                description=f"Computed from active dataset '{active_ds.name}'.",
                unit=("ratio" if "margin" in primary_key or
                      "rate" in primary_key else "currency"),
                non_negative=(primary_key not in ("profit",)),
                ratio_0_1=("margin" in primary_key),
            )
            return GenSQL(
                sql=result["sql"],
                intent=result["intent_type"],
                kpi=headline_kpi,
                dimension=result.get("dim"),
                month=month,
                diagnostic=(result["intent_type"] == "diagnostic") or diagnostic,
                source="rule",
                query_intent=intent,
                notes=[f"active_dataset={active_ds.id} table={active_ds.table}"],
            )

    in_domain = _is_in_domain(question, kpi, dim, month) or bool(
        intent.metrics or intent.dimensions or intent.explicit_factors
    )
    if not in_domain:
        return GenSQL(
            sql="", intent="unknown", kpi=None, dimension=None, month=None,
            diagnostic=False, notes=["question is out of scope"],
            source="rule", out_of_scope=True, query_intent=intent,
        )

    # Vague / judgement questions with no concrete metric or dimension get
    # routed to CLARIFY. This stops "give me insights" from confidently
    # defaulting to SUM(revenue).
    if intent.vague and intent.is_empty and kpi is None and dim is None:
        return GenSQL(
            sql="", intent="unknown", kpi=None, dimension=None, month=None,
            diagnostic=False,
            notes=["vague question: no specific KPI or dimension named"],
            source="rule", out_of_scope=True, query_intent=intent,
        )

    # Prefer intent-driven SQL whenever the intent asks for a breakdown /
    # ranking / correlation / loss filter — that is what the failing
    # questions look like. Fall back to the legacy generator for the
    # simple aggregate case (keeps existing tests green).
    intent_sql = _sql_from_intent(intent)
    if intent_sql:
        # Pick the headline KPI to match the LAST metric that the SELECT
        # list ends with — that's the column downstream analyzer / KPI
        # validator will read as the value.
        primary_metric_name = None
        for f in intent.filters:
            if f["kind"] == "metric_lt_zero":
                primary_metric_name = f["metric"]
                break
        if primary_metric_name is None:
            if intent.analysis_type == "correlation" and "gross_margin" in intent.metrics:
                primary_metric_name = "gross_margin"
            elif intent.metrics:
                primary_metric_name = intent.metrics[0]
        headline_kpi = KPIS.get(primary_metric_name) if primary_metric_name else None
        if headline_kpi is None:
            headline_kpi = KPIS["total_revenue"]
        legacy_intent = intent.analysis_type
        if legacy_intent == "aggregate":
            legacy_intent = "breakdown" if intent.dimensions else "aggregate"
        primary_dim = intent.dimensions[0] if intent.dimensions else None
        return GenSQL(
            sql=intent_sql,
            intent=legacy_intent,
            kpi=headline_kpi,
            dimension=primary_dim,
            month=month,
            diagnostic=(intent.analysis_type == "diagnostic") or diagnostic,
            source="rule",
            query_intent=intent,
        )

    # Legacy path — everything below is unchanged behaviour.
    if kpi is None:
        kpi = KPIS["total_revenue"]

    kpi_expr = kpi.sql_expr
    key = kpi.key

    if dim == "month":
        where = f"WHERE {_month_filter_sql(month)} " if month else ""
        sql = (
            f"SELECT substr(order_date,1,7) AS month, {kpi_expr} AS {key} "
            f"FROM orders {where}GROUP BY substr(order_date,1,7) ORDER BY month"
        )
        return GenSQL(sql=sql, intent="trend", kpi=kpi, dimension="month",
                      month=month, diagnostic=False, source="rule",
                      query_intent=intent)

    if dim:
        if dim == "region":
            joins = "JOIN regions ON regions.region_id = orders.region_id"
            group_col = "regions.region_name"
            label_alias = "region"
        elif dim == "category":
            joins = "JOIN products ON products.product_id = orders.product_id"
            group_col = "products.category"
            label_alias = "category"
        elif dim == "product":
            joins = "JOIN products ON products.product_id = orders.product_id"
            group_col = "products.product_name"
            label_alias = "product"
        elif dim == "segment":
            joins = "JOIN customers ON customers.customer_id = orders.customer_id"
            group_col = "customers.segment"
            label_alias = "segment"
        else:
            joins = "JOIN customers ON customers.customer_id = orders.customer_id"
            group_col = "customers.customer_name"
            label_alias = "customer"

        where = f"WHERE {_month_filter_sql(month)} " if month else ""
        order_dir = "ASC" if top_bottom == "bottom" else "DESC"
        limit = " LIMIT 5" if top_bottom else ""
        sql = (
            f"SELECT {group_col} AS {label_alias}, {kpi_expr} AS {key} "
            f"FROM orders {joins} {where}GROUP BY {group_col} "
            f"ORDER BY {key} {order_dir}{limit}"
        )
        legacy_int = "diagnostic" if diagnostic else "breakdown"
        return GenSQL(sql=sql, intent=legacy_int, kpi=kpi, dimension=dim,
                      month=month, diagnostic=diagnostic, source="rule",
                      query_intent=intent)

    where = f"WHERE {_month_filter_sql(month)} " if month else ""
    sql = f"SELECT {kpi_expr} AS {key} FROM orders {where}".strip()
    legacy_int = "diagnostic" if diagnostic else "aggregate"
    return GenSQL(sql=sql, intent=legacy_int, kpi=kpi, dimension=None,
                  month=month, diagnostic=diagnostic, source="rule",
                  query_intent=intent)


# =============================================================================
# LLM path (unchanged, keeps query_intent for coverage scoring)
# =============================================================================

_LLM_SYSTEM = (
    "You translate business questions into a single read-only SQLite SELECT "
    "statement for the given schema. Return SQL only, no prose, no fences."
)


def _llm_generate(question: str, llm: LLMClient) -> Optional[GenSQL]:
    schema = get_schema()
    prompt = (
        f"Schema:\n{schema.as_ddl_text()}\n\n"
        f"Business question: {question}\n\n"
        "Write ONE SQLite SELECT statement that answers it. "
        "No INSERT/UPDATE/DELETE/DDL. No comments. No markdown."
    )
    text = llm.complete(prompt, system=_LLM_SYSTEM, temperature=0.0)
    if not text:
        return None
    text = re.sub(r"^```(?:sql)?\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"\s*```$", "", text.strip())
    text = text.strip().rstrip(";").strip()
    if not text.lower().lstrip().startswith("select"):
        return None
    kpi = resolve_kpi(question)
    return GenSQL(sql=text, intent="llm", kpi=kpi, dimension=None,
                  month=_detect_month(question),
                  diagnostic=_is_diagnostic(question),
                  source="llm",
                  query_intent=_extract_intent(question, schema))


def generate_sql(question: str, llm: Optional[LLMClient] = None) -> GenSQL:
    if llm is not None and llm.available:
        g = _llm_generate(question, llm)
        if g is not None:
            return g
    return _rule_generate(question)


# =============================================================================
# Public coverage function — used by reliability.confidence
# =============================================================================

_KPI_EXPR_TOKENS = {
    "total_revenue":   "sum(revenue",
    "profit":          "sum(revenue-cost",
    "gross_margin":    "sum(revenue-cost)*1.0/sum(revenue",
    "discount_rate":   "sum(discount",
    "avg_order_value": "sum(revenue)*1.0/count",
    "order_count":     "count(*",
    "units_sold":      "sum(quantity",
}

_DIM_COL_TOKENS = {
    "region":       ("region_name", "regions.region_name"),
    "category":     ("products.category", "category"),
    "sub_category": ("products.sub_category", "sub_category"),
    "product":      ("products.product_name", "product_name"),
    "segment":      ("customers.segment", "segment"),
    "customer":     ("customers.customer_name", "customer_name"),
    "month":        ("substr(order_date,1,7)",),
}


def compute_intent_coverage(intent: Optional[QueryIntent], sql: str) -> float:
    """Fraction of the intent's required elements that the SQL actually
    covers. Bare-aggregate intents (no dims / filters / factors) score 1.0
    so simple `what is total revenue?` questions still answer confidently.

    NEVER lies for the caller: this function ONLY reads the SQL and the
    intent, both of which are already produced by the pipeline."""
    if intent is None or not sql:
        return 1.0 if intent is None else 0.0

    s = re.sub(r"\s+", " ", sql.strip().lower())

    required: list[str] = []
    present: list[str] = []

    for d in intent.dimensions:
        required.append(f"dim:{d}")
        cols = _DIM_COL_TOKENS.get(d, (d,))
        # A dimension is "covered" iff SQL has a GROUP BY that mentions
        # one of the column names for that dim (or the dim in the SELECT
        # for the month case).
        has_group_by = "group by" in s
        hits = has_group_by and any(c.lower() in s for c in cols)
        if hits:
            present.append(f"dim:{d}")

    for m in intent.metrics:
        required.append(f"metric:{m}")
        # match either the KPI expression signature or the canonical
        # column that appears in the SELECT list (e.g. `AS discount_rate`)
        signature = _KPI_EXPR_TOKENS.get(m, m)
        if signature in s.replace(" ", "") or f"as {m}" in s or f"as avg_discount" in s and m == "discount_rate":
            present.append(f"metric:{m}")

    for f in intent.filters:
        if f["kind"] == "metric_lt_zero":
            required.append("filter:loss")
            has_pred = "having" in s or "where" in s
            if has_pred and re.search(r"<\s*0", s):
                present.append("filter:loss")
        elif f["kind"] == "limit":
            required.append("filter:limit")
            if "limit" in s:
                present.append("filter:limit")

    # Explicit factors — count each factor whose canonical form is present.
    for tok in intent.explicit_factors:
        kind, canon = _canon_from_factor(tok)
        if not kind:
            continue
        required.append(f"factor:{canon}")
        if kind == "metric":
            signature = _KPI_EXPR_TOKENS.get(canon, canon)
            if signature in s.replace(" ", "") or f"as {canon}" in s \
                    or (canon == "discount_rate" and "avg_discount" in s):
                present.append(f"factor:{canon}")
        elif kind == "dim":
            cols = _DIM_COL_TOKENS.get(canon, (canon,))
            if "group by" in s and any(c.lower() in s for c in cols):
                present.append(f"factor:{canon}")

    if not required:
        return 1.0
    return len(present) / len(required)
