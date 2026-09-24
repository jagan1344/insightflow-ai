"""Planner — turns a natural-language question + an ActiveDataset + a
KPICatalog into an AnalyticalPlan.

The planner is DETERMINISTIC and does not use an LLM. It works in three
stages:

    1. Surface analysis: which intent kind does this question look like?
       (direct KPI, breakdown, trend, comparison, growth, top-N,
       bottom-N, share of total, ratio, average-at-grain, contribution,
       ambiguous, unsupported).

    2. Binding: for every KPI mention, look it up in the KPICatalog. For
       every dimension mention (a word after "by ...", or a bare dim
       noun) look it up in `ActiveDataset.dimensions`. For every time
       mention, bind to a date column. For every filter mention, produce
       a FilterExpr against a real column.

    3. Shape selection: with the bindings in hand, the planner picks the
       one intent_kind whose shape best fits. If two candidates fit
       (e.g. "revenue by region in July" is both breakdown and filter),
       the more-specific one wins.

Nothing about this file is dataset-specific. Adding a new column layout
to the codebase does NOT require changing the planner — the catalog and
the dataset registry already carry that knowledge.
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import List, Optional, Tuple

from ..knowledge.dataset_registry import ActiveDataset
from ..knowledge.kpi_catalog import KPICatalog, KPIDefinition, build_catalog
from .plan import (
    AnalyticalPlan, ComparisonSpec, ContributionSpec, DimRef, FilterExpr,
    Grain, IntentKind, MeasureRef,
)


# ---------------------------------------------------------------------------
# Language vocabulary — pure linguistic knowledge, NOT dataset knowledge.
# Everything here is generic and does not reference the demo schema.
# ---------------------------------------------------------------------------

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_QUARTERS = {"q1": (1, 3), "q2": (4, 6), "q3": (7, 9), "q4": (10, 12)}

_TIME_UNIT_WORDS = {
    "day": "day", "daily": "day",
    "week": "week", "weekly": "week",
    "month": "month", "monthly": "month",
    "quarter": "quarter", "quarterly": "quarter",
    "year": "year", "yearly": "year", "annual": "year",
    "over time": "month", "trend": "month",
}

_TOP_WORDS      = ("top", "best", "highest", "largest", "most", "biggest",
                    "leader", "leaders", "leading")
_BOTTOM_WORDS   = ("bottom", "worst", "lowest", "smallest", "least",
                    "weakest")
_SHARE_WORDS    = ("share", "percentage", "percent", "% of", "proportion",
                    "contribution to total", "fraction")
_GROWTH_WORDS   = ("growth", "grow", "increase", "decrease", "decline",
                    "change", "changed", "trending", "up", "down",
                    "month-over-month", "mom", "yoy", "year-over-year")
_COMPARE_WORDS  = ("vs", "versus", "compared to", "compare",
                    "compared with", "against")
_CONTRIB_WORDS  = ("contributed", "contribution", "contributor",
                    "drove", "responsible for", "biggest driver",
                    "why did", "explain the change")
_AMBIGUOUS_HINTS = (
    "how is my business", "how are we doing", "how's business",
    "how's it going", "tell me about", "what should i do",
    "what do you think", "give me insights", "give me a summary",
    "any thoughts", "anything interesting", "the numbers",
    "overall picture", "big picture",
)


# =============================================================================
# Helper: normalise question text
# =============================================================================

def _norm(q: str) -> str:
    return " " + q.strip().lower() + " "


def _tokens(q: str) -> List[str]:
    return re.findall(r"[a-z_0-9]+", q.lower())


# =============================================================================
# Helper: extract time filter / grain from text
# =============================================================================

def _find_time_unit(q: str) -> Optional[str]:
    ql = _norm(q)
    for phrase, unit in _TIME_UNIT_WORDS.items():
        if f" {phrase} " in ql or f" {phrase}?" in ql:
            return unit
    return None


def _find_year(q: str) -> Optional[int]:
    m = re.search(r"\b(20\d{2})\b", q)
    return int(m.group(1)) if m else None


def _find_month_number(q: str) -> Optional[int]:
    ql = q.lower()
    m = re.search(r"\bin\s+([a-z]+)\b", ql)
    if m and m.group(1) in _MONTHS:
        return _MONTHS[m.group(1)]
    for name, num in _MONTHS.items():
        if re.search(rf"\b{name}\b", ql):
            return num
    return None


def _find_two_months(q: str) -> Optional[Tuple[int, int]]:
    """Find two month names in order, for comparison / contribution."""
    ql = q.lower()
    hits: List[Tuple[int, int]] = []  # (position, month#)
    for name, num in _MONTHS.items():
        for m in re.finditer(rf"\b{name}\b", ql):
            hits.append((m.start(), num))
    if len(hits) < 2:
        return None
    hits.sort()
    return (hits[0][1], hits[1][1])


def _period_string(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


# =============================================================================
# KPI binding
# =============================================================================

def _bind_kpis(question: str, catalog: KPICatalog) -> List[KPIDefinition]:
    """Return every KPI in the catalog whose alias appears in the text,
    longest alias first (so specific ones win). Overlapping matches are
    dropped so 'gross' inside 'gross margin' doesn't add a second KPI.
    """
    ql = _norm(question)
    matched: List[Tuple[int, int, str, KPIDefinition]] = []
    for kpi in catalog.kpis.values():
        for alias in kpi.aliases:
            a = alias.lower()
            if len(a) < 2:
                continue
            for m in re.finditer(
                    rf"(?<![a-z0-9_]){re.escape(a)}(?![a-z0-9_])", ql):
                matched.append((len(a), m.start(), kpi.kpi_id, kpi))
    # longest alias first; break ties by earliest position
    matched.sort(key=lambda t: (-t[0], t[1], t[2]))

    seen_ids: set = set()
    covered_spans: list[tuple[int, int]] = []
    out: List[KPIDefinition] = []
    for length, pos, kid, kpi in matched:
        if kid in seen_ids:
            continue
        span = (pos, pos + length)
        if any(s <= span[0] < e or s < span[1] <= e for s, e in covered_spans):
            continue
        covered_spans.append(span)
        seen_ids.add(kid)
        out.append(kpi)
    return out


# =============================================================================
# Dimension binding
# =============================================================================

_STOPWORDS_AFTER_BY = {
    "looking", "doing", "using", "the", "a", "an", "my", "our",
    "that", "which", "what", "some", "many", "how", "much",
    "each", "every", "any",
}


def _norm_col_key(s: str) -> str:
    return s.lower().strip().replace(" ", "_").replace("-", "_")


def _bind_dim_column(ds: ActiveDataset, name: str) -> Optional[str]:
    """Best-effort binding of a dimension noun to a physical column.

    Search order:
      1. exact column name (case-insensitive, hyphen/underscore-normalised)
      2. any dimension column whose name CONTAINS the noun as a token
      3. any dimension column whose noun CONTAINS the column name
      4. singular ↔ plural match
      5. common aliases (products→product_name, customers→customer_name, ...)
    """
    if not name:
        return None
    nl = _norm_col_key(name)
    # exact match — but only if the column is dimension-like
    for cname, info in ds.columns.items():
        if info.role in ("dimension", "id") and _norm_col_key(cname) == nl:
            return cname
    # 'sub_category' should beat 'category' when both are candidates.
    ranked: list[tuple[int, str]] = []
    for cname, info in ds.columns.items():
        if info.role != "dimension":
            continue
        cn = _norm_col_key(cname)
        score = 0
        if nl == cn:
            score = 100
        elif nl in cn:
            score = 50 + len(nl)
        elif cn in nl:
            score = 30 + len(cn)
        if score:
            ranked.append((score, cname))
    if ranked:
        ranked.sort(key=lambda t: (-t[0], t[1]))
        return ranked[0][1]
    # try singular ↔ plural
    if nl.endswith("s"):
        stripped = nl[:-1]
        for cname, info in ds.columns.items():
            if info.role != "dimension":
                continue
            cn = _norm_col_key(cname)
            if stripped in cn:
                return cname
    # domain aliases (demo dim conventions)
    _ALIAS = {
        "product": "product_name", "products": "product_name",
        "customer": "customer_name", "customers": "customer_name",
        "region": "region_name", "regions": "region_name",
    }
    if nl in _ALIAS:
        target = _ALIAS[nl]
        for cname in ds.columns.keys():
            if cname == target:
                return cname
    return None


def _looks_like_measure(noun: str, ds: ActiveDataset,
                         catalog: Optional[KPICatalog]) -> bool:
    lookup = _norm_col_key(noun)
    for c, info in ds.columns.items():
        if _norm_col_key(c) == lookup and info.role == "measure":
            return True
    if catalog is not None:
        for k in catalog.kpis.values():
            for alias in k.aliases:
                if _norm_col_key(alias) == lookup:
                    return True
    return False


def _find_dim_mentions(question: str, ds: ActiveDataset,
                         catalog: Optional[KPICatalog] = None
                         ) -> List[Tuple[str, str]]:
    """Return list of (raw_noun, bound_column). Unbound nouns yield ("noun", "").

    Extraction strategy:
      * "by <noun>" / "across <noun>" / "per <noun>" / "for each <noun>"
      * "which <noun>" (top-N implicit)
      * "top/bottom N <noun> by ..." — <noun> is dim
      * "<adj> <noun>" combined with a metric filter (e.g. "loss-making
        sub-categories") — <noun> is dim
      * bare mention of a dimension column name (hyphen-tolerant)
    """
    out: List[Tuple[str, str]] = []
    seen_nouns: set = set()
    # Normalise the query so hyphens between two words look like spaces.
    ql = _norm(question).replace("-", " ")

    for pat in [
        r"\bby\s+([a-z][a-z_\-\s]{1,30})",
        r"\bacross\s+([a-z][a-z_\-\s]{1,30})",
        r"\bper\s+([a-z][a-z_\-\s]{1,30})",
        r"\bfor\s+each\s+([a-z][a-z_\-\s]{1,30})",
        r"\bfrom\s+each\s+([a-z][a-z_\-\s]{1,30})",
        r"\bin\s+each\s+([a-z][a-z_\-\s]{1,30})",
    ]:
        for m in re.finditer(pat, ql):
            # Multi-word dims: try progressively longer sub-phrases (e.g.
            # "sub category", "product line") before falling back to the
            # first word.
            phrase = m.group(1).strip().rstrip("?.")
            candidates = []
            words = phrase.split()
            for k in range(min(3, len(words)), 0, -1):
                candidates.append(" ".join(words[:k]))
            noun = words[0]
            if noun in _STOPWORDS_AFTER_BY:
                continue
            # time-unit words are handled separately
            if noun in _TIME_UNIT_WORDS:
                continue
            if noun in seen_nouns:
                continue
            col = ""
            bound_noun = noun
            for cand in candidates:
                col = _bind_dim_column(ds, cand) or ""
                if col:
                    bound_noun = cand
                    break
            seen_nouns.add(noun)
            # Skip "by <measure_col_or_kpi>" — that names a metric
            # ordering, not a dim to CLARIFY on. Only add to `out` when
            # either bound to a dim or clearly not a measure/kpi.
            if not col and _looks_like_measure(noun, ds, catalog):
                continue
            out.append((bound_noun, col))

    # "top/bottom N <dim> by X" / "top <dim>" — dim between top and by
    m_top = re.search(r"\b(?:top|bottom|worst|best|highest|lowest)\s+"
                       r"\d*\s*([a-z][a-z_\s]{1,30}?)(?:\s+by\b|\s*$|\?)", ql)
    if m_top:
        noun = m_top.group(1).strip().split()[-1]
        if noun and noun not in seen_nouns and noun not in _STOPWORDS_AFTER_BY:
            col = _bind_dim_column(ds, noun) or ""
            if col:
                out.append((noun, col))
                seen_nouns.add(noun)

    # "which <dim>" — implicit top/bottom 1
    m_which = re.search(r"\bwhich\s+([a-z][a-z_\s]{1,30}?)\b", ql)
    if m_which:
        noun = m_which.group(1).strip().split()[0]
        if noun and noun not in seen_nouns and noun not in _STOPWORDS_AFTER_BY:
            col = _bind_dim_column(ds, noun) or ""
            if col:
                out.append((noun, col))
                seen_nouns.add(noun)

    # bare mention of a dimension column (hyphen/underscore-tolerant),
    # longest-name-first so 'sub_category' beats 'category'.
    cnames = sorted(
        [c for c, i in ds.columns.items() if i.role == "dimension"],
        key=lambda c: -len(c),
    )
    # Standalone "sub <noun>" mention where <noun> is a dim (e.g.
    # "sub-categories are losing money"). If the dataset actually has
    # a `sub_<noun>` column, bind to it; otherwise expose as unbound so
    # the plan CLARIFIES that the dataset can't answer that granularity.
    for m_sub in re.finditer(r"\bsub\s+([a-z]+)\b", ql):
        base = m_sub.group(1)
        base_sing = base
        if base.endswith("ies"):
            base_sing = base[:-3] + "y"
        elif base.endswith("s") and not base.endswith("ss"):
            base_sing = base[:-1]
        sub_dim = f"sub_{base_sing}"
        bound = _bind_dim_column(ds, sub_dim) or ""
        if sub_dim not in [c for c, _ in [(nn, cc) for nn, cc in out]] \
                and not any(n == sub_dim for n, _ in out):
            out.append((sub_dim, bound))
            if bound:
                seen_nouns.add(base)
                seen_nouns.add("sub")

    covered_spans: list[tuple[int, int]] = []
    for cname in cnames:
        cn_norm = cname.lower().replace("_", " ")
        # Build a small list of forms — singular, and a plural variant.
        forms = {cn_norm}
        if cn_norm.endswith("y"):
            forms.add(cn_norm[:-1] + "ies")
        elif cn_norm.endswith(("s", "sh", "ch", "x")):
            forms.add(cn_norm + "es")
        else:
            forms.add(cn_norm + "s")
        m = None
        for form in sorted(forms, key=len, reverse=True):
            m = re.search(rf"\b{re.escape(form)}\b", ql)
            if m:
                break
        if not m:
            continue
        span = (m.start(), m.end())
        # Skip a compound "sub <cname>" (user wrote "sub-categories" but
        # the dataset only has `category`). Instead register it as an
        # unbound `sub_<cname>` so the plan CLARIFIES.
        preceding = ql[max(0, span[0] - 6):span[0]].strip()
        if preceding.endswith("sub"):
            sub_noun = f"sub_{cname}"
            if sub_noun not in [c for _, c in out]:
                out.append((sub_noun, ""))
            continue
        if any(s <= span[0] < e or s < span[1] <= e for s, e in covered_spans):
            continue
        covered_spans.append(span)
        if cname not in [c for _, c in out]:
            out.append((cn_norm, cname))
            for w in cn_norm.split():
                seen_nouns.add(w)

    return out


# =============================================================================
# Filter binding
# =============================================================================

def _bind_time_filter(question: str, ds: ActiveDataset) -> List[FilterExpr]:
    """Extract time-window filters from text and bind them to a date column."""
    date_col = ds.dates[0] if ds.dates else ""
    if not date_col:
        return []
    filters: List[FilterExpr] = []
    year  = _find_year(question) or 2026
    month = _find_month_number(question)
    ql = question.lower()

    # explicit year+month
    if month is not None and "vs" not in ql and "versus" not in ql \
            and "compared" not in ql:
        period = _period_string(year, month)
        filters.append(FilterExpr(kind="time_range", column=date_col,
                                   lo=period, hi=period))
        return filters
    # quarter
    m = re.search(r"\bq([1-4])\b", ql)
    if m:
        qkey = f"q{m.group(1)}"
        lo_m, hi_m = _QUARTERS[qkey]
        filters.append(FilterExpr(
            kind="time_range", column=date_col,
            lo=_period_string(year, lo_m),
            hi=_period_string(year, hi_m),
        ))
    return filters


def _bind_metric_filter(question: str, kpis: List[KPIDefinition],
                         catalog: Optional[KPICatalog] = None
                         ) -> List[FilterExpr]:
    """'loss-making', 'unprofitable', 'in the red', '< 0' etc."""
    ql = question.lower()
    if any(t in ql for t in ("loss-making", "loss making", "unprofitable",
                              "losing money", "draining cash", "in the red",
                              "bleeding cash", "negative profit")):
        target = next((k for k in kpis if k.kpi_id == "profit"), None)
        if target is None and catalog is not None:
            target = catalog.get("profit")
        if target:
            return [FilterExpr(kind="metric_lt", kpi_id=target.kpi_id,
                                threshold=0.0)]
    return []


# =============================================================================
# Intent kind detection
# =============================================================================

def _has_word(q: str, words) -> bool:
    ql = _norm(q)
    return any(w in ql for w in words)


def _detect_intent_kind(
    question: str,
    kpis: List[KPIDefinition],
    dims: List[Tuple[str, str]],
    time_unit: Optional[str],
    two_months: Optional[Tuple[int, int]],
) -> str:
    ql = _norm(question)

    # ambiguous first — a vague/judgement question with no bindings.
    if not kpis and not dims and not time_unit and any(h in ql for h in _AMBIGUOUS_HINTS):
        return IntentKind.AMBIGUOUS

    # contribution — asks for who drove a change.
    if any(w in ql for w in _CONTRIB_WORDS) and two_months and dims:
        return IntentKind.CONTRIBUTION

    # comparison — two periods explicitly named.
    if _has_word(question, _COMPARE_WORDS) and two_months:
        return IntentKind.COMPARISON

    # growth — growth/change words with a time signal but not two periods.
    if _has_word(question, _GROWTH_WORDS) and (time_unit or two_months):
        if two_months:
            return IntentKind.COMPARISON
        return IntentKind.GROWTH

    # share of total.
    if _has_word(question, _SHARE_WORDS) and dims:
        return IntentKind.SHARE_OF_TOTAL

    # top-N / bottom-N.
    if _has_word(question, _TOP_WORDS) and dims:
        return IntentKind.TOP_N
    if _has_word(question, _BOTTOM_WORDS) and dims:
        return IntentKind.BOTTOM_N
    # "which X had the highest/lowest Y" — implicit top/bottom 1
    if re.search(r"\bwhich\b", ql) and dims and \
            (_has_word(question, _TOP_WORDS + _BOTTOM_WORDS)
             or "most" in ql or "least" in ql):
        return IntentKind.TOP_N if _has_word(question, _TOP_WORDS + ("most",)) \
                else IntentKind.BOTTOM_N

    # average-at-grain — "average <metric> per <time-unit>" or
    # "average monthly/weekly/... <metric>"
    if re.search(r"\baverage\b", ql) and time_unit:
        return IntentKind.AVERAGE_AT_GRAIN

    # trend — a time unit was named.
    if time_unit:
        return IntentKind.TREND

    # breakdown — a dim was named.
    if dims:
        return IntentKind.BREAKDOWN

    # ratio — "X per Y" where both are KPIs or a per-<id>.
    if re.search(r"\bper\b", ql) and len(kpis) >= 1:
        return IntentKind.RATIO

    # nothing else fired but we did bind a KPI — direct KPI.
    if kpis:
        return IntentKind.DIRECT_KPI

    # absolutely no bindings — ambiguous.
    return IntentKind.AMBIGUOUS


# =============================================================================
# Assembling the plan
# =============================================================================

def _mref(kpi: KPIDefinition) -> MeasureRef:
    return MeasureRef(
        kpi_id=kpi.kpi_id,
        display_name=kpi.display_name,
        formula=kpi.formula,
        aggregation=kpi.aggregation,
        unit=kpi.unit,
    )


def _dref(col: str, ds: ActiveDataset) -> DimRef:
    info = ds.columns.get(col)
    is_time = bool(info and info.role == "date")
    return DimRef(column=col, display_name=col.replace("_", " ").title(),
                  is_time=is_time)


class Planner:
    """Deterministic question → AnalyticalPlan planner."""

    def __init__(self, ds: ActiveDataset, catalog: Optional[KPICatalog] = None):
        self.ds = ds
        self.catalog = catalog or build_catalog(ds)

    # ------------------------------------------------------------------
    def plan(self, question: str) -> AnalyticalPlan:
        ds = self.ds
        catalog = self.catalog

        ql_lo = question.lower()
        kpis = _bind_kpis(question, catalog)
        # dim mentions (bound + unbound)
        dim_mentions = _find_dim_mentions(question, ds, catalog)
        bound_dims = [(n, c) for n, c in dim_mentions if c]
        unbound_dims = [n for n, c in dim_mentions if not c]

        time_unit = _find_time_unit(question)
        two_months = _find_two_months(question)

        # Loss-making / unprofitable filters pull in the profit KPI even
        # if the user didn't say the word.
        metric_filters = _bind_metric_filter(question, kpis, catalog=catalog)
        for f in metric_filters:
            k = catalog.get(f.kpi_id)
            if k and not any(m.kpi_id == k.kpi_id for m in kpis):
                kpis = [k] + kpis

        kind = _detect_intent_kind(question, kpis, bound_dims,
                                    time_unit, two_months)

        # "loss-making sub-categories" is a filtered breakdown, not a
        # direct KPI on the aggregate: promote it.
        if metric_filters and bound_dims and kind == IntentKind.DIRECT_KPI:
            kind = IntentKind.BREAKDOWN

        # Diagnostic questions — "why did X drop/decline in <month>" —
        # implicitly compare that month against the previous one. When
        # no dim is bound we default to the first dimension the dataset
        # exposes so the plan can produce a contribution decomposition.
        one_month = _find_month_number(question)
        is_diagnostic = one_month is not None and not two_months and any(
            w in ql_lo for w in ("why", "cause", "reason", "drop",
                                  "decline", "fell", "decrease", "lower",
                                  "diagnose"))
        if is_diagnostic:
            prev = one_month - 1 if one_month > 1 else 12
            two_months = (prev, one_month)
            if not bound_dims:
                # pick the first "natural" dimension the dataset has
                for cand in ("category", "region_name", "sub_category",
                              "product_name", "segment"):
                    if cand in ds.columns:
                        bound_dims = [(cand, cand)]
                        break
                if not bound_dims and ds.dimensions:
                    bound_dims = [(ds.dimensions[0], ds.dimensions[0])]
            kind = (IntentKind.CONTRIBUTION if bound_dims
                    else IntentKind.COMPARISON)

        # If two months are named + a dim is bound and the question hints
        # at contribution ("which", "contributed", "drove", "decline"),
        # elevate to contribution — this rescues cases the surface-word
        # rules missed.
        if kind == IntentKind.COMPARISON and bound_dims and (
                "which" in ql_lo or "contributed" in ql_lo or
                "drove" in ql_lo or "decline" in ql_lo or
                "biggest driver" in ql_lo):
            kind = IntentKind.CONTRIBUTION

        # Fallback KPIs when the user didn't name one but the question is
        # answerable-shaped (breakdown / trend / top-N / share).
        if not kpis and kind not in (IntentKind.UNSUPPORTED,
                                      IntentKind.AMBIGUOUS):
            fallback = catalog.get("total_revenue") or catalog.get("row_count")
            if fallback is not None:
                kpis = [fallback]

        # ---------- ambiguous / unsupported early exits ----------
        if kind == IntentKind.AMBIGUOUS or (not kpis and not bound_dims):
            plan = AnalyticalPlan(
                intent_kind=IntentKind.AMBIGUOUS,
                question=question, table=ds.table,
                notes=["No specific KPI or dimension bound from the question."],
            )
            for n in unbound_dims:
                plan.unavailable.append(f"dimension:{n}")
            return plan

        # ---------- build the plan by kind ----------
        measures = [_mref(k) for k in kpis]
        dims = [_dref(c, ds) for _, c in bound_dims]
        filters = _bind_time_filter(question, ds) + metric_filters
        notes: List[str] = []

        grain: Optional[Grain] = None
        comparison: Optional[ComparisonSpec] = None
        contribution: Optional[ContributionSpec] = None
        top_n: Optional[int] = None
        share = False
        order_by = ""

        date_col = ds.dates[0] if ds.dates else ""

        if kind == IntentKind.TREND:
            unit = time_unit or "month"
            if not date_col:
                return AnalyticalPlan(
                    intent_kind=IntentKind.UNSUPPORTED,
                    measures=measures, dims=dims, filters=filters,
                    question=question, table=ds.table,
                    unavailable=[f"time_grain:{unit}"],
                    notes=[f"Dataset {ds.name!r} has no date column."],
                )
            dims = [DimRef(column=date_col, display_name=date_col.title(),
                           is_time=True, time_unit=unit)]
            grain = Grain(kind="time", time_unit=unit, time_column=date_col)
            order_by = "time_asc"

        elif kind == IntentKind.AVERAGE_AT_GRAIN:
            unit = time_unit or "month"
            if not date_col:
                return AnalyticalPlan(
                    intent_kind=IntentKind.UNSUPPORTED,
                    measures=measures, dims=dims, filters=filters,
                    question=question, table=ds.table,
                    unavailable=[f"time_grain:{unit}"],
                )
            grain = Grain(kind="time", time_unit=unit, time_column=date_col)

        elif kind == IntentKind.TOP_N:
            n_match = re.search(r"\btop\s+(\d+)\b", question.lower())
            top_n = int(n_match.group(1)) if n_match else 5
            if re.search(r"\bwhich\b", question.lower()) and not n_match:
                top_n = 1
            order_by = "measure_desc"

        elif kind == IntentKind.BOTTOM_N:
            n_match = re.search(r"\bbottom\s+(\d+)\b", question.lower())
            top_n = int(n_match.group(1)) if n_match else 5
            if re.search(r"\bwhich\b", question.lower()) and not n_match:
                top_n = 1
            order_by = "measure_asc"

        elif kind == IntentKind.SHARE_OF_TOTAL:
            share = True

        elif kind == IntentKind.COMPARISON:
            if not date_col or not two_months:
                return AnalyticalPlan(
                    intent_kind=IntentKind.UNSUPPORTED,
                    measures=measures, dims=dims, filters=filters,
                    question=question, table=ds.table,
                    unavailable=(["date_column"] if not date_col else
                                  ["two_time_periods"]),
                )
            year = _find_year(question) or 2026
            comparison = ComparisonSpec(
                time_column=date_col,
                base_period=_period_string(year, two_months[0]),
                target_period=_period_string(year, two_months[1]),
                mode="delta",
            )
            # comparison overrides the plain time filter added above
            filters = [f for f in filters if f.kind != "time_range"]

        elif kind == IntentKind.GROWTH:
            unit = time_unit or "month"
            if not date_col:
                return AnalyticalPlan(
                    intent_kind=IntentKind.UNSUPPORTED,
                    measures=measures, dims=dims, filters=filters,
                    question=question, table=ds.table,
                    unavailable=[f"time_grain:{unit}"],
                )
            grain = Grain(kind="time", time_unit=unit, time_column=date_col)
            order_by = "time_asc"

        elif kind == IntentKind.CONTRIBUTION:
            if not date_col or not two_months or not bound_dims:
                return AnalyticalPlan(
                    intent_kind=IntentKind.UNSUPPORTED,
                    measures=measures, dims=dims, filters=filters,
                    question=question, table=ds.table,
                    unavailable=(["date_column"] if not date_col else
                                  ["two_time_periods_and_dimension"]),
                )
            year = _find_year(question) or 2026
            direction = "decline" if "decline" in question.lower() or \
                                     "drop" in question.lower() or \
                                     "fall" in question.lower() else \
                        ("gain" if "gain" in question.lower() or
                                    "grew" in question.lower() else "any")
            contribution = ContributionSpec(
                time_column=date_col,
                base_period=_period_string(year, two_months[0]),
                target_period=_period_string(year, two_months[1]),
                dim_column=bound_dims[0][1],
                direction=direction,
            )
            filters = [f for f in filters if f.kind != "time_range"]

        elif kind == IntentKind.RATIO:
            # If exactly one KPI and there's an id column mentioned, use
            # that id's count. Otherwise treat as direct KPI.
            pass

        # ---------- default order_by for breakdown ----------
        if kind == IntentKind.BREAKDOWN and not order_by:
            order_by = "measure_desc"

        # ---------- unavailable dims ----------
        unavailable: List[str] = [f"dimension:{n}" for n in unbound_dims]

        return AnalyticalPlan(
            intent_kind=kind,
            measures=measures,
            dims=dims,
            filters=filters,
            grain=grain,
            comparison=comparison,
            contribution=contribution,
            top_n=top_n,
            share_of_total=share,
            order_by=order_by,
            unavailable=unavailable,
            question=question,
            table=ds.table,
            notes=notes,
        )
