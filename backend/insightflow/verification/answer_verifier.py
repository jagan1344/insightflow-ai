"""Independent answer verification + sensitivity diagnostics.

Runs AFTER the main query. It never trusts the plan's own reading of the
question; it re-derives quantities the answer must satisfy using different
SQL shapes or invariants. Findings are of two kinds:

  violations   an invariant that must hold is broken -> the answer cannot be
               trusted (the orchestrator downgrades it)
  diagnostics  assumptions the result is sensitive to (join row loss, NULL
               measurements, time-boundary sensitivity). These are signals,
               not proof of an error.

Checks (each only when applicable):
  breakdown_reconciles   sum of groups == the same query without grouping
                         (catches rows dropped/duplicated by joins)
  avg_within_bounds      AVG lies between MIN and MAX of the column
  count_distinct_le_rows COUNT(DISTINCT x) <= COUNT(*)
  semijoin_equivalence   (multi-table) the join-based total equals an
                         EXISTS/semi-join formulation (no fan-out)
  null_measure_share     diagnostic: share of rows with NULL measure
  boundary_sensitivity   diagnostic: result moves a lot if the end of a
                         day-level time filter shifts by one day
"""
from __future__ import annotations

import copy
import re
import sqlite3
from dataclasses import dataclass, field
from typing import List, Optional

from ..plan.plan import AnalyticalPlan, IntentKind


@dataclass
class Finding:
    name: str
    severity: str            # violation | diagnostic | pass
    detail: str = ""


@dataclass
class VerificationReport:
    findings: List[Finding] = field(default_factory=list)

    @property
    def violations(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "violation"]

    @property
    def diagnostics(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "diagnostic"]

    @property
    def ok(self) -> bool:
        return not self.violations


def _scalar(con: sqlite3.Connection, sql: str):
    try:
        r = con.execute(sql).fetchone()
        return None if r is None else r[0]
    except sqlite3.Error:
        return None


def _close(a, b, tol=1e-6) -> bool:
    try:
        a, b = float(a or 0), float(b or 0)
    except (TypeError, ValueError):
        return True
    return abs(a - b) <= tol * max(abs(a), abs(b), 1.0)


def _as_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def verify(plan: AnalyticalPlan, sql: str, rows: List[tuple], ds, catalog,
           db_path: str) -> VerificationReport:
    rep = VerificationReport()
    if not sql or plan is None or not rows:
        return rep
    if plan.intent_kind not in (IntentKind.DIRECT_KPI, IntentKind.BREAKDOWN,
                                IntentKind.TREND, IntentKind.TOP_N,
                                IntentKind.DISTINCT_COUNT,
                                IntentKind.NULL_COUNT):
        return rep
    from ..plan.compiler import SQLCompiler
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return rep
    try:
        comp = SQLCompiler(ds, catalog)
        _breakdown_reconciles(rep, plan, rows, comp, con)
        _avg_bounds(rep, plan, rows, ds, con)
        _distinct_le_rows(rep, plan, rows, ds, con)
        _semijoin_equivalence(rep, plan, rows, ds, comp, con)
        _null_measure_share(rep, plan, ds, comp, con)
        _boundary_sensitivity(rep, plan, rows, comp, con)
    finally:
        con.close()
    return rep


# -- violations --------------------------------------------------------

def _additive(plan) -> bool:
    return bool(plan.measures) and all(
        m.aggregation in ("sum", "count") for m in plan.measures) \
        and not plan.top_n \
        and not any(f.kind.startswith("metric_") for f in plan.filters)


def _breakdown_reconciles(rep, plan, rows, comp, con) -> None:
    if not plan.dims or len(plan.measures) != 1 or not _additive(plan):
        return
    if len(rows) >= 1000:          # row-capped: groups incomplete
        return
    p2 = copy.deepcopy(plan)
    p2.dims = []; p2.grain = None; p2.order_by = ""; p2.top_n = None
    p2.intent_kind = IntentKind.DIRECT_KPI
    try:
        total_sql = comp.compile(p2)
    except Exception:
        return
    if not total_sql:
        return
    total = _scalar(con, total_sql)
    got = sum((_as_float(r[-1]) or 0.0) for r in rows)
    if _close(got, total):
        rep.findings.append(Finding("breakdown_reconciles", "pass",
                                    f"groups sum {got:.6g} == total {_as_float(total) or 0:.6g}"))
    else:
        rep.findings.append(Finding(
            "breakdown_reconciles", "violation",
            f"sum of groups {got:.6g} != ungrouped total "
            f"{_as_float(total) or 0:.6g}: rows were dropped or duplicated"))


def _avg_bounds(rep, plan, rows, ds, con) -> None:
    if plan.dims or len(plan.measures) != 1 or len(rows) != 1:
        return
    m = plan.measures[0]
    mm = re.fullmatch(r'AVG\("([^"]+)"\)', (m.formula or "").strip())
    if not mm or mm.group(1) not in ds.columns:
        return
    col = mm.group(1)
    lo = _scalar(con, f'SELECT MIN("{col}") FROM "{ds.table}"')
    hi = _scalar(con, f'SELECT MAX("{col}") FROM "{ds.table}"')
    v = _as_float(rows[0][-1])
    if v is None or lo is None or hi is None:
        return
    if v < lo - 1e-9 or v > hi + 1e-9:
        rep.findings.append(Finding(
            "avg_within_bounds", "violation",
            f"AVG {v:.6g} outside [{lo}, {hi}] of column {col}"))


