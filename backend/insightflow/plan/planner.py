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

import datetime as _dt
import os
import re
from dataclasses import replace
from typing import List, Optional, Tuple

from ..knowledge.dataset_registry import ActiveDataset
from ..knowledge.kpi_catalog import KPICatalog, KPIDefinition, build_catalog
from .plan import (
    AnalyticalPlan, ComparisonSpec, ContributionSpec, DimRef, FilterExpr,
    Grain, IntentKind, MeasureRef, RelativeStatSpec,
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
    "week": "week", "weekly": "week", "week-over-week": "week", "wow": "week",
    "month": "month", "monthly": "month",
    "month-over-month": "month", "mom": "month",
    "quarter": "quarter", "quarterly": "quarter",
    "quarter-over-quarter": "quarter", "qoq": "quarter",
    "year": "year", "yearly": "year", "annual": "year",
    "year-over-year": "year", "yoy": "year",
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
                    "why did", "explain the change",
                    "swing", "biggest change", "largest change",
                    "biggest movement", "largest movement",
                    "biggest shift", "largest shift", "biggest delta",
                    "largest delta")
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
    """Detect a trend/grain word ("monthly", "quarterly", "year-over-year").

    Suppressed when the unit word is actually part of a relative-period
    phrase ("last year", "this month", "next quarter"), which is a
    specific-period filter, not a trend request. See _find_relative_period.
    """
    ql = _norm(q)
    _REL_PREFIXES = ("last", "this", "previous", "current", "next",
                      "upcoming", "coming")
    for phrase, unit in _TIME_UNIT_WORDS.items():
        if f" {phrase} " not in ql and f" {phrase}?" not in ql:
            continue
        # Reject if preceded by a relative-period prefix.
        reject = False
        for prefix in _REL_PREFIXES:
            if f" {prefix} {phrase} " in ql or f" {prefix} {phrase}?" in ql:
                reject = True
                break
        if reject:
            continue
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
    """Find two month names (or quarter refs) in order for comparison
    or contribution.

    Suppressed when the connector between the two months is a RANGE
    connector ("through"/"to"/"until"/"-"/"and") rather than a comparison
    one ("vs"/"versus"/"compared to"/"against"). A range of months is a
    time filter, not a two-period comparison.

    Also handles "Q2 and Q3 2026" / "Q2 vs Q3 2026" by returning the
    middle months of each quarter — the planner's COMPARISON branch
    uses those as period labels downstream.
    """
    ql = q.lower()
    if _find_month_range(q) is not None:
        return None
    hits: List[Tuple[int, int]] = []  # (position, month#)
    for name, num in _MONTHS.items():
        for m in re.finditer(rf"\b{name}\b", ql):
            hits.append((m.start(), num))
    # Quarter mentions — use middle month of each quarter.
    for m in re.finditer(r"\bq([1-4])\b", ql):
        q_num = int(m.group(1))
        mid_month = (q_num - 1) * 3 + 2
        hits.append((m.start(), mid_month))
    if len(hits) < 2:
        return None
    hits.sort()
    return (hits[0][1], hits[1][1])


# ---------------------------------------------------------------------------
# Month-range detection (Defect A)
# ---------------------------------------------------------------------------

_RANGE_CONNECTORS = r"(?:through|thru|to|until|-|–|—|and)"


def _find_month_range(q: str) -> Optional[Tuple[int, int, Optional[int]]]:
    """Extract an inclusive month range of the form
    "from <A> (through|to|until|-|and) <B> [20YY]" or "<A> to <B> [20YY]".

    Returns (lo_month, hi_month, year_or_None). Only matches when the
    connector is a range connector, not a comparison one; so "January vs
    September" never matches here.
    """
    ql = q.lower()
    # Suppress when a comparison connector is present.
    if any(c in ql for c in (" vs ", " vs. ", " versus ",
                              " compared to ", " compared with ",
                              " against ")):
        return None
    # Suppress when growth/change wording is present — "how did revenue
    # change from June to July" is a two-period COMPARISON, not a
    # 2-month filter. Keep "monthly revenue from Jan through Sep" (no
    # growth words) as a range filter.
    _CHANGE_HINTS = (" change ", " changed ", " growth ", " grow ",
                      " grew ", " increase ", " decrease ", " decline ",
                      " trend ", " trending ", " how did ")
    if any(h in ql for h in _CHANGE_HINTS):
        return None

    # Build the month alternation.
    month_pat = "(" + "|".join(sorted(_MONTHS.keys(), key=len,
                                       reverse=True)) + ")"
    year_a_pat = r"(?:\s+(20\d{2}))?"  # optional year after month-A
    year_b_pat = r"(?:\s+(?:in\s+)?(20\d{2}))?"  # optional year after B
    patterns = [
        rf"\bfrom\s+{month_pat}{year_a_pat}\s+(?:through|thru|to|until|-|–|—|and)\s+{month_pat}{year_b_pat}\b",
        rf"\bbetween\s+{month_pat}{year_a_pat}\s+and\s+{month_pat}{year_b_pat}\b",
        rf"\b{month_pat}{year_a_pat}\s+(?:through|thru|to|until|–|—)\s+{month_pat}{year_b_pat}\b",
    ]
    for pat in patterns:
        m = re.search(pat, ql)
        if not m:
            continue
        a, year_a_raw, b, year_b_raw = m.group(1), m.group(2), m.group(3), m.group(4)
        if a not in _MONTHS or b not in _MONTHS:
            continue
        lo, hi = _MONTHS[a], _MONTHS[b]
        year = int(year_a_raw) if year_a_raw else (
            int(year_b_raw) if year_b_raw else None)
        year_hi = int(year_b_raw) if year_b_raw else (
            int(year_a_raw) if year_a_raw else None)
        return (lo, hi, year, year_hi)
    return None


# ---------------------------------------------------------------------------
# Relative-period resolution (Defect B)
# ---------------------------------------------------------------------------

def _reference_date() -> _dt.date:
    """The 'now' date relative-period phrases are resolved against.
    Override with env var INSIGHTFLOW_REF_DATE=YYYY-MM-DD for deterministic
    tests."""
    override = os.environ.get("INSIGHTFLOW_REF_DATE")
    if override:
        try:
            return _dt.date.fromisoformat(override)
        except ValueError:
            pass
    return _dt.date.today()


def _find_relative_period(q: str) -> Optional[Tuple[int, int, int, str]]:
    """Resolve relative-period phrases to (lo_year, lo_month, hi_year,
    hi_month inclusive) plus a kind label. Returns None if no relative
    phrase matches.

    Recognised: last year, this year, year to date / ytd, last month,
    this month, last quarter, this quarter.
    """
    ql = _norm(q)
    ref = _reference_date()
    y, m = ref.year, ref.month

    if re.search(r"\blast\s+year\b", ql):
        return (y - 1, 1, y - 1, 12, "last_year")
    if re.search(r"\bthis\s+year\b|\bcurrent\s+year\b", ql):
        return (y, 1, y, 12, "this_year")
    if re.search(r"\byear[- ]to[- ]date\b|\bytd\b", ql):
        return (y, 1, y, m, "ytd")
    if re.search(r"\bmonth[- ]to[- ]date\b|\bmtd\b", ql):
        return (y, m, y, m, "mtd")
    if re.search(r"\bquarter[- ]to[- ]date\b|\bqtd\b", ql):
        q_num = (m - 1) // 3 + 1
        lo_m = (q_num - 1) * 3 + 1
        return (y, lo_m, y, m, "qtd")
    if re.search(r"\blast\s+month\b|\bprevious\s+month\b", ql):
        lm_y, lm_m = (y, m - 1) if m > 1 else (y - 1, 12)
        return (lm_y, lm_m, lm_y, lm_m, "last_month")
    if re.search(r"\bthis\s+month\b|\bcurrent\s+month\b", ql):
        return (y, m, y, m, "this_month")
    if re.search(r"\blast\s+quarter\b|\bprevious\s+quarter\b", ql):
        q_num = (m - 1) // 3 + 1
        lq = q_num - 1 if q_num > 1 else 4
        lq_y = y if q_num > 1 else y - 1
        lo_m = (lq - 1) * 3 + 1
        hi_m = lo_m + 2
        return (lq_y, lo_m, lq_y, hi_m, "last_quarter")
    if re.search(r"\bthis\s+quarter\b|\bcurrent\s+quarter\b", ql):
        q_num = (m - 1) // 3 + 1
        lo_m = (q_num - 1) * 3 + 1
        hi_m = lo_m + 2
        return (y, lo_m, y, hi_m, "this_quarter")
    return None


# ---------------------------------------------------------------------------
# Forecasting / destructive-intent detection (Defects C, E)
# ---------------------------------------------------------------------------

_FORECAST_PATTERNS = (
    r"\bforecast(?:ed|ing|s)?\b",
    r"\bpredict(?:ed|ion|ions|s)?\b",
    r"\bprojection[s]?\b",
    r"\bprojected\b",
    r"\bwill\b.*\brevenue\b",
    r"\bwill\s+(?:the|our|my|be)\b",
    r"\bexpected\s+to\b",
    r"\bgoing\s+to\s+(?:be|see|make|earn)\b",
    r"\bestimate(?:d|s)?\s+(?:for|next|future|upcoming)\b",
    r"\bestimate\s+revenue\s+for\s+(?:november|december|january|february|march|april|may|june|july|august|september|october)\s+20(?:2[7-9]|[3-9]\d)\b",
    r"\bnext\s+(?:day|week|month|quarter|year)\b",
    r"\bupcoming\s+(?:day|week|month|quarter|year)\b",
    r"\bfuture\s+(?:day|week|month|quarter|year|revenue|sales|orders)\b",
    r"\bbudget\s+for\s+(?:next|upcoming|future|20(?:2[7-9]|[3-9]\d))\b",
    r"\bshould\s+we\s+expect\b",
    r"\bwhat\s+(?:do\s+)?(?:you\s+)?expect\b",
)


def is_forecast_question(q: str) -> bool:
    ql = _norm(q)
    return any(re.search(p, ql) for p in _FORECAST_PATTERNS)


_DESTRUCTIVE_VERBS = (
    "delete", "drop", "truncate", "destroy", "wipe", "erase", "purge",
    "clear", "remove", "modify", "update", "insert", "alter",
    "rollback", "reset",
)
_DESTRUCTIVE_TARGETS = (
    "orders", "customers", "products", "regions", "data", "database",
    "db", "records", "rows", "table", "tables", "entries", "everything",
    "all", "every",
)


def is_destructive_request(q: str) -> bool:
    """Detect a request to delete/modify/truncate data BEFORE SQL
    generation. Matches an imperative verb (optionally preceded by
    'please' or a prompt marker like '[ ]') followed by a destructive
    target word within a short window.
    """
    ql = _norm(q).strip()
    # Strip common prompt-template markers at the very start.
    ql = re.sub(r"^\s*[\[\(][^\]\)]*[\]\)]\s*", "", ql)
    ql = ql.lstrip(" .,:;-")
    verb_group = "|".join(_DESTRUCTIVE_VERBS)
    tgt_group = "|".join(_DESTRUCTIVE_TARGETS)
    # Imperative: optional "please", then verb within first few words,
    # then a destructive target within ~8 words.
    pat = rf"^(?:please\s+)?(?:{verb_group})\b[\w\s'\",\.]{{0,60}}?\b(?:{tgt_group})\b"
    if re.search(pat, ql):
        return True
    # Also match "I want to delete X" / "can you delete X"
    pat2 = (rf"\b(?:want|need|would like|try|can you|could you|please)\b"
            rf"[\w\s]*?\b(?:{verb_group})\b[\w\s'\",\.]{{0,60}}?"
            rf"\b(?:{tgt_group})\b")
    if re.search(pat2, ql):
        return True
    return False


