"""Natural-language → SQL generation.

Rule-based path is the default (works fully offline). When an LLM is
available it is tried first, but the SQL is still passed through the
validator. If the LLM returns anything other than a single SELECT, we fall
back to the rule-based path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from ..knowledge.kpi import KPI, KPIS, resolve_kpi
from ..knowledge.schema_agent import get_schema
from ..llm import LLMClient


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
    "margin", "profitability", "profit",
    "region", "regions",
    "category", "categories",
    "product", "products",
    "customer", "customers",
    "unit", "units", "quantity", "volume",
    "data", "count", "total", "average", "avg",
    "top", "bottom", "trend", "month", "monthly", "year",
    "segment", "segments",
    "discount", "discounts",
    "aov",
}


@dataclass
class GenSQL:
    sql: str
    intent: str                    # e.g. "aggregate", "breakdown", "trend", "diagnostic"
    kpi: Optional[KPI]
    dimension: Optional[str] = None       # short name: region / category / product / segment / month
    month: Optional[int] = None
    diagnostic: bool = False
    notes: List[str] = field(default_factory=list)
    source: str = "rule"           # "rule" | "llm"
    out_of_scope: bool = False


# ---------------------------------------------------------------------------

def _detect_month(q: str) -> Optional[int]:
    ql = q.lower()
    for name, num in MONTHS.items():
        # word-boundary match
        if re.search(rf"\b{name}\b", ql):
            return num
    return None


def _detect_dimension(q: str) -> Optional[str]:
    ql = q.lower()
    if re.search(r"\bby\s+month\b", ql) or "trend" in ql or "monthly" in ql or "over time" in ql:
        return "month"
    m = re.search(r"\bby\s+([a-z]+)\b", ql)
    if m and m.group(1) in DIMENSIONS:
        return DIMENSIONS[m.group(1)][0]
    # patterns like "top products by revenue" — dimension precedes "by"
    m2 = re.search(r"\b(?:top|bottom|best|worst)\s+\d*\s*([a-z]+)\b", ql)
    if m2 and m2.group(1) in DIMENSIONS:
        return DIMENSIONS[m2.group(1)][0]
    return None


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


def _is_in_domain(q: str, kpi: Optional[KPI], dim: Optional[str], month: Optional[int]) -> bool:
    if kpi or dim or month is not None:
        return True
    ql = q.lower()
    tokens = re.findall(r"[a-zA-Z]+", ql)
    return any(t.lower() in DOMAIN_TERMS for t in tokens)


def _month_filter_sql(month: int) -> str:
    yy = 2026  # demo year
    mm = f"{month:02d}"
    return f"order_date >= '{yy}-{mm}-01' AND order_date < date('{yy}-{mm}-01','+1 month')"


def _rule_generate(question: str) -> GenSQL:
    kpi = resolve_kpi(question)
    dim = _detect_dimension(question)
    month = _detect_month(question)
    diagnostic = _is_diagnostic(question)
    top_bottom = _detect_top_bottom(question)

    in_domain = _is_in_domain(question, kpi, dim, month)
    if not in_domain:
        return GenSQL(
            sql="", intent="unknown", kpi=None, dimension=None, month=None,
            diagnostic=False, notes=["question is out of scope"],
            source="rule", out_of_scope=True,
        )

    # Default to revenue for in-domain questions with no KPI.
    if kpi is None:
        kpi = KPIS["total_revenue"]

    kpi_expr = kpi.sql_expr
    key = kpi.key

    # ---------- trend ----------
    if dim == "month":
        where = f"WHERE {_month_filter_sql(month)} " if month else ""
        sql = (
            f"SELECT substr(order_date,1,7) AS month, {kpi_expr} AS {key} "
            f"FROM orders {where}GROUP BY substr(order_date,1,7) ORDER BY month"
        )
        return GenSQL(sql=sql, intent="trend", kpi=kpi, dimension="month",
                      month=month, diagnostic=False, source="rule")

    # ---------- breakdown ----------
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
        else:  # customer
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
        intent = "breakdown"
        if diagnostic:
            intent = "diagnostic"
        return GenSQL(sql=sql, intent=intent, kpi=kpi, dimension=dim,
                      month=month, diagnostic=diagnostic, source="rule")

    # ---------- aggregate / diagnostic aggregate ----------
    where = f"WHERE {_month_filter_sql(month)} " if month else ""
    sql = f"SELECT {kpi_expr} AS {key} FROM orders {where}".strip()
    intent = "diagnostic" if diagnostic else "aggregate"
    return GenSQL(sql=sql, intent=intent, kpi=kpi, dimension=None,
                  month=month, diagnostic=diagnostic, source="rule")


# ---------------------------------------------------------------------------

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
    # strip fences
    text = re.sub(r"^```(?:sql)?\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"\s*```$", "", text.strip())
    text = text.strip().rstrip(";").strip()
    if not text.lower().lstrip().startswith("select"):
        return None
    kpi = resolve_kpi(question)
    return GenSQL(sql=text, intent="llm", kpi=kpi, dimension=None,
                  month=_detect_month(question),
                  diagnostic=_is_diagnostic(question),
                  source="llm")


# ---------------------------------------------------------------------------

def generate_sql(question: str, llm: Optional[LLMClient] = None) -> GenSQL:
    if llm is not None and llm.available:
        g = _llm_generate(question, llm)
        if g is not None:
            return g
    return _rule_generate(question)