def _distinct_le_rows(rep, plan, rows, ds, con) -> None:
    if plan.dims or len(plan.measures) != 1 or len(rows) != 1:
        return
    m = plan.measures[0]
    if m.aggregation != "count_distinct" or plan.filters:
        return
    v = _as_float(rows[0][-1])
    n = _scalar(con, f'SELECT COUNT(*) FROM "{ds.table}"')
    if v is not None and n is not None and v > n:
        rep.findings.append(Finding(
            "count_distinct_le_rows", "violation",
            f"COUNT(DISTINCT) {v:g} exceeds row count {n}"))


def _semijoin_equivalence(rep, plan, rows, ds, comp, con) -> None:
    """Multi-table scalar: re-express every filter on a joined table as an
    EXISTS semi-join and compare. A difference means the join multiplied
    or dropped anchor rows."""
    rel = getattr(ds, "rel", None)
    if rel is None or plan.dims or len(plan.measures) != 1 or len(rows) != 1:
        return
    if not _additive(plan) and plan.measures[0].aggregation not in ("avg", "min", "max"):
        return
    p2 = copy.deepcopy(plan)
    joined = [f for f in p2.filters if f.kind in ("eq", "in") and f.column
              and rel.source(f.column) is not None
              and rel.source(f.column).kind == "safe"]
    if not joined:
        return
    comp2 = type(comp)(ds, comp.catalog)
    comp2._joins = {}
    parts = []
    for f in joined:
        src = rel.source(f.column)
        # build correlated EXISTS along the many-to-one chain
        sql_ex = _exists_for_safe(rel, src, f)
        parts.append(sql_ex)
    keep = [f for f in p2.filters if f not in joined]
    p2.filters = keep
    base = comp2.compile(p2)
    if not base:
        return
    base = _inject_where(base, parts)
    alt = _scalar(con, base)
    got = _as_float(rows[0][-1])
    if got is None and alt is None:
        return
    if _close(got, alt):
        rep.findings.append(Finding("semijoin_equivalence", "pass",
                                    "join result == semi-join result"))
    else:
        rep.findings.append(Finding(
            "semijoin_equivalence", "violation",
            f"join-based {got} != semi-join {alt}: the joins changed the grain"))


def _exists_for_safe(rel, src, f) -> str:
    a = rel.anchor
    st = src.steps
    aliases = [f"v{i}" for i in range(len(st))]
    sql = f'SELECT 1 FROM "{st[0].edge.parent_table}" AS {aliases[0]}'
    for i in range(1, len(st)):
        e = st[i].edge
        sql += (f' JOIN "{e.parent_table}" AS {aliases[i]} ON '
                f'{aliases[i]}."{e.parent_col}" = {aliases[i-1]}."{e.child_col}"')
    e0 = st[0].edge
    def lit(v): return "'" + str(v).replace("'", "''") + "'"
    if f.kind == "eq":
        pred = f'{aliases[-1]}."{src.column}" = {lit(f.value)}'
    else:
        pred = f'{aliases[-1]}."{src.column}" IN (' + ", ".join(lit(v) for v in f.value) + ")"
    sql += f' WHERE {aliases[0]}."{e0.parent_col}" = "{a}"."{e0.child_col}" AND {pred}'
    return f"EXISTS ({sql})"


def _inject_where(sql: str, parts: List[str]) -> str:
    cond = " AND ".join(parts)
    if re.search(r"\bWHERE\b", sql, re.I):
        return re.sub(r"\bWHERE\b", f"WHERE {cond} AND", sql, count=1, flags=re.I)
    m = re.search(r"\b(GROUP BY|ORDER BY|LIMIT|HAVING)\b", sql, re.I)
    if m:
        return sql[:m.start()] + f"WHERE {cond} " + sql[m.start():]
    return sql + f" WHERE {cond}"


# -- diagnostics ---------------------------------------------------------

def _null_measure_share(rep, plan, ds, comp, con) -> None:
    for m in plan.measures:
        mm = re.fullmatch(r'(?:SUM|AVG)\("([^"]+)"\)', (m.formula or "").strip())
        if not mm or mm.group(1) not in ds.columns:
            continue
        col = mm.group(1)
        n = _scalar(con, f'SELECT COUNT(*) FROM "{ds.table}"') or 0
        nn = _scalar(con, f'SELECT COUNT(*) FROM "{ds.table}" WHERE "{col}" IS NULL') or 0
        if n and nn / n >= 0.05:
            rep.findings.append(Finding(
                "null_measure_share", "diagnostic",
                f"{nn}/{n} rows have no '{col}'; {m.aggregation.upper()} ignores them"))


def _boundary_sensitivity(rep, plan, rows, comp, con) -> None:
    if plan.dims or len(rows) != 1 or len(plan.measures) != 1:
        return
    tf = [f for f in plan.filters if f.kind == "time_range" and f.column
          and len(str(f.hi)) >= 10]
    if not tf:
        return
    import datetime as dt
    try:                      # a deliberately narrow window (a single day) is not "sensitive"
        if any((dt.date.fromisoformat(str(f.hi)[:10]) -
                dt.date.fromisoformat(str(f.lo)[:10])).days <= 7 for f in tf):
            return
    except ValueError:
        return
    p2 = copy.deepcopy(plan)
    for f in p2.filters:
        if f.kind == "time_range" and len(str(f.hi)) >= 10:
            try:
                d = dt.date.fromisoformat(str(f.hi)[:10]) + dt.timedelta(days=1)
            except ValueError:
                return
            f.hi = d.isoformat()
    sql2 = comp.compile(p2)
    alt = _scalar(con, sql2) if sql2 else None
    got = _as_float(rows[0][-1]); altf = _as_float(alt)
    if got and altf is not None and abs(altf - got) / max(abs(got), 1e-9) > 0.25:
        rep.findings.append(Finding(
            "boundary_sensitivity", "diagnostic",
            f"shifting the filter end by one day changes the result {got:.6g} -> {altf:.6g}"))