def _period_string(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


# Spelled-number → integer, used by TOP_N / BOTTOM_N so "top three" and
# "top 3" plan identically.
_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
    "thirty": 30, "fifty": 50, "hundred": 100,
}


def _parse_count_after(ql: str, head: str, default: int = 5) -> int:
    """Parse the integer after a leading token like 'top' or 'bottom'.

    Accepts both digits ('top 3') and English spellings ('top three').
    Returns `default` when no count is given.
    """
    m = re.search(rf"\b{re.escape(head)}\s+(\d+)\b", ql)
    if m:
        return max(1, int(m.group(1)))
    m2 = re.search(
        rf"\b{re.escape(head)}\s+("
        + "|".join(sorted(_WORD_NUMBERS, key=len, reverse=True))
        + r")\b", ql)
    if m2:
        return _WORD_NUMBERS[m2.group(1)]
    return default


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
    "all", "looking", "doing", "using", "the", "a", "an", "my", "our",
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
    rel = getattr(ds, "rel", None)
    if rel is not None:
        from ..knowledge.rel_context import table_noun_dimension
        hit = table_noun_dimension(rel, name)
        if hit:
            return hit
    # abbreviation-tolerant token match ("destination" ~ "dest",
    # "cust" ~ "customer"): every noun token must match a column token
    # by equality or a >=4-char prefix, and the match must be unique.
    ntoks = [t for t in re.split(r"[^a-z0-9]+", name.lower()) if t]
    if ntoks and ds.kind != "demo":
        hits = []
        for cname, info in ds.columns.items():
            if info.role != "dimension":
                continue
            ctoks = [t for t in re.split(r"[^a-z0-9]+", cname.lower()) if t]
            if all(any(a == b or (min(len(a), len(b)) >= 4 and
                                   (a.startswith(b) or b.startswith(a)))
                       for b in ctoks) for a in ntoks):
                hits.append(cname)
        if len(hits) == 1:
            return hits[0]
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

    def _already_bound(col: str) -> bool:
        return col != "" and any(c == col for _, c in out)
    # Normalise the query so hyphens between two words look like spaces.
    ql = _norm(question).replace("-", " ")

    for pat in [
        r"\bby\s+([a-z][a-z_\-\s,]{1,60})",
        r"\bacross\s+([a-z][a-z_\-\s,]{1,60})",
        r"\bper\s+([a-z][a-z_\-\s,]{1,30})",
        r"\bfor\s+each\s+([a-z][a-z_\-\s]{1,30})",
        r"\bfrom\s+each\s+([a-z][a-z_\-\s]{1,30})",
        r"\bin\s+each\s+([a-z][a-z_\-\s]{1,30})",
    ]:
        for m in re.finditer(pat, ql):
            phrase = m.group(1).strip().rstrip("?.")
            # "paid BY students FROM California": an agent constraint, not a
            # grouping request.
            if re.match(r"^[a-z_\-]+(?:\s+[a-z_\-]+)?\s+"
                        r"(?:from|with|who|whose|living|based|born|located)\b",
                        phrase):
                continue
            # "by region and category" or "by region, category, month" —
            # split on "and"/comma first and bind each part in ORDER.
            # Otherwise "by region and category" was binding to
            # 'category' (longer name → higher score) and losing the
            # dim ordering the user actually asked for.
            parts = [p.strip() for p in
                      re.split(r"\s+and\s+|\s*,\s*", phrase) if p.strip()]
            for part in parts:
                # Multi-word single-dim: try progressively longer
                # sub-phrases (e.g. "sub category", "product line").
                words = part.split()
                if not words:
                    continue
                noun = words[0]
                if noun in _STOPWORDS_AFTER_BY:
                    continue
                if noun in _TIME_UNIT_WORDS:
                    continue
                if noun in seen_nouns:
                    continue
                candidates: list[str] = []
                for k in range(min(3, len(words)), 0, -1):
                    candidates.append(" ".join(words[:k]))
                col = ""
                bound_noun = noun
                for cand in candidates:
                    col = _bind_dim_column(ds, cand) or ""
                    if col:
                        bound_noun = cand
                        break
                seen_nouns.add(noun)
                if not col and any(_looks_like_measure(c, ds, catalog)
                                   for c in candidates):
                    continue
                if _already_bound(col):
                    continue
                out.append((bound_noun, col))

    # "top/bottom N <dim> by X" / "top <dim>" — dim between top and by
    m_top = re.search(r"\b(?:top|bottom|worst|best|highest|lowest)\s+"
                       r"\d*\s*([a-z][a-z_\s]{1,30}?)(?:\s+by\b|\s*$|\?)", ql)
    if m_top:
        noun = m_top.group(1).strip().split()[-1]
        if noun and noun not in seen_nouns and noun not in _STOPWORDS_AFTER_BY:
            col = _bind_dim_column(ds, noun) or ""
            if col and not _already_bound(col):
                out.append((noun, col))
                seen_nouns.add(noun)

    # "which <dim>" — implicit top/bottom 1. Try progressively longer
    # sub-phrases (up to 3 words) so "which sub category" binds the
    # multi-word dim column, not just "sub".
    m_which = re.search(r"\bwhich\s+([a-z][a-z_\s]{1,30}?)\b", ql)
    if m_which:
        phrase = m_which.group(1).strip()
        words = phrase.split()
        col = ""
        bound_noun = words[0]
        for k in range(min(3, len(words)), 0, -1):
            cand = " ".join(words[:k])
            col = _bind_dim_column(ds, cand) or ""
            if col:
                bound_noun = cand
                break
        # Widen the search a bit: also try the noun immediately after
        # "which" (e.g. "which sub category" → "sub category").
        if not col:
            extended = re.search(r"\bwhich\s+([a-z][a-z_\s]{1,40})",
                                  ql)
            if extended:
                tail = extended.group(1).strip().split()
                for k in range(min(3, len(tail)), 1, -1):
                    cand = " ".join(tail[:k])
                    col = _bind_dim_column(ds, cand) or ""
                    if col:
                        bound_noun = cand
                        break
        if bound_noun and bound_noun not in seen_nouns \
                and bound_noun not in _STOPWORDS_AFTER_BY \
                and col and not _already_bound(col):
            out.append((bound_noun, col))
            for w in bound_noun.split():
                seen_nouns.add(w)

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
        if bound and _already_bound(bound):
            continue
        if sub_dim not in [c for c, _ in out] \
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

def _mentioned_date_col(question: str, ds: ActiveDataset) -> Optional[str]:
    """The ONE date column the question points at. Specific words
    ('delivered', 'discharge') beat the plain table noun ('shipments' for
    ship_dt); the table noun only decides when nothing more specific is said."""
    if len(ds.dates) < 2:
        return None
    ql = _norm(question)
    words = re.findall(r"[a-z0-9]+", ql)
    tnouns = set()
    for t in re.split(r"[^a-z0-9]+", ds.table.lower()):
        if t:
            tnouns |= {t, t.rstrip("s")}
    specific, noun_only = [], []
    for d in ds.dates:
        toks = [t for t in re.split(r"[^a-z0-9]+", d.lower())
                if t and t not in ("date", "dt", "on", "at", "time")]
        sp = nn = False
        for t in toks:
            if len(t) < 3:
                continue
            stem = t[:max(4, len(t) - 2)]
            for w in words:
                if w.startswith(stem):
                    if w in tnouns:
                        nn = True
                    else:
                        sp = True
        if sp:
            specific.append(d)
        elif nn:
            noun_only.append(d)
    if len(specific) == 1:
        return specific[0]
    if not specific and len(noun_only) == 1:
        return noun_only[0]
    return None


def _ambiguous_date_columns(question: str, ds: ActiveDataset,
                             time_unit: Optional[str]) -> List[str]:
    """>1 date column and a time-based question that does not say which."""
    if len(ds.dates) < 2 or getattr(ds, "date_choice", None):
        return []
    ql = _norm(question)
    timey = bool(time_unit) or bool(re.search(
        r"\b(20\d\d|january|february|march|april|may|june|july|august|"
        r"september|october|november|december|last|this|month|quarter|year)\b",
        ql))
    if not timey:
        return []
    return [] if _mentioned_date_col(question, ds) else list(ds.dates)


_YEAR_CACHE: dict = {}


def _data_years(ds: ActiveDataset, date_col: str) -> List[int]:
    """Distinct calendar years present in a date column (cached by row count)."""
    import sqlite3
    from ..config import settings
    url = settings.database_url
    if not url.startswith("sqlite") or not date_col:
        return []
    path = url.split(":///", 1)[1] if ":///" in url else url
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            n = con.execute(f'SELECT COUNT(*) FROM "{ds.table}"').fetchone()[0]
            key = (path, ds.table, date_col, n)
            if key not in _YEAR_CACHE:
                rows = con.execute(
                    f'SELECT DISTINCT substr("{date_col}",1,4) FROM "{ds.table}" '
                    f'WHERE "{date_col}" IS NOT NULL').fetchall()
                if len(_YEAR_CACHE) > 64:
                    _YEAR_CACHE.clear()
                _YEAR_CACHE[key] = sorted(int(r[0]) for r in rows
                                          if str(r[0]).isdigit())
            return _YEAR_CACHE[key]
        finally:
            con.close()
    except Exception:
        return []


def _default_year(ds: ActiveDataset, date_col: str) -> int:
    """Year to use when the question names a month but no year: the
    dataset's own year (latest if several). Demo keeps its fixed default."""
    if ds.kind != "demo":
        ys = _data_years(ds, date_col)
        if ys:
            return ys[-1]
    return 2026


def _year_ambiguity(question: str, ds: ActiveDataset) -> List[int]:
    """Years in the data when the question names a month/quarter without a
    year and the data spans several years."""
    if ds.kind == "demo" or not ds.dates:
        return []
    ql = question.lower()
    from ..reliability.mention_coverage import year_tokens
    if year_tokens(ql):
        return []
    named = re.search(
        r"\b(january|february|march|april|june|july|august|september|october|"
        r"november|december)\b|\bq[1-4]\b|\b(?:in|of|during)\s+may\b", ql)
    if not named:
        return []
    ys = _data_years(ds, ds.dates[0])
    return ys if len(ys) > 1 else []


