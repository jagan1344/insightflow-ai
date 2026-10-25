"""Typed intermediate representation of WHAT WAS ASKED, derived from the
analytical plan and grounded in the discovered schema.

Every column in the spec is looked up in the active dataset (anchor columns,
related-table sources from the relationship graph, or governed metric
expressions). A reference that cannot be grounded is recorded as unresolved,
never invented. The spec is deliberately independent of the SQL text so that
it can be compared against it afterwards (see preserve.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional

_MONEY = ("amount", "price", "fee", "revenue", "sales", "cost", "salary", "bonus",
          "balance", "tuition", "freight", "usd", "eur", "profit", "discount",
          "income", "spend", "payment", "charge")
_QTY = ("qty", "quantity", "units", "hours", "weight", "count", "volume", "kg")

_SCALAR_Q = re.compile(
    r"^\s*(?:what\s+(?:is|was|are|were)\s+(?:the\s+)?|how\s+many\s+|how\s+much\s+|"
    r"total\s+|sum\s+of\s+|number\s+of\s+|count\s+of\s+|average\s+|avg\s+|mean\s+|"
    r"maximum\s+|minimum\s+|max\s+|min\s+)")
_GROUP_Q = re.compile(
    r"\b(per|each|every|across|breakdown|broken\s+down|split|grouped?\s+by|"
    r"distribution)\b|\bby\s+(?!the\s)[a-z_]+")
_RANK_Q = re.compile(r"\b(top|bottom)\s+\d+\b|\bwhich\b|\b(highest|lowest|most|least|best|worst)\b")
_TREND_Q = re.compile(r"\b(trend|over\s+time|monthly|weekly|daily|quarterly|yearly|annually|rolling|moving)\b")
_CMP_Q = re.compile(r"\b(compare|compared|versus|vs\.?|growth|change|decline|drop)\b")
_AGENT = re.compile(r"\bby\s+[a-z_\-]+(?:\s+[a-z_\-]+)?\s+(?:from|with|who|whose|living|based|born|located)\b")


def requested_shape(question: str, ds=None) -> str:
    """Output shape the WORDING asks for, independent of the plan:
    scalar | grouped | ranking | comparison | trend | unspecified. Known data values are
    masked first ("insured by Medicaid" is a filter, not a grouping)."""
    q = question.lower()
    if ds is not None and getattr(ds, "kind", "demo") != "demo":
        try:
            from ..plan.planner import _value_index, _value_mentions
            for lo, _c in _value_mentions(question, _value_index(ds)):
                q = q.replace(lo, " ")
        except Exception:
            pass
    q = _AGENT.sub(" ", q)
    if _CMP_Q.search(q):
        return "comparison"
    if _TREND_Q.search(q):
        return "trend"
    if _RANK_Q.search(q):
        return "ranking"
    if _GROUP_Q.search(q):
        return "grouped"
    # only an explicit "what is / how many / total ..." opening promises ONE figure
    return "scalar" if _SCALAR_Q.search(q) else "unspecified"


@dataclass
class Grounded:
    column: str
    table: str = ""
    origin: str = "anchor"          # anchor | related | governed | synthetic | ungrounded
    sql_type: str = ""
    semantic_type: str = "other"    # money | quantity | flag | id | date | category | other


@dataclass
class MetricSpec:
    kpi_id: str
    display: str
    aggregation: str
    unit: str = ""
    columns: List[Grounded] = field(default_factory=list)
    expression: str = ""


@dataclass
class FilterSpec:
    kind: str                       # value | exclusion | numeric | null_state | exists | flag | having
    column: str
    table: str = ""
    polarity: str = "include"       # include | exclude
    op: str = "="
    values: list = field(default_factory=list)
    origin: str = "anchor"


@dataclass
class TimeSpec:
    column: str
    table: str
    lo: str
    hi: str
    role_basis: str                 # named | governed | unique | default_anchor | guessed


@dataclass
class JoinSpec:
    table: str
    via: str
    safe: bool
    nullable: bool
    semi: bool                      # fan-out table reached only through EXISTS


@dataclass
class SemanticSpec:
    question: str
    intent: str
    requested_shape: str
    shape: str
    metrics: List[MetricSpec] = field(default_factory=list)
    dims: List[Grounded] = field(default_factory=list)
    filters: List[FilterSpec] = field(default_factory=list)
    time: Optional[TimeSpec] = None
    limit: Optional[int] = None
    joins: List[JoinSpec] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)
    unsupported: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    n_time_dims: int = 0
    share: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def _sem_type(ds, column: str, info, unit: str) -> str:
    low = column.lower()
    if column in (getattr(ds, "flag_columns", ()) or ()):
        return "flag"
    role = getattr(info, "role", "") if info is not None else ""
    if role == "id":
        return "id"
    if role == "date":
        return "date"
    if role == "dimension":
        return "category"
    if unit == "currency" or any(t in low for t in _MONEY):
        return "money"
    if any(t in low for t in _QTY):
        return "quantity"
    return "other"


def _ground(ds, column: str, unit: str = "") -> Grounded:
    rel = getattr(ds, "rel", None)
    src = rel.source(column) if rel is not None else None
    info = ds.columns.get(column)
    if src is not None:
        return Grounded(column, src.table, "related", "REAL" if src.numeric else "TEXT",
                        _sem_type(ds, column, info, unit))
    if info is not None:
        return Grounded(column, ds.table, "anchor", info.sql_type, _sem_type(ds, column, info, unit))
    return Grounded(column, "", "ungrounded", "", "other")


def _formula_columns(formula: str) -> List[str]:
    cols = re.findall(r"\{\{dim:([^}]+)\}\}", formula or "")
    cols += re.findall(r'"([^"]+)"', re.sub(r"\{\{dim:[^}]+\}\}", "", formula or ""))
    return list(dict.fromkeys(cols))


def build_spec(question: str, plan, ds, catalog=None) -> SemanticSpec:
    from ..plan.plan import IntentKind
    rel = getattr(ds, "rel", None)
    ik = plan.intent_kind
    if ik in (IntentKind.COMPARISON, IntentKind.GROWTH, IntentKind.CONTRIBUTION):
        shape = "comparison"
    elif ik == IntentKind.TREND or any(d.is_time for d in plan.dims):
        shape = "trend"
    elif plan.top_n or ik in (IntentKind.TOP_N, IntentKind.TOP_N_PER_GROUP):
        shape = "ranking"
    elif plan.dims or plan.share_of_total:
        shape = "grouped"
    else:
        shape = "scalar"
    spec = SemanticSpec(question=question, intent=ik, requested_shape=requested_shape(question, ds),
                        shape=shape, limit=plan.top_n,
                        n_time_dims=sum(1 for d in plan.dims if d.is_time),
                        share=bool(plan.share_of_total))

    for m in plan.measures:
        cols = [_ground(ds, c, m.unit) for c in _formula_columns(m.formula)]
        spec.metrics.append(MetricSpec(m.kpi_id, m.display_name or m.kpi_id,
                                       (m.aggregation or "").lower(), m.unit, cols, m.formula))
    for d in plan.dims:
        if not d.is_time:
            spec.dims.append(_ground(ds, d.column))

    for f in plan.filters:
        col = f.column
        g = _ground(ds, col) if col else None
        tbl = g.table if g else ""
        org = g.origin if g else "anchor"
        if f.kind == "time_range":
            spec.time = TimeSpec(col, tbl, str(f.lo), str(f.hi), _time_basis(question, col, ds))
        elif f.kind in ("eq", "in"):
            kind = "flag" if col in (getattr(ds, "flag_columns", ()) or ()) else "value"
            vals = list(f.value) if isinstance(f.value, (list, tuple)) else [f.value]
            spec.filters.append(FilterSpec(kind, col, tbl, "include", "=" if len(vals) == 1 else "in", vals, org))
        elif f.kind == "not_in":
            spec.filters.append(FilterSpec("exclusion", col, tbl, "exclude", "not in", list(f.value), org))
        elif f.kind in ("cmp", "range"):
            spec.filters.append(FilterSpec("numeric", col, tbl, "include",
                                           f.op or "between", [f.value if f.kind == "cmp" else (f.lo, f.hi)], org))
        elif f.kind in ("null", "not_null"):
            spec.filters.append(FilterSpec("null_state", col, tbl, "exclude" if f.kind == "null" else "include",
                                           f.kind, [], org))
        elif f.kind in ("has_related", "no_related"):
            spec.filters.append(FilterSpec("exists", col, tbl, "include" if f.kind == "has_related" else "exclude",
                                           f.kind, [], org))
        elif f.kind.startswith("metric_"):
            spec.filters.append(FilterSpec("having", f.kpi_id, "", "include", f.kind, [f.threshold]))

    if rel is not None:
        seen = set()
        cols = [g.column for mt in spec.metrics for g in mt.columns] + \
               [d.column for d in spec.dims] + [f.column for f in spec.filters] + \
               ([spec.time.column] if spec.time else [])
        for c in cols:
            s = rel.source(c)
            if s is None or s.table in seen:
                continue
            seen.add(s.table)
            via = " -> ".join(f"{st.edge.child_table}.{st.edge.child_col}" for st in s.steps)
            spec.joins.append(JoinSpec(s.table, via, s.kind == "safe",
                                       bool(s.nullable), s.kind == "fanout"))
        for mt in spec.metrics:
            if any(g.origin == "related" for g in mt.columns):
                spec.assumptions.append(
                    f"'{mt.display}' is a related-table measure counted once per {ds.table} row")
    spec.unresolved = list(plan.unavailable)
    for mt in spec.metrics:
        for g in mt.columns:
            if g.origin == "ungrounded":
                spec.unresolved.append(f"ungrounded_column:{g.column}")
    for d in spec.dims:
        if d.origin == "ungrounded":
            spec.unresolved.append(f"ungrounded_column:{d.column}")
    return spec


def _time_basis(question: str, column: str, ds) -> str:
    from ..plan.planner import _mentioned_date_col
    rel = getattr(ds, "rel", None)
    if getattr(ds, "date_choice", None) == column:
        return "governed"
    if len(ds.dates) <= 1:
        return "unique"
    if _mentioned_date_col(question, ds) == column:
        return "named"
    own = [d for d in ds.dates if rel is None or rel.source(d) is None]
    if len(own) == 1 and own[0] == column:
        return "default_anchor"
    return "guessed"