def _bind_time_filter(question: str, ds: ActiveDataset) -> List[FilterExpr]:
    """Extract time-window filters from text and bind them to a date column.

    Precedence (first match wins):
      1. Relative period ("last year", "year to date", "last month", ...).
      2. Explicit month range ("from January through September 2026").
      3. Quarter ("Q2 2026").
      4. Single explicit month ("in July 2026", "July 2026").
    """
    date_col = ds.dates[0] if ds.dates else ""
    if not date_col:
        return []
    filters: List[FilterExpr] = []
    ql = question.lower()

    # 1a. "Last N days" sliding window (Phase 2).
    n_days = _find_last_n_days(question)
    if n_days is not None and n_days > 0:
        import datetime as _d
        ref = _reference_date()
        lo_date = ref - _d.timedelta(days=n_days - 1)
        # time_range here carries full ISO dates ("YYYY-MM-DD") as lo/hi;
        # the compiler recognises that shape and emits a day-level filter
        # instead of the month-range predicate.
        filters.append(FilterExpr(
            kind="time_range", column=date_col,
            lo=lo_date.isoformat(),
            hi=(ref + _d.timedelta(days=1)).isoformat(),
        ))
        return filters

    # 1b. Relative period (Defect B)
    rel = _find_relative_period(question)
    if rel is not None:
        lo_y, lo_m, hi_y, hi_m, _kind = rel
        filters.append(FilterExpr(
            kind="time_range", column=date_col,
            lo=_period_string(lo_y, lo_m),
            hi=_period_string(hi_y, hi_m),
        ))
        return filters

    # 2. Month range (Defect A)
    rng = _find_month_range(question)
    if rng is not None:
        lo_m, hi_m, year_lo, year_hi = rng
        # If either year is missing, borrow from the other side or the
        # bare year token in the question, or default to 2026.
        default_year = _find_year(question) or _default_year(ds, date_col)
        lo_year = year_lo if year_lo is not None else (
            year_hi if year_hi is not None else default_year)
        hi_year = year_hi if year_hi is not None else (
            year_lo if year_lo is not None else default_year)
        # Backwards range ("September through January" with no explicit
        # hi-year) crosses year boundary into the next year.
        if hi_m < lo_m and year_hi is None:
            hi_year = lo_year + 1
        filters.append(FilterExpr(
            kind="time_range", column=date_col,
            lo=_period_string(lo_year, lo_m),
            hi=_period_string(hi_year, hi_m),
        ))
        return filters

    year = _find_year(question) or _default_year(ds, date_col)
    month = _find_month_number(question)

    # 3. Explicit single month (unchanged behaviour)
    if month is not None and "vs" not in ql and "versus" not in ql \
            and "compared" not in ql:
        period = _period_string(year, month)
        filters.append(FilterExpr(kind="time_range", column=date_col,
                                   lo=period, hi=period))
        return filters
    # 4. Quarters.
    # 4a. TWO quarters mentioned together → treat as a two-period
    # comparison. _find_two_months is where the planner expects two
    # periods; convert each quarter to its middle month so the
    # COMPARISON intent branch picks it up.
    q_hits = re.findall(r"\bq([1-4])\b", ql)
    if len(q_hits) >= 2 and any(w in ql for w in
                                 (" vs ", " vs. ", " versus ",
                                  " compared ", " and ", " to ",
                                  " between ")):
        # Return no filter here — the planner's COMPARISON branch (via
        # the two-months path) will emit the correct UNION ALL SQL.
        return filters
    # 4b. Single quarter.
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
    # 5. A bare year ("in 2025"): the whole calendar year. A single explicit
    # year only - two years mean a comparison, which is handled elsewhere.
    ql_nv = ql
    if ds.kind != "demo":          # digits inside a known value are not years
        for lo, _c in _value_mentions(question, _value_index(ds)):
            ql_nv = ql_nv.replace(lo, " ")
    from ..reliability.mention_coverage import year_tokens
    years = set(year_tokens(ql_nv))
    if len(years) == 1 and not re.search(r"\b(vs|versus|compared)\b", ql):
        y = int(next(iter(years)))
        filters.append(FilterExpr(
            kind="time_range", column=date_col,
            lo=_period_string(y, 1), hi=_period_string(y, 12)))
    return filters


def _find_post_agg_stat(question: str
                          ) -> Optional[Tuple[str, Optional[float], str]]:
    """Detect a request for median / percentile / stddev / variance.

    Returns (statistic, parameter, column) where
      statistic ∈ {"median", "percentile", "stddev", "variance"}
      parameter is the percentile value (0-100) when statistic ==
        "percentile", else None
      column is the physical column to pull (one of
        revenue / quantity / discount / cost — the only numeric
        columns on `orders`).
    Returns None when no match.
    """
    ql = " " + question.lower().strip() + " "
    _COLS = {
        "revenue": "revenue", "value": "revenue", "amount": "revenue",
        "order value": "revenue", "order revenue": "revenue",
        "sales": "revenue",
        "quantity": "quantity", "qty": "quantity", "units": "quantity",
        "discount": "discount", "cost": "cost",
    }

    def _pick_col(tail: str) -> str:
        for phrase in sorted(_COLS, key=len, reverse=True):
            if phrase in tail:
                return _COLS[phrase]
        return "revenue"

    # Median
    m = re.search(r"\bmedian\s+(?:order\s+|of\s+)?([a-z ]{3,30})", ql)
    if m or re.search(r"\bmedian\b", ql):
        tail = m.group(1).strip() if m else ql
        return ("median", None, _pick_col(tail))
    # Percentile — "90th percentile", "p95", "p75 of revenue"
    m = re.search(r"\b(\d{1,3})(?:st|nd|rd|th)?\s+percentile\b.*?"
                   r"(?:of\s+)?([a-z ]{3,30})?", ql)
    if m:
        try:
            p = float(m.group(1))
        except ValueError:
            return None
        if 0 <= p <= 100:
            tail = m.group(2) or ""
            return ("percentile", p, _pick_col(tail))
    m = re.search(r"\bp(\d{1,3})\b.*?(?:of\s+)?([a-z ]{3,30})?", ql)
    if m:
        try:
            p = float(m.group(1))
        except ValueError:
            return None
        if 0 <= p <= 100:
            tail = m.group(2) or ""
            return ("percentile", p, _pick_col(tail))
    # Stddev / variance
    m = re.search(r"\b(?:standard\s+deviation|stddev|std\s+dev)\s+(?:of\s+)?([a-z ]{3,30})", ql)
    if m:
        return ("stddev", None, _pick_col(m.group(1)))
    m = re.search(r"\bvariance\s+(?:of\s+)?([a-z ]{3,30})", ql)
    if m:
        return ("variance", None, _pick_col(m.group(1)))
    return None


def _find_last_n_days(question: str) -> Optional[int]:
    """Detect 'last N days / weeks' and return the number of days.
    Weeks are converted to days (* 7)."""
    ql = question.lower()
    m = re.search(r"\b(?:last|past|previous)\s+(\d{1,4})\s+days?\b", ql)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(?:last|past|previous)\s+(\d{1,3})\s+weeks?\b", ql)
    if m:
        return int(m.group(1)) * 7
    return None


def _find_rolling_window(question: str) -> Optional[int]:
    """Detect 'N-month rolling average' / 'rolling N-month average'
    / 'moving average' and return the window size in months. Returns
    `None` when the phrase isn't rolling-flavoured."""
    ql = question.lower()
    patterns = (
        r"\b(\d{1,3})[\s-]+month\s+(?:rolling|moving|trailing)\b",
        r"\b(?:rolling|moving|trailing)[\s-]+(\d{1,3})[\s-]+month\b",
        r"\b(?:rolling|moving|trailing)\s+average\b.*\b(\d{1,3})\b",
    )
    for p in patterns:
        m = re.search(p, ql)
        if m:
            try:
                return max(1, int(m.group(1)))
            except (TypeError, ValueError):
                pass
    if re.search(r"\b(?:rolling|moving|trailing)\s+average\b", ql):
        return 3  # default window
    return None


def _find_null_target_column(question: str, ds: ActiveDataset) -> Optional[str]:
    """Detect 'orders with missing <col>' / 'rows where <col> is null'
    and return the physical column name. The column must exist on the
    dataset."""
    ql = question.lower()
    patterns = (
        r"\b(?:with|where)\s+(?:missing|null|empty|blank|no|unspecified|unknown)\s+([a-z_]+)\b",
        r"\b([a-z_]+)\s+is\s+(?:null|missing|empty|blank)\b",
        r"\bmissing\s+([a-z_]+)\b",
        r"\bnull\s+([a-z_]+)\b",
    )
    if ds.kind != "demo":
        m = re.search(r"\b(?:missing|null|empty|blank|unspecified)\s+"
                      r"([a-z_ ]+?)\s*\??\s*$", ql) or \
            re.search(r"\b(?:have|has|with|where|having)\s+no\s+"
                      r"([a-z_ ]+?)\s*\??\s*$", ql) or \
            re.search(r"\b(?:with|where)\s+(?:no|an?\s+)?"
                      r"([a-z_ ]+?)\s+(?:is\s+)?(?:null|missing|empty|blank)"
                      r"\b", ql)
        if m:
            phrase = _norm_words(m.group(1))
            best = None
            _UNIT = {"usd", "eur", "gbp", "amt", "amount", "value", "val",
                     "kg", "lb", "pct", "num", "cnt", "total"}
            _pt = set(phrase.split())
            core_hits = []
            for cname in ds.columns:
                ct = [t for t in _norm_words(cname).split() if t not in _UNIT]
                if ct and all(t in _pt for t in ct):
                    core_hits.append(cname)
            for cname in ds.columns:
                n = _norm_words(cname)
                if re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])",
                             phrase) and (
                        best is None or len(n) > len(_norm_words(best))):
                    best = cname
            if best:
                return best
            if len(core_hits) == 1:
                return core_hits[0]
    for p in patterns:
        m = re.search(p, ql)
        if not m:
            continue
        token = m.group(1)
        # Direct column match.
        for cname in ds.columns:
            if cname.lower() == token:
                return cname
        # Common aliases.
        aliases = {
            "cost": "cost", "revenue": "revenue", "price": "revenue",
            "amount": "revenue", "quantity": "quantity", "qty": "quantity",
            "discount": "discount", "date": "order_date",
        }
        if token in aliases:
            for cname in ds.columns:
                if cname.lower() == aliases[token]:
                    return cname
    return None


def _find_distinct_count_dim(question: str, ds: ActiveDataset
                              ) -> Optional[Tuple[str, str]]:
    """Detect 'how many distinct X' / 'count of unique X' and bind X to
    a dimension column. Returns (noun, column) or None."""
    ql = question.lower()
    patterns = (
        r"\bhow\s+many\s+(?:distinct|unique|different|separate)\s+([a-z_]+)\b",
        r"\b(?:distinct|unique)\s+count\s+of\s+([a-z_]+)\b",
        r"\bcount\s+of\s+(?:distinct|unique|different)\s+([a-z_]+)\b",
        r"\bnumber\s+of\s+(?:distinct|unique|different)\s+([a-z_]+)\b",
    )
    for p in patterns:
        m = re.search(p, ql)
        if not m:
            continue
        noun = m.group(1)
        rel = getattr(ds, "rel", None)
        if rel is not None:
            from ..knowledge.rel_context import fk_noun_column
            if fk_noun_column(rel, noun):
                return None          # counted via the anchor FK KPI
        col = _bind_dim_column(ds, noun)
        if col:
            return (noun, col)
        # Try singular form.
        if noun.endswith("s"):
            col = _bind_dim_column(ds, noun[:-1])
            if col:
                return (noun, col)
    return None


_EXTREMUM_WORDS = {
    "max":     ("MAX", "max"),
    "maximum": ("MAX", "max"),
    "largest": ("MAX", "largest"),
    "highest": ("MAX", "highest"),
    "biggest": ("MAX", "biggest"),
    "greatest":("MAX", "greatest"),
    "min":     ("MIN", "min"),
    "minimum": ("MIN", "minimum"),
    "smallest":("MIN", "smallest"),
    "lowest":  ("MIN", "lowest"),
}


def _bind_measure_phrase(text: str, ds: ActiveDataset) -> Optional[str]:
    """Longest measure column whose space-normalised name appears in
    `text` (word-bounded)."""
    t = _norm_words(text)
    best = None
    _rel = getattr(ds, "rel", None)
    for cname, info in ds.columns.items():
        if info.role != "measure":
            continue
        if _rel is not None and _rel.source(cname) is not None:
            continue          # related-table attribute: not a base column
        n = _norm_words(cname)
        if re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", t):
            if best is None or len(n) > len(_norm_words(best)):
                best = cname
    return best


def _find_extremum(question: str, catalog: KPICatalog,
                    ds: Optional[ActiveDataset] = None
                    ) -> Optional[Tuple[str, str, str]]:
    """Detect 'minimum/maximum order <metric>' / 'largest order value'.
    Returns (sql_fn, display_name, column_expr) or None.

    Only matches ROW-LEVEL extremum (not aggregate "max revenue in July",
    which is a filtered sum).
    """
    ql = question.lower()
    if ds is not None and ds.kind != "demo" \
            and not re.search(r"^\s*which\b", ql):
        for word, (fn, label) in _EXTREMUM_WORDS.items():
            m = re.search(rf"\b{word}\s+(?:single\s+|individual\s+)?"
                          rf"(?:order\s+|row\s+|transaction\s+)?"
                          rf"([a-z_ ]+?)\s*\??\s*$", ql)
            if m:
                col = _bind_measure_phrase(m.group(1), ds)
                if col:
                    return (fn, label, col)
    # Column alias → physical column on the orders table.
    _COL = {
        "revenue": "revenue", "value": "revenue", "amount": "revenue",
        "quantity": "quantity", "qty": "quantity", "units": "quantity",
        "discount": "discount", "cost": "cost",
    }
    for word, (fn, label) in _EXTREMUM_WORDS.items():
        pat = rf"\b{word}\s+(?:single\s+|individual\s+)?(?:order|row|transaction)\s*(?:single\s+|individual\s+)?(revenue|value|amount|quantity|qty|units|discount|cost)\b"
        m = re.search(pat, ql)
        if m:
            col = _COL.get(m.group(1), m.group(1))
            return (fn, label, col)
    # Short form: "what's the maximum revenue?" when no dim is implied.
    # Reject when the question starts with "which <dim>" — that's a
    # top-1-breakdown pattern, not an aggregate extremum.
    if re.search(r"^\s*which\b", ql):
        return None
    for word, (fn, label) in _EXTREMUM_WORDS.items():
        pat = rf"^\s*(?:please\s+)?what(?:'s|\s+is)?\s+the\s+{word}\s+(revenue|order\s+value|quantity|units|discount|cost)\s*\??\s*$"
        m = re.search(pat, ql)
        if m:
            col = _COL.get(m.group(1).replace("order ", "").strip(), "revenue")
            return (fn, label, col)
    return None


def _find_top_per_group(question: str, ds: ActiveDataset, catalog: KPICatalog
                          ) -> Optional[Tuple[int, str, str]]:
    """Detect 'top N <inner_dim> per/in-each/within-each <partition_dim>'
    or 'rank <inner_dim> within each <partition_dim>'.

    Returns (n, inner_col, partition_col) or None.
    """
    ql = question.lower()
    m = re.search(
        r"\btop\s+(\d+|one|two|three|four|five|ten)?\s*([a-z_]+)\s+"
        r"(?:per|in\s+each|within\s+each|for\s+each|by\s+each)\s+([a-z_]+)\b", ql)
    if not m:
        # "top <dim> in each <group>" with no N → N=1
        m = re.search(
            r"\btop\s+([a-z_]+)\s+(?:in\s+each|per|within\s+each|for\s+each|by\s+each)\s+([a-z_]+)\b", ql)
        if m:
            n = 1
            inner_token, part_token = m.group(1), m.group(2)
        else:
            # "rank <inner> within each <group>" — no explicit N; use 10
            # as a reasonable default so each group's full rank list is
            # not accidentally returned (which could be millions of rows).
            m = re.search(
                r"\brank\s+([a-z_]+)\s+"
                r"(?:within\s+each|per|in\s+each|for\s+each)\s+([a-z_]+)\b", ql)
            if m:
                n = 10
                inner_token, part_token = m.group(1), m.group(2)
            else:
                return None
    else:
        n_raw = m.group(1) or "1"
        word_nums = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10}
        try:
            n = int(n_raw)
        except ValueError:
            n = word_nums.get(n_raw, 1)
        inner_token, part_token = m.group(2), m.group(3)
    inner_col = _bind_dim_column(ds, inner_token) \
                 or _bind_dim_column(ds, inner_token.rstrip("s"))
    part_col = _bind_dim_column(ds, part_token) \
                 or _bind_dim_column(ds, part_token.rstrip("s"))
    if not inner_col or not part_col or inner_col == part_col:
        return None
    return (n, inner_col, part_col)


def _find_threshold_grouped(question: str, ds: ActiveDataset,
                              catalog: KPICatalog
                              ) -> Optional[Tuple[str, str, float, str]]:
    """Detect 'months where <metric> > N' / 'regions with <metric>
    above M'. Returns (dim_col, kpi_id, threshold, operator) or None.

    `operator` is 'gt' or 'lt' (metric_gt_grouped / metric_lt_grouped).
    """
    ql = question.lower()
    _NUM_SUFFIX = {"k": 1_000, "thousand": 1_000, "m": 1_000_000,
                    "million": 1_000_000, "billion": 1_000_000_000}
    # Variant A: "which <dim-plural> ... <metric> <op> <num>"
    # Variant B: "<dim-plural> with <metric> <op> <num>"
    patterns = [
        (r"\b(?:which|what|in\s+which)\s+([a-z_]+)\b[^?]{0,60}?"
         r"\b([a-z_ ]+?)\s+"
         r"(exceed(?:ed|s)?|above|over|greater\s+than|more\s+than|>\s*|at\s+least)\s*"
         r"(?:\$\s*)?(\d[\d,]*(?:\.\d+)?)\s*(k|m|million|thousand|billion)?\b", "gt"),
        (r"\b([a-z_]+)\s+with\s+([a-z_ ]+?)\s+"
         r"(exceed(?:ed|s)?|above|over|greater\s+than|more\s+than|>\s*|at\s+least)\s*"
         r"(?:\$\s*)?(\d[\d,]*(?:\.\d+)?)\s*(k|m|million|thousand|billion)?\b", "gt"),
        (r"\b(?:which|what|in\s+which)\s+([a-z_]+)\b[^?]{0,60}?"
         r"\b([a-z_ ]+?)\s+"
         r"(below|under|less\s+than|<\s*|at\s+most)\s*"
         r"(?:\$\s*)?(\d[\d,]*(?:\.\d+)?)\s*(k|m|million|thousand|billion)?\b", "lt"),
    ]
    for pat, op in patterns:
        m = re.search(pat, ql)
        if not m:
            continue
        dim_token = m.group(1)
        metric_phrase = m.group(2).strip()
        num_raw = m.group(4)
        suffix = (m.group(5) or "").lower()
        try:
            threshold = float(num_raw.replace(",", ""))
        except ValueError:
            continue
        threshold *= _NUM_SUFFIX.get(suffix, 1)
        # Bind the dim. "months" → time bucket month; otherwise lookup.
        if dim_token in ("month", "months"):
            dim_col = "__month__"  # special sentinel; compiler handles
        elif dim_token in ("quarter", "quarters"):
            dim_col = "__quarter__"
        elif dim_token in ("year", "years"):
            dim_col = "__year__"
        else:
            dim_col = _bind_dim_column(ds, dim_token) \
                       or _bind_dim_column(ds, dim_token.rstrip("s"))
            if not dim_col:
                continue
        # Resolve the KPI from the metric phrase.
        kpi: Optional[KPIDefinition] = None
        for word_phrase in (metric_phrase,
                             metric_phrase.split()[-1],
                             metric_phrase.split()[0]):
            for k in catalog.kpis.values():
                if any(a.lower() == word_phrase for a in k.aliases):
                    kpi = k
                    break
            if kpi:
                break
        if not kpi:
            # Default to revenue when the user said "revenue"/"sales".
            kpi = catalog.get("total_revenue")
        if not kpi:
            continue
        return (dim_col, kpi.kpi_id, threshold, op)
    return None


_VALUE_STOPWORDS = {
    "the", "and", "for", "all", "any", "each", "every", "per", "other",
    "total", "average", "none", "null", "unknown", "yes", "no", "true",
    "false", "new", "top", "last", "this", "next", "year", "month",
    "week", "day", "which", "what", "how", "many", "much",
}
_MAX_DISTINCT_PER_DIM = 5000


def _norm_words(s: str) -> str:
    return re.sub(r"[\s_]+", " ", s.strip().lower())


def _value_index(ds: ActiveDataset) -> dict:
    """Schema-grounded index: lowercased distinct value -> [(column,
    original value)], built from every dimension column of an uploaded
    dataset. Columns with very high cardinality are skipped (they are
    identifiers, not filterable categories)."""
    import sqlite3
    from ..config import settings
    idx: dict = {}
    db_url = settings.database_url
    db_path = db_url.split(":///", 1)[1] if ":///" in db_url else db_url
    try:
        with sqlite3.connect(db_path) as c:
            rel = getattr(ds, "rel", None)
            for cname, info in ds.columns.items():
                if info.role != "dimension":
                    continue
                src = rel.source(cname) if rel is not None else None
                ptab, pcol = (src.table, src.column) if src else (ds.table, cname)
                rows = c.execute(
                    f'SELECT DISTINCT "{pcol}" FROM "{ptab}" '
                    f'WHERE "{pcol}" IS NOT NULL LIMIT '
                    f'{_MAX_DISTINCT_PER_DIM + 1}').fetchall()
                if len(rows) > _MAX_DISTINCT_PER_DIM:
                    continue
                for (v,) in rows:
                    lo = str(v).strip().lower()
                    if len(lo) < 2 or lo in _VALUE_STOPWORDS:
                        continue
                    if re.fullmatch(r"[\d\W_]+", lo):
                        continue
                    idx.setdefault(lo, []).append((cname, v))
    except Exception:
        return {}
    return idx


def _value_mentions(question: str, idx: dict) -> list:
    """Non-overlapping, longest-first mentions of known dim values.
    Returns [(lower_value, [(col, orig), ...])]. A value present in
    more than one column has >1 candidates (ambiguous)."""
    ql = question.lower()
    taken: list = []
    out: list = []
    for lo in sorted(idx, key=lambda v: (-len(v), v)):
        for m in re.finditer(
                rf"(?<![a-z0-9]){re.escape(lo)}(?![a-z0-9])", ql):
            span = (m.start(), m.end())
            if any(span[0] < e and s < span[1] for s, e in taken):
                continue
            taken.append(span)
            out.append((lo, idx[lo]))
            break
    return out


def _uploaded_dim_nouns(ds: ActiveDataset) -> dict:
    """noun phrase -> column, from the dataset's own dimension names."""
    nouns: dict = {}
    for cname, info in ds.columns.items():
        if info.role != "dimension":
            continue
        full = _norm_words(cname)
        nouns[full] = cname
        first = full.split(" ")[0]
        nouns.setdefault(first, cname)
    return nouns


def _find_ambiguous_values(question: str, ds: ActiveDataset) -> List[str]:
    if ds.kind == "demo":
        return []
    out = []
    rel = getattr(ds, "rel", None)
    for lo, cands in _value_mentions(question, _value_index(ds)):
        cols = sorted({c for c, _ in cands})
        if len(cols) > 1:
            out.append(f"ambiguous_value:{lo}=" + "|".join(cols))
        elif rel is not None and rel.source(cols[0]) is not None \
                and rel.source(cols[0]).kind == "ambiguous":
            src = rel.source(cols[0])
            out.append(f"ambiguous_join_path:{lo}=" + " | ".join(src.candidates))
    return out


_TITLE = re.compile(r"[A-Z][\w'&\-]*[a-z][\w'&\-]*")
_NOT_ENTITY = {"january", "february", "march", "april", "may", "june", "july",
               "august", "september", "october", "november", "december",
               "monday", "tuesday", "wednesday", "thursday", "friday",
               "saturday", "sunday", "top", "bottom", "show", "what",
               "which", "how", "why", "compare", "list", "give", "total"}


_NEG_CUE = re.compile(
    r"\b(not\s+including|excluding|exclude|except(?:\s+for)?|without|minus|"
    r"other\s+than|apart\s+from|not\s+counting|but\s+not|besides|"
    r"not\s+(?:in|from|for|at))\b")


def _find_negated_references(question: str, ds: ActiveDataset,
                              catalog: Optional[KPICatalog]) -> List[str]:
    """'everyone except Cardiology', 'total fee not including copay':
    exclusion is not implemented, and ignoring the cue would answer the
    OPPOSITE question (the excluded value becomes the filter). Refuse
    instead of guessing."""
    ql = question.lower()
    out = []
    for m in _NEG_CUE.finditer(ql):
        tail = ql[m.end(): m.end() + 60]
        hit = None
        if True:
            for c in ds.columns:
                ph = re.sub(r"[^a-z0-9]+", " ", c.lower()).strip()
                if ph and re.search(rf"(?<![a-z0-9]){re.escape(ph)}(?![a-z0-9])", tail):
                    hit = ph; break
        if hit is None and catalog is not None:
            for k in catalog.kpis.values():
                if any(re.search(rf"(?<![a-z0-9]){re.escape(a.lower())}(?![a-z0-9])", tail)
                       for a in k.aliases if len(a) > 3):
                    hit = k.display_name.lower(); break
        if hit:
            out.append(f"unsupported_exclusion:{m.group(0)} {hit}")
    return out


def _find_unknown_proper_nouns(question: str, ds: ActiveDataset,
                                catalog: Optional[KPICatalog]) -> List[str]:
    """Capitalised phrases (not sentence-initial, not months) that match no
    known value, column word, or KPI word are treated as references to
    entities the data does not contain."""
    if ds.kind == "demo":
        return []
    idx = _value_index(ds)
    known = set()
    for v in idx:
        known |= set(re.findall(r"[a-z0-9']+", v))
    for c in ds.columns:
        known |= set(re.findall(r"[a-z0-9]+", c.lower()))
    if catalog is not None:
        for k in catalog.kpis.values():
            for a in k.aliases:
                known |= set(re.findall(r"[a-z0-9]+", a.lower()))
            known |= set(re.findall(r"[a-z0-9]+", k.display_name.lower()))
    toks = list(_TITLE.finditer(question))
    phrases, cur = [], []
    for i, m in enumerate(toks):
        adj = cur and question[cur[-1].end():m.start()].strip() == ""
        if cur and adj and question[cur[-1].end():m.start()] == " ":
            cur.append(m)
        else:
            if cur:
                phrases.append(cur)
            cur = [m]
    if cur:
        phrases.append(cur)
    out = []
    for ph in phrases:
        words = [m.group(0).lower() for m in ph]
        if ph[0].start() == 0 and len(ph) == 1:
            continue
        if all(w in _NOT_ENTITY or w in known for w in words):
            continue
        if any(w in known for w in words):
            continue
        phrase = " ".join(words)
        if phrase in idx:
            continue
        before = question[:ph[0].start()].lower()
        if not re.search(r"\b(?:for|in|at|by|with|from|of|to|named|called|on|"
                         r"about|vs|versus|and|or|than)\s+(?:the\s+)?"
                         r"(?:[a-z_]+\s+)?$", before):
            continue        # not introduced like an entity reference
        out.append(f"value:unrecognised={phrase}")
    return out


_NEG_BEFORE = re.compile(
    r"(?:excluding|exclude|except(?:\s+for)?|without|other\s+than|apart\s+from|"
    r"aside\s+from|besides|minus|not\s+including|not\s+counting|but\s+not|"
    r"not\s+in|not\s+from|not\s+for|not\s+at|not\s+by|outside(?:\s+of)?)"
    r"\s+(?:the\s+|those\s+|any\s+|all\s+)?"
    r"(?:(?!and\b|or\b|but\b|for\b|in\b|by\b)[a-z_]+\s+){0,4}$")


def _classified_mentions(question: str, ds: ActiveDataset) -> list:
    """Known dimension values in the question with their polarity:
    [(lower_value, candidates, negated)] in text order. A value is negated
    after an exclusion cue ("except", "excluding", "not in"...), and the
    negation carries over "and"/"or"/comma-joined values."""
    idx = _value_index(ds)
    ql = question.lower()
    taken, found = [], []
    for lo in sorted(idx, key=lambda v: (-len(v), v)):
        for m in re.finditer(rf"(?<![a-z0-9]){re.escape(lo)}(?![a-z0-9])", ql):
            span = (m.start(), m.end())
            if any(span[0] < e and s < span[1] for s, e in taken):
                continue
            taken.append(span)
            found.append((m.start(), m.end(), lo, idx[lo]))
    found.sort()
    out, prev_neg, prev_end = [], False, -1
    for st, en, lo, cands in found:
        before = ql[max(0, st - 60):st]
        neg = bool(_NEG_BEFORE.search(before))
        if not neg and prev_neg and re.fullmatch(
                r"\s*(?:,|and|or|,\s*and|,\s*or)?\s*(?:the\s+)?(?:[a-z_]+\s+)?",
                ql[prev_end:st]):
            neg = True
        out.append((lo, cands, neg))
        prev_neg, prev_end = neg, en
    return out


def _find_conflicting_conditions(question: str, ds: ActiveDataset) -> List[str]:
    if ds.kind == "demo":
        return []
    seen = {}
    out = []
    for lo, cands, neg in _classified_mentions(question, ds):
        key = lo
        if key in seen and seen[key] != neg:
            out.append(f"conflicting_conditions:{lo}=included and excluded")
        seen[key] = neg
    return out


_CMP = [(r"at\s+least|>=|no\s+less\s+than", ">="),
        (r"at\s+most|<=|no\s+more\s+than", "<="),
        (r"more\s+than|greater\s+than|over|above|exceeding|>", ">"),
        (r"less\s+than|fewer\s+than|under|below|<", "<"),
        (r"exactly|equal\s+to|equals?|=|of|is", "=")]
_CMP_ALT = "|".join(f"(?:{p})" for p, _ in _CMP)


def _cmp_op(word: str) -> str:
    for p, op in _CMP:
        if re.fullmatch(p, word.strip()):
            return op
    return "="


def _find_numeric_filters(question: str, ds: ActiveDataset) -> List[FilterExpr]:
    """Row-level numeric conditions on NUMERIC ATTRIBUTES OF RELATED TABLES
    ("4 credit courses", "credits over 3"). Aggregate thresholds on the base
    measure ("customers with revenue above 1000") are a different feature and
    are not parsed here."""
    rel = getattr(ds, "rel", None)
    if rel is None:
        return []
    ql = question.lower()
    for lo, _c in _value_mentions(question, _value_index(ds)):
        ql = ql.replace(lo, " ")
    out = []
    for flat, src in rel.sources.items():
        if not getattr(src, "numeric", False) or src.kind != "safe":
            continue
        words = [w for w in re.split(r"[^a-z0-9]+", flat.lower()) if w]
        colpat = r"\s+".join(
            rf"{re.escape(w[:-1] if w.endswith('s') and len(w) > 3 else w)}s?" for w in words)
        num = r"(\d+(?:\.\d+)?)"
        m1 = re.search(rf"(?:\b({_CMP_ALT})\s*)?(?<![\d.]){num}\s*-?\s*{colpat}\b", ql)
        m2 = re.search(rf"\b{colpat}\s*(?:\b({_CMP_ALT})\b\s*)?(?<![\d.]){num}(?![\d])", ql)
        m = m1 or m2
        if not m:
            continue
        op_word, val = m.group(1), float(m.group(2))
        if re.fullmatch(r"(?:19|20)\d{2}", m.group(2)):
            continue                      # a year, not a quantity
        out.append(FilterExpr(kind="cmp", column=flat,
                              value=int(val) if val == int(val) else val,
                              op=_cmp_op(op_word) if op_word else "="))
    return out


def _find_value_filters(question: str, ds: ActiveDataset
                          ) -> List[FilterExpr]:
    """Detect value-equality filters of the form "<value> <dim-noun>"
    or "in <value> region / category / segment / for <value>".

    Returns a list of `FilterExpr(kind="eq", column=<physical column>,
    value=<string>)` for each distinct match. The value must match a
    known distinct value in the dataset's dim column — this prevents
    spurious matches on arbitrary nouns.

    Examples that match:
      "revenue in East region" → eq(regions.region_name='East')
      "revenue in Furniture category" → eq(products.category='Furniture')
      "revenue for Enterprise segment" → eq(customers.segment='Enterprise')
      "East region revenue" → same as above (prefix form)

    Examples that do NOT match:
      "revenue by region" (grouping, not filter)
      "which region had the highest revenue" (question about dim)
    """
    out: List[FilterExpr] = []
    if ds.kind != "demo":
        inc: dict = {}
        exc: dict = {}
        _rel = getattr(ds, "rel", None)
        for lo, cands, neg in _classified_mentions(question, ds):
            cols = {c for c, _ in cands}
            if len(cols) != 1:
                continue   # ambiguous: handled by _find_ambiguous_values
            col, orig = cands[0]
            if _rel is not None and _rel.source(col) is not None \
                    and _rel.source(col).kind == "ambiguous":
                continue
            (exc if neg else inc).setdefault(col, [])
            if orig not in (exc if neg else inc)[col]:
                (exc if neg else inc)[col].append(orig)
        for col, vals in inc.items():
            if len(vals) == 1:
                out.append(FilterExpr(kind="eq", column=col, value=vals[0]))
            else:
                # alternatives of the SAME column, never an empty conjunction
                out.append(FilterExpr(kind="in", column=col, value=vals))
        for col, vals in exc.items():
            out.append(FilterExpr(kind="not_in", column=col, value=vals))
        return out
    import sqlite3
    from ..config import settings

    # Map of dim-noun -> (physical column, candidate SQL for distinct values)
    _DIM_MAP = []
    if ds.kind == "demo":
        _DIM_MAP = [
            ("region", "regions.region_name",
             "SELECT DISTINCT region_name FROM regions"),
            ("category", "products.category",
             "SELECT DISTINCT category FROM products"),
            ("segment", "customers.segment",
             "SELECT DISTINCT segment FROM customers"),
            ("product", "products.product_name",
             "SELECT DISTINCT product_name FROM products"),
        ]
    else:
        # Uploaded single-table dataset: use the dataset's own dim columns.
        for cname, info in ds.columns.items():
            if info.role != "dimension":
                continue
            _DIM_MAP.append((cname.lower(), cname, None))

    # Load distinct values once.
    db_url = settings.database_url
    db_path = db_url.split(":///", 1)[1] if ":///" in db_url else db_url
    try:
        with sqlite3.connect(db_path) as c:
            values_per_dim = {}
            for noun, col, sql in _DIM_MAP:
                if sql is None:
                    quoted_col = f'"{col}"'
                    sql = f'SELECT DISTINCT {quoted_col} FROM "{ds.table}"'
                try:
                    values_per_dim[noun] = {
                        str(r[0]): r[0] for r in c.execute(sql).fetchall()
                        if r[0] is not None}
                except Exception:
                    values_per_dim[noun] = {}
    except Exception:
        return []

    ql = question.lower()
    seen: set = set()
    for noun, col, _sql in _DIM_MAP:
        values = values_per_dim.get(noun, {})
        if not values:
            continue
        lower_to_orig = {k.lower(): v for k, v in values.items()}
        for v_lo, v_orig in lower_to_orig.items():
            if not v_lo or len(v_lo) < 2:
                continue
            if (col, v_orig) in seen:
                continue
            pat = (rf"\b(?:in|for|within|from)?\s*(?:the\s+)?"
                   rf"{re.escape(v_lo)}\s+{re.escape(noun)}\b")
            if re.search(pat, ql):
                out.append(FilterExpr(kind="eq", column=col, value=v_orig))
                seen.add((col, v_orig))
    return out


def _find_unknown_dim_values(question: str, ds: ActiveDataset
                              ) -> List[str]:
    """Detect patterns like '<proper noun> <dim-noun>' / 'in <X> region'
    where the proper noun does NOT match any known dim value. Returns
    a list of "<dim>:<unknown_value>" strings suitable for
    `plan.unavailable` — the planner's existing CLARIFY path then
    surfaces the issue instead of silently answering with the all-dim
    total.
    """
    import sqlite3
    from ..config import settings
    if ds.kind != "demo":
        idx = _value_index(ds)
        nouns = _uploaded_dim_nouns(ds)
        if not nouns:
            return []
        per_col: dict = {}
        for lo, cands in idx.items():
            for c, _ in cands:
                per_col.setdefault(c, set()).add(lo)
        ql = " " + question.lower() + " "
        noun_alt = "|".join(sorted((re.escape(n) for n in nouns),
                                    key=len, reverse=True))
        unk: List[str] = []
        for m in re.finditer(
                rf"\b(?:in|for|within|from|at)\s+(?:the\s+)?"
                rf"([a-z0-9][a-z0-9&'\-\. ]{{0,40}}?)\s+({noun_alt})\b",
                ql):
            value = m.group(1).strip()
            noun = m.group(2)
            if not value or value.split()[0] in _VALUE_STOPWORDS or \
                    value in ("a", "an", "each", "every", "any", "all"):
                continue
            if value in idx or f"{value} {noun}" in idx:
                continue            # known value (possibly other column)
            if re.fullmatch(r"[\d\W_]+", value):
                continue
            # value with a known-value substring is handled by the filter
            if any(re.search(rf"(?<![a-z0-9]){re.escape(v)}(?![a-z0-9])",
                             value) for v in idx):
                continue
            unk.append(f"value:{noun}={value}")
        return unk
    unknowns: List[str] = []
    db_url = settings.database_url
    db_path = db_url.split(":///", 1)[1] if ":///" in db_url else db_url
    _DIM_SQL = [
        ("region", "SELECT region_name FROM regions"),
        ("category", "SELECT DISTINCT category FROM products"),
        ("segment", "SELECT DISTINCT segment FROM customers"),
    ]
    try:
        with sqlite3.connect(db_path) as c:
            known_per_dim = {noun: {str(r[0]).lower()
                                     for r in c.execute(sql).fetchall()
                                     if r[0] is not None}
                              for noun, sql in _DIM_SQL}
    except Exception:
        return []

    ql = " " + question.lower() + " "
    for noun, _sql in _DIM_SQL:
        # "in <word> <noun>" / "<word> <noun>" / "for <word> <noun>"
        for m in re.finditer(
                rf"\b(?:in|for|within|from)\s+(?:the\s+)?([a-z][a-z\-]+)\s+{re.escape(noun)}\b",
                ql):
            value = m.group(1)
            if value in ("a", "an", "the", "each", "every", "any",
                          "which", "what"):
                continue
            if value not in known_per_dim.get(noun, set()):
                unknowns.append(f"value:{noun}={value}")
    return unknowns


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
    *,
    ds: Optional[ActiveDataset] = None,
    catalog: Optional[KPICatalog] = None,
) -> str:
    ql = _norm(question)

    # New capability intents (Phase 2 2026-10-23) — these are checked
    # BEFORE the generic fallbacks so they are not mistaken for a
    # simple DIRECT_KPI / BREAKDOWN / TREND.
    if ds is not None:
        if _find_null_target_column(question, ds):
            return IntentKind.NULL_COUNT
        if _find_distinct_count_dim(question, ds):
            return IntentKind.DISTINCT_COUNT
    if _find_rolling_window(question) is not None:
        return IntentKind.ROLLING_AVG
    if catalog is not None and _find_extremum(question, catalog, ds):
        return IntentKind.EXTREMUM
    if ds is not None and catalog is not None \
            and _find_top_per_group(question, ds, catalog):
        return IntentKind.TOP_N_PER_GROUP
    if ds is not None and catalog is not None \
            and _find_threshold_grouped(question, ds, catalog):
        return IntentKind.THRESHOLD_GROUPED
    # Phase 4 (2026-10-23): post-aggregation stats computed in Python.
    if _find_post_agg_stat(question):
        return IntentKind.POST_AGG_STAT

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

    # top-N / bottom-N. But if TWO periods are named plus a
    # change-flavored word ("largest ... from A to B") the user really
    # wants the biggest per-dim swing across periods — that's
    # contribution, not a plain top-N on one period.
    change_flavored = any(w in ql for w in _GROWTH_WORDS + _CONTRIB_WORDS)
    if _has_word(question, _TOP_WORDS) and dims and two_months \
            and change_flavored:
        return IntentKind.CONTRIBUTION
    if _has_word(question, _TOP_WORDS) and dims:
        return IntentKind.TOP_N
    if _has_word(question, _BOTTOM_WORDS) and dims and two_months \
            and change_flavored:
        return IntentKind.CONTRIBUTION
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

def _find_entity_column(ds: ActiveDataset,
                         catalog: KPICatalog,
                         bound_dims: List[Tuple[str, str]],
                         question: str) -> Optional[str]:
    """Pick the "entity" the relative-to-stat filter is talking about.

    Priority:
      1. The entity noun in the question — "customers with ...",
         "which products have ...", "products whose ...". Bind to a
         real column via the dim resolver (with plural handling and
         friendly aliases like customer→customer_name).
      2. Any dim/id column whose name appears in the question.
      3. First bound dim.
      4. First dim column (prefer named entities, not ids).
      5. First id column.
    """
    ql = question.lower()

    # 1) Entity-noun pattern: "<noun> with/whose/that/having"
    entity_patterns = [
        r"^\s*(?:which\s+|show\s+me\s+|list\s+)?([a-z][a-z_ ]{1,30}?)s?\s+(?:with|whose|that|having|where|are)\b",
        r"\bfor\s+(?:each|every)\s+([a-z][a-z_]+)s?\b",
    ]
    for pat in entity_patterns:
        m = re.search(pat, ql)
        if not m:
            continue
        noun = m.group(1).strip().split()[-1]
        if not noun or noun in _STOPWORDS_AFTER_BY:
            continue
        # Friendly alias — a user saying "customers" typically wants
        # the customer_name label column, not the customer_id key.
        _NAME_ALIAS = {
            "customer": "customer_name",
            "product": "product_name",
            "region": "region_name",
        }
        preferred = _NAME_ALIAS.get(noun)
        if preferred and preferred in ds.columns:
            return preferred
        col = _bind_dim_column(ds, noun)
        if col:
            return col

    # 2) Explicit column mention (existing behaviour)
    for cname, info in ds.columns.items():
        if info.role in ("id", "dimension"):
            token = cname.lower().replace("_", " ")
            if re.search(rf"\b{re.escape(token)}s?\b", ql):
                return cname

    # 3) First bound dim
    if bound_dims:
        return bound_dims[0][1]

    # 4) Prefer a named-entity dim over a raw id (row_id would be a
    # terrible group-by choice).
    for cname in catalog.dimensions:
        return cname
    for cname in catalog.id_columns:
        return cname
    return None


_STAT_WORDS = {
    "average": "avg", "avg": "avg", "mean": "avg",
    "median": "median",
}
_OP_WORDS_GT = ("above", "greater than", "more than", "higher than",
                 "exceed", "exceeding", "over")
_OP_WORDS_LT = ("below", "less than", "lower than", "under",
                 "beneath", "smaller than")


def _detect_relative_to_stat(question: str, ds: ActiveDataset,
                              catalog: KPICatalog,
                              bound_dims: List[Tuple[str, str]]
                              ) -> Optional[RelativeStatSpec]:
    """Look for '<measure> above/below the average/median' patterns and
    build a RelativeStatSpec. Supports one AND'd second clause."""
    ql = " " + question.lower() + " "
    if not any(w in ql for w in _OP_WORDS_GT + _OP_WORDS_LT):
        return None

    def find_clause(text: str):
        """Return (kpi_id, stat, op) or None for one clause."""
        # find stat word
        stat = None
        stat_pos = -1
        for word, code in _STAT_WORDS.items():
            m = re.search(rf"\b{word}\b", text)
            if m and (stat_pos == -1 or m.start() < stat_pos):
                stat = code; stat_pos = m.start()
        if stat is None:
            return None
        # find operator
        op = None
        op_pos = -1
        for w in _OP_WORDS_GT:
            m = re.search(rf"\b{re.escape(w)}\b", text)
            if m and (op_pos == -1 or m.start() < op_pos):
                op = "gt"; op_pos = m.start()
        for w in _OP_WORDS_LT:
            m = re.search(rf"\b{re.escape(w)}\b", text)
            if m and (op_pos == -1 or m.start() < op_pos):
                op = "lt"; op_pos = m.start()
        if op is None:
            return None
        # find KPI mentioned in this clause (or fall back to nearest KPI
        # before the op word).
        kpi_hits = []
        for kpi in catalog.kpis.values():
            for alias in kpi.aliases:
                a = alias.lower()
                if len(a) < 3:
                    continue
                for m in re.finditer(
                        rf"(?<![a-z0-9_]){re.escape(a)}(?![a-z0-9_])", text):
                    kpi_hits.append((m.start(), len(a), kpi))
        # Prefer the KPI that appears BEFORE the op (so "revenue above
        # avg" binds to revenue, not to whatever comes after)
        kpi_hits = [h for h in kpi_hits if h[0] < op_pos] + kpi_hits
        # Longest alias first among those before op
        before = sorted([h for h in kpi_hits if h[0] < op_pos],
                        key=lambda h: (-h[1], h[0]))
        after = sorted([h for h in kpi_hits if h[0] >= op_pos],
                       key=lambda h: (-h[1], h[0]))
        picked = before[0] if before else (after[0] if after else None)
        if picked is None:
            return None
        return (picked[2].kpi_id, stat, op)

    # Split into "clause1 AND clause2" if AND / but is present
    parts = re.split(r"\b(?:and|but)\b", ql)
    clause1 = find_clause(parts[0])
    if clause1 is None and len(parts) > 1:
        clause1 = find_clause(parts[1])
    if clause1 is None:
        return None
    clause2 = find_clause(parts[1]) if len(parts) > 1 else None

    kpi_id, stat, op = clause1
    entity = _find_entity_column(ds, catalog, bound_dims, question)
    if entity is None:
        return None
    spec = RelativeStatSpec(measure_kpi_id=kpi_id,
                             entity_column=entity, stat=stat, op=op)
    if clause2 is not None and clause2[0] != kpi_id:
        spec.and_measure_kpi_id = clause2[0]
        spec.and_stat = clause2[1]
        spec.and_op = clause2[2]
    return spec


def _protect_value_commas(question: str, ds: ActiveDataset) -> str:
    """A comma inside a known dimension value ("O'Neil, Sam") is not a
    clause separator."""
    if ds.kind == "demo" or "," not in question:
        return question
    ql = question.lower()
    for lo in _value_index(ds):
        if "," not in lo:
            continue
        for m in re.finditer(rf"(?<![a-z0-9]){re.escape(lo)}(?![a-z0-9])", ql):
            seg = question[m.start():m.end()].replace(",", "\u2063")
            question = question[:m.start()] + seg + question[m.end():]
            ql = question.lower()
    return question


def _first_clause(question: str) -> str:
    """Split a compound question on ", " or " and " between independent
    clauses and return the first. Doesn't split short natural phrases
    like "revenue and profit" (a coordinated noun pair, no verb after
    "and"), only clear multi-clause forms like
    "Top 5 X by Y in Q2 2026, Revenue in the first half of the year".
    """
    q = question.strip()
    # Comma-followed-by-capitalised-word is the strongest signal.
    m = re.search(r",\s+([A-Z][A-Za-z]+)", q)
    if m and m.start() > 8:
        return q[:m.start()].rstrip(" ,.;")
    # Otherwise, split on " and " ONLY when the second half looks like a
    # separate clause. Cheap heuristic: second half starts with a metric
    # word AND contains a preposition.
    #
    # Important exception (Defect G): "noun1 and noun2 by X" is NOT a
    # compound question — it's a coordinated noun pair that shares the
    # grouping "by X". So if the token immediately before " and " is
    # itself a bare noun (not followed by "in"/"by"/"per"/… — i.e. the
    # grouping/filter clause is only AFTER noun2), do not split.
    lo = q.lower()
    idx = lo.find(" and ")
    if idx > 8:
        second = q[idx + 5:].strip()
        if re.match(r"^[A-Za-z]+\s+(?:in|by|per|from|for|across)\b",
                     second):
            # Check the pre-"and" context — if it ends with a bare noun
            # that could also take the grouping ("revenue and profit by
            # X"), don't split. Specifically: if the first clause does
            # NOT already contain its own grouping/filter preposition,
            # the "by X" after "and" belongs to BOTH nouns.
            first = q[:idx]
            first_has_grouping = bool(re.search(
                r"\b(?:in|by|per|from|for|across)\s+[A-Za-z]",
                first.lower()))
            if first_has_grouping:
                return first.rstrip(" ,.;")
            # else fall through: treat as coordinated noun pair, keep whole.
    return q


def _promote_by_measure(question: str, measures: List[MeasureRef],
                          catalog: KPICatalog) -> List[MeasureRef]:
    """For "top N X by <metric> ...": find the KPI whose alias appears
    right after "by" and move it to position 0 of the measures list, so
    ORDER BY / LIMIT rank on the metric the user asked for — not on
    whichever KPI happened to match a longer alias earlier in the
    question ("Revenue ..." matching "revenue" is 7 chars vs "profit"
    at 6, so total_revenue would otherwise win)."""
    if len(measures) < 2:
        return measures
    ql = question.lower()
    m = re.search(r"\bby\s+([a-z][a-z_ ]{1,30})", ql)
    if not m:
        return measures
    tail = m.group(1).strip()
    # Try progressively shorter prefixes so "by average order value" and
    # "by profit in Q2" both bind correctly.
    words = tail.split()
    best_kpi_id: Optional[str] = None
    for k in range(min(4, len(words)), 0, -1):
        cand = " ".join(words[:k])
        for kpi in catalog.kpis.values():
            for alias in kpi.aliases:
                if alias.lower() == cand:
                    best_kpi_id = kpi.kpi_id
                    break
            if best_kpi_id:
                break
        if best_kpi_id:
            break
    if not best_kpi_id:
        return measures
    ordered: List[MeasureRef] = [m for m in measures if m.kpi_id == best_kpi_id]
    ordered.extend(m for m in measures if m.kpi_id != best_kpi_id)
    return ordered


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

        # Compound questions ("Sales by region, Profit by month" or
        # "Top 5 by profit in Q2, revenue in H1") are not one plan.
        # Keep only the first clause so the plan pipeline gives a clean
        # answer to one question. The user can ask the second question
        # separately. Record the dropped part in plan.notes so the
        # response can surface it to the user.
        _dm = _mentioned_date_col(question, ds)
        if _dm and ds.dates and _dm != ds.dates[0]:
            import copy as _copy
            ds = _copy.copy(ds)
            ds.columns = {_dm: ds.columns[_dm],
                          **{k: v for k, v in ds.columns.items() if k != _dm}}
            ds.date_choice = _dm
            self.ds = ds
        original = question
        question = _protect_value_commas(question, ds)
        question = _first_clause(question).replace("\u2063", ",")
        _dropped_suffix = ""
        if question != original and original.startswith(question):
            _dropped_suffix = original[len(question):].lstrip(" ,.;")
        ql_lo = question.lower()
        kpis = _bind_kpis(question, catalog)
        _metric_conflicts: List[str] = []
        for _alias, _ids in getattr(catalog, "conflicts", {}).items():
            if _alias.startswith("__"):
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(_alias)}(?![a-z0-9])",
                         ql_lo) and not any(k.kpi_id in _ids for k in kpis):
                _metric_conflicts.append(
                    f"ambiguous_metric:{_alias}=" + "|".join(_ids))
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

        # "How many sales ..." asks for a count of records, even though
        # "sales" is also a revenue alias. A monetary/sum KPI bound only
        # through the counted noun is replaced by the row count.
        _hm = re.search(r"\b(?:how\s+many|number\s+of)\s+([a-z_]+)", ql_lo)
        if _hm and len(kpis) == 1 and kpis[0].aggregation in (
                "sum", "derived") and catalog.get("row_count") is not None \
                and not re.search(r"\b(distinct|unique)\b", ql_lo) \
                and re.search(rf"\b{re.escape(_hm.group(1))}\b",
                              " ".join(kpis[0].aliases).lower()) \
                and not re.search(r"\b(?:total|sum|amount|value|revenue)\b",
                                  ql_lo[_hm.end():]):
            kpis = [catalog.get("row_count")]

        kind = _detect_intent_kind(question, kpis, bound_dims,
                                    time_unit, two_months,
                                    ds=ds, catalog=catalog)

        # "loss-making sub-categories" is a filtered breakdown, not a
        # direct KPI on the aggregate: promote it.
        if metric_filters and bound_dims and kind == IntentKind.DIRECT_KPI:
            kind = IntentKind.BREAKDOWN

        # "customers with revenue above average" / "products with profit
        # below the median" / "customers with revenue above average AND
        # profit below average" — a relative-to-stat filter on entities.
        rel_spec = _detect_relative_to_stat(question, ds, catalog, bound_dims)
        if rel_spec is not None:
            kind = IntentKind.RELATIVE_TO_STAT

        # Diagnostic questions — "why did X drop/decline in <month>" —
        # implicitly compare that month against the previous one, and
        # when a dim is available (either explicitly bound by the user
        # OR a natural default on the dataset) decompose by dimension.
        # (Defect D: this used to require `not two_months`, which skipped
        # the diagnostic path for "Why did X drop in July compared to
        # June?" because _find_two_months would already have returned
        # (6, 7).)
        _DIAG_WORDS = ("why", "cause", "reason", "drop",
                        "decline", "fell", "decrease", "lower",
                        "diagnose", "dropped", "declined", "fallen")
        has_diag_word = any(w in ql_lo for w in _DIAG_WORDS)
        one_month = _find_month_number(question)
        is_diagnostic = has_diag_word and (
            one_month is not None or two_months is not None)
        if is_diagnostic:
            if two_months is None and one_month is not None:
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
        _AGG_CUE = re.compile(
            r"\b(average|avg|mean|median|maximum|minimum|max|min|"
            r"how\s+many|number\s+of|count)\b")
        _count_cue = re.search(r"\b(how\s+many|number\s+of|count)\b", ql_lo)
        if not kpis and _count_cue and kind == IntentKind.DIRECT_KPI \
                and catalog.get("row_count") is not None:
            kpis = [catalog.get("row_count")]
        elif not kpis and kind == IntentKind.DIRECT_KPI \
                and _AGG_CUE.search(ql_lo):
            # An explicit aggregate was requested but no measure binds:
            # never fall back to revenue silently.
            kind = IntentKind.AMBIGUOUS
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
            plan.unavailable.extend(_metric_conflicts)
            return plan

        # ---------- build the plan by kind ----------
        _nf_pre = _find_numeric_filters(question, ds)
        if _nf_pre and len(kpis) > 1:
            _fcols = {f.column for f in _nf_pre}
            _keep = [k for k in kpis
                     if not any("{{dim:%s}}" % c in k.formula for c in _fcols)]
            if _keep:
                kpis = _keep
        measures = [_mref(k) for k in kpis]
        dims = [_dref(c, ds) for c in [c for _, c in bound_dims]]
        # Phase 2 (2026-10-24): value-equality filters on dim values
        # ("in East region", "for Furniture category", "SMB segment").
        value_filters = _find_value_filters(question, ds) \
            + _find_numeric_filters(question, ds)
        if ds.kind != "demo" and unbound_dims:
            _vtext = " ".join(str(f.value).lower() for f in value_filters)
            _vtext += " " + " ".join(
                lo for lo, _c in _value_mentions(question, _value_index(ds)))
            unbound_dims = [n for n in unbound_dims
                            if not re.search(rf"(?<![a-z0-9]){re.escape(n.lower())}(?![a-z0-9])", _vtext)]
        filters = _bind_time_filter(question, ds) + metric_filters \
                  + value_filters
        # Early notes list — populated by the value-filter / dim-dedup
        # pass below. Later code (`notes: List[str] = []`) overwrites;
        # we re-assign to append-safe before then.
        _early_notes: List[str] = []
        # Unknown-dim-value detection ("Antarctica region" etc.):
        # mark the request as unavailable so the planner's CLARIFY
        # path fires instead of silently answering with the all-dim
        # total.
        _unknown_values: List[str] = _find_unknown_dim_values(question, ds)
        _unknown_values += _find_ambiguous_values(question, ds)
        _unknown_values += _find_unknown_proper_nouns(question, ds, catalog)
        _unknown_values += _metric_conflicts
        _unknown_values += _find_conflicting_conditions(question, ds)
        _yamb = _year_ambiguity(question, ds)
        if _yamb:
            _unknown_values.append("ambiguous_year:" + "|".join(map(str, _yamb)))
        _unknown_values += _find_negated_references(question, ds, catalog)
        _rel = getattr(ds, "rel", None)
        if _rel is not None:
            for _n, _c in bound_dims:
                _src = _rel.source(_c)
                if _src is None:
                    continue
                if _src.kind == "ambiguous":
                    _unknown_values.append(
                        f"ambiguous_join_path:{_c}=" + " | ".join(_src.candidates))
                elif _src.kind == "fanout":
                    _unknown_values.append(
                        f"fanout_dimension:{_c}=grouping by a one-to-many "
                        f"table would double-count the measure")
        _date_amb = _ambiguous_date_columns(question, ds, time_unit)
        if _date_amb:
            _unknown_values.append("ambiguous_date_column:" + "|".join(_date_amb))
        # When a value filter is present for a given dim AND that
        # same dim was bound as a grouping, remove the grouping (user
        # asked for a filtered single row, not a breakdown).
        if value_filters:
            # Build the set of SHORT dim nouns a value filter targets,
            # so we can match against the bound_dims noun column.
            _NOUNS = {
                "regions.region_name": {"region", "region_name"},
                "products.category":   {"category"},
                "products.sub_category": {"sub_category", "subcategory"},
                "products.product_name": {"product", "product_name"},
                "customers.segment":   {"segment"},
                "customers.customer_name": {"customer", "customer_name"},
            }
            vf_dim_nouns: set = set()
            for f in value_filters:
                if f.kind == "not_in":
                    continue            # "by state excluding X" still groups
                vf_dim_nouns |= _NOUNS.get(f.column, set())
                if ds.kind != "demo":
                    _base = _norm_words(f.column)
                    vf_dim_nouns |= {f.column, f.column.lower(), _base,
                                     _base.split(" ")[0]}
            _old_bound = list(bound_dims)
            bound_dims = [(n, c) for n, c in bound_dims
                           if not (n in vf_dim_nouns
                                    or c in vf_dim_nouns)]
            if bound_dims != _old_bound:
                _early_notes.append(
                    "value_filter_removed_redundant_breakdown=" +
                    ",".join(f"{n}:{c}" for n, c in _old_bound
                              if (n in vf_dim_nouns or c in vf_dim_nouns)))
                # If this leaves BREAKDOWN with no bound dims, demote
                # to DIRECT_KPI so the compiler emits a filtered scalar.
                if kind == IntentKind.BREAKDOWN and not bound_dims:
                    kind = IntentKind.DIRECT_KPI
        dims = [_dref(c, ds) for _, c in bound_dims]
        notes: List[str] = list(_early_notes)
        # Tag the plan when the time filter came from a relative-period
        # phrase (Defect B). The orchestrator reads this note so an
        # empty result on a relative-period filter becomes CLARIFY
        # instead of a quiet ANSWER with no rows.
        _rel = _find_relative_period(question)
        if _rel is not None:
            lo_y, lo_m, hi_y, hi_m, _kind_rel = _rel
            notes.append(
                f"relative_period={_kind_rel}:"
                f"{_period_string(lo_y, lo_m)}..{_period_string(hi_y, hi_m)}"
            )

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
            top_n = _parse_count_after(question.lower(), "top", default=5)
            if re.search(r"\bwhich\b", question.lower()) and top_n == 5 \
                    and not re.search(r"\btop\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b", question.lower()):
                top_n = 1
            order_by = "measure_desc"
            measures = _promote_by_measure(question, measures, catalog)

        elif kind == IntentKind.BOTTOM_N:
            top_n = _parse_count_after(question.lower(), "bottom", default=5)
            if re.search(r"\bwhich\b", question.lower()) and top_n == 5 \
                    and not re.search(r"\bbottom\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b", question.lower()):
                top_n = 1
            order_by = "measure_asc"
            measures = _promote_by_measure(question, measures, catalog)

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

        elif kind == IntentKind.DISTINCT_COUNT:
            hit = _find_distinct_count_dim(question, ds)
            if hit is not None:
                _noun, dim_col = hit
                # Use a synthetic measure whose formula is COUNT(DISTINCT ...).
                sel = dim_col
                if getattr(ds, "rel", None) is not None and \
                        ds.rel.source(dim_col) is not None:
                    sel = "{{dim:%s}}" % dim_col
                if ds.kind == "demo":
                    # Translate common tokens to the correct joined-table col.
                    _joined = {
                        "customer": "customers.customer_name",
                        "customer_name": "customers.customer_name",
                        "product": "products.product_name",
                        "product_name": "products.product_name",
                        "region": "regions.region_name",
                        "region_name": "regions.region_name",
                        "category": "products.category",
                        "sub_category": "products.sub_category",
                        "segment": "customers.segment",
                    }
                    sel = _joined.get(dim_col, dim_col)
                alias = f"distinct_{dim_col.replace('.', '_')}"
                measures = [MeasureRef(
                    kpi_id=alias,
                    display_name=f"Distinct {dim_col.replace('_', ' ').title()}",
                    formula=f"COUNT(DISTINCT {sel})",
                    aggregation="count_distinct", unit="count")]
                dims = []  # scalar

        elif kind == IntentKind.NULL_COUNT:
            null_col = _find_null_target_column(question, ds)
            if null_col:
                _formula, _label = "COUNT(*)", f"Rows with missing {null_col}"
                _agg = "count"
                _em = re.search(r"\bhow\s+many\s+([a-z_]+)", ql_lo)
                if _em and ds.kind != "demo":
                    _noun = _em.group(1)
                    _ecol = (_bind_dim_column(ds, _noun) or
                             (_bind_dim_column(ds, _noun[:-1])
                              if _noun.endswith("s") else None))
                    if _ecol and _ecol != null_col and \
                            _ecol in ds.columns:
                        _formula = f'COUNT(DISTINCT "{_ecol}")'
                        _label = (f"Distinct {_ecol} with missing "
                                  f"{null_col}")
                        _agg = "count_distinct"
                measures = [MeasureRef(
                    kpi_id=f"null_{null_col}",
                    display_name=_label,
                    formula=_formula,
                    aggregation=_agg, unit="count")]
                dims = []
                filters = [FilterExpr(kind="null", column=null_col)]

        elif kind == IntentKind.EXTREMUM:
            hit = _find_extremum(question, catalog, ds)
            if hit is not None:
                fn, label, col = hit
                measures = [MeasureRef(
                    kpi_id=f"{fn.lower()}_{col}",
                    display_name=f"{label.title()} {col.title()}",
                    formula=f"{fn}({col})",
                    aggregation=fn.lower(), unit="currency" if col != "quantity" else "count")]
                dims = []

        elif kind == IntentKind.ROLLING_AVG:
            window = _find_rolling_window(question) or 3
            if date_col:
                dims = [DimRef(column=date_col, display_name=date_col.title(),
                                is_time=True, time_unit="month")]
                grain = Grain(kind="time", time_unit="month",
                               time_column=date_col)
                # Fallback KPI to total_revenue if none bound.
                if not measures:
                    rev = catalog.get("total_revenue")
                    if rev:
                        measures = [_mref(rev)]
                # Store window in notes so the compiler reads it.
                notes.append(f"rolling_window={window}")
                order_by = "time_asc"

        elif kind == IntentKind.TOP_N_PER_GROUP:
            hit = _find_top_per_group(question, ds, catalog)
            if hit is not None:
                n, inner_col, part_col = hit
                dims = [DimRef(column=part_col,
                                display_name=part_col.replace("_", " ").title()),
                        DimRef(column=inner_col,
                                display_name=inner_col.replace("_", " ").title())]
                if not measures:
                    rev = catalog.get("total_revenue")
                    if rev:
                        measures = [_mref(rev)]
                top_n = n   # repurpose top_n to carry inner-group N
                order_by = "measure_desc"

        elif kind == IntentKind.POST_AGG_STAT:
            hit = _find_post_agg_stat(question)
            if hit is not None:
                stat, param, col = hit
                # The compiler emits SELECT col FROM ... [WHERE] which
                # the orchestrator reduces in Python using stats.<fn>.
                # Store the stat spec in plan.notes so the orchestrator
                # can read it back without a new field.
                param_str = f":{param}" if param is not None else ""
                notes.append(f"post_agg_stat={stat}{param_str}:{col}")
                alias = (f"{stat}_{col}" if param is None
                          else f"p{int(param)}_{col}")
                measures = [MeasureRef(
                    kpi_id=alias,
                    display_name=f"{stat.title()} of {col.title()}"
                                  + (f" (p{param})" if param is not None else ""),
                    formula=col,  # raw column; compiler pulls it as-is
                    aggregation=f"post_agg_{stat}",
                    unit="currency" if col in ("revenue", "cost", "discount")
                           else "count")]
                dims = []

        elif kind == IntentKind.THRESHOLD_GROUPED:
            hit = _find_threshold_grouped(question, ds, catalog)
            if hit is not None:
                dim_col, kpi_id, threshold, op = hit
                k = catalog.get(kpi_id)
                if k:
                    measures = [_mref(k)]
                # Dim: time-bucket sentinels resolve to date_col with a
                # time_unit; everything else is a plain dim column.
                if dim_col == "__month__":
                    dims = [DimRef(column=date_col, display_name="Month",
                                     is_time=True, time_unit="month")]
                    grain = Grain(kind="time", time_unit="month",
                                   time_column=date_col)
                elif dim_col == "__quarter__":
                    dims = [DimRef(column=date_col, display_name="Quarter",
                                     is_time=True, time_unit="quarter")]
                    grain = Grain(kind="time", time_unit="quarter",
                                   time_column=date_col)
                elif dim_col == "__year__":
                    dims = [DimRef(column=date_col, display_name="Year",
                                     is_time=True, time_unit="year")]
                    grain = Grain(kind="time", time_unit="year",
                                   time_column=date_col)
                else:
                    dims = [DimRef(column=dim_col,
                                     display_name=dim_col.replace("_", " ").title())]
                hv_kind = "metric_gt_grouped" if op == "gt" \
                           else "metric_lt_grouped"
                filters = filters + [FilterExpr(
                    kind=hv_kind, kpi_id=kpi_id, threshold=threshold)]
                order_by = "measure_desc"

        elif kind == IntentKind.RELATIVE_TO_STAT and rel_spec is not None:
            # measures come from the spec so the SELECT list matches
            k1 = catalog.get(rel_spec.measure_kpi_id)
            measures = [_mref(k1)] if k1 else []
            if rel_spec.and_measure_kpi_id:
                k2 = catalog.get(rel_spec.and_measure_kpi_id)
                if k2:
                    measures.append(_mref(k2))
            # dim is the entity we group by
            entity_info = ds.columns.get(rel_spec.entity_column)
            if entity_info is not None:
                dims = [DimRef(column=rel_spec.entity_column,
                                display_name=rel_spec.entity_column
                                             .replace("_", " ").title())]
            filters = [f for f in filters if f.kind != "metric_lt"]
            order_by = "measure_desc"

        # ---------- default order_by for breakdown ----------
        if kind == IntentKind.BREAKDOWN and not order_by:
            order_by = "measure_desc"

        # ---------- unavailable dims ----------
        unavailable: List[str] = [f"dimension:{n}" for n in unbound_dims]
        unavailable.extend(_unknown_values)
        if _dropped_suffix:
            notes.append(f"compound_question_dropped_suffix={_dropped_suffix!r}")

        return AnalyticalPlan(
            intent_kind=kind,
            measures=measures,
            dims=dims,
            filters=filters,
            grain=grain,
            comparison=comparison,
            contribution=contribution,
            relative_stat=(rel_spec if kind == IntentKind.RELATIVE_TO_STAT
                            else None),
            top_n=top_n,
            share_of_total=share,
            order_by=order_by,
            unavailable=unavailable,
            question=question,
            table=ds.table,
            notes=notes,
        )
