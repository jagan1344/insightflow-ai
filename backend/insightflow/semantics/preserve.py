"""Semantic-preservation verification: does the EXECUTED query, its rows and
the written answer still carry every constraint of the SemanticSpec?

Heuristic text analysis of SQL (no SQL parser dependency); each finding names
the missing/contradicting element. Findings are violations unless severity
says otherwise."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


@dataclass
class SemanticFinding:
    rule: str
    detail: str
    severity: str = "violation"


F = SemanticFinding
_AGG_FN = {"sum": "SUM", "avg": "AVG", "min": "MIN", "max": "MAX",
           "count": "COUNT", "count_distinct": "COUNT"}


def _phys(ds, col: str) -> str:
    rel = getattr(ds, "rel", None)
    s = rel.source(col) if rel is not None else None
    return s.column if s is not None else col


def _strip_exists(sql: str) -> str:
    out, i = [], 0
    pat = re.compile(r"\bEXISTS\s*\(", re.I)
    while True:
        m = pat.search(sql, i)
        if not m:
            out.append(sql[i:]); break
        out.append(sql[i:m.start()] + "EXISTS_SEMI")
        depth, j = 1, m.end()
        while j < len(sql) and depth:
            depth += (sql[j] == "(") - (sql[j] == ")")
            j += 1
        i = j
    return "".join(out)


def _nums(text: str) -> List[float]:
    out = []
    for m in re.finditer(r"(-?\d[\d,]*\.?\d*)\s*([kKmMbB]\b)?", text):
        raw = m.group(1).replace(",", "").rstrip(".")
        try:
            v = float(raw)
        except ValueError:
            continue
        v *= {"k": 1e3, "m": 1e6, "b": 1e9}.get((m.group(2) or "").lower(), 1)
        out.append(v)
    return out


def preserve(spec, sql: str, columns: list, rows: list, explanation: str, ds) -> List[F]:
    out: List[F] = []
    if not sql:
        return out
    s = re.sub(r"\s+", " ", sql)
    sl = s.lower()
    outer = _strip_exists(s)
    outer_l = outer.lower()

    # ---- measures and aggregation functions --------------------------------
    calls = [(m.group(1).upper(), bool(m.group(2)), m.group(3).lower())
             for m in re.finditer(r"\b(SUM|AVG|COUNT|MIN|MAX)\s*\(\s*(DISTINCT\s+)?([^()]*(?:\([^()]*\)[^()]*)*)\)", s, re.I)]
    for mt in spec.metrics:
        agg = mt.aggregation
        if agg in _AGG_FN:
            fn = _AGG_FN[agg]
            want_cols = [_phys(ds, g.column).lower() for g in mt.columns]
            ok = False
            for f, dist, arg in calls:
                if f != fn:
                    continue
                if fn == "COUNT" and (agg == "count_distinct") != dist:
                    continue
                if fn == "COUNT" and not want_cols:
                    ok = True            # COUNT(*)
                elif all(c in arg for c in want_cols):
                    ok = True
            if not ok:
                out.append(F("measure_not_preserved",
                             f"'{mt.display}' needs {fn}{'(DISTINCT ...)' if agg == 'count_distinct' else ''}"
                             f"({', '.join(want_cols) or '*'}) but the query does not compute it"))
        elif agg in ("ratio", "derived"):
            miss = [g.column for g in mt.columns if _phys(ds, g.column).lower() not in sl]
            if miss:
                out.append(F("measure_not_preserved", f"columns {miss} of '{mt.display}' are absent from the query"))

    # ---- filters ---------------------------------------------------------------
    for f in spec.filters:
        col = _phys(ds, f.column).lower()
        if f.kind in ("value", "flag", "exclusion"):
            if col not in sl:
                out.append(F("filter_not_preserved", f"filter on '{f.column}' is missing"))
                continue
            for v in f.values:
                lit = str(v).replace("'", "''")
                if lit not in s:
                    out.append(F("filter_not_preserved", f"value '{v}' of '{f.column}' is not in the query"))
            if f.kind == "exclusion" and not re.search(r"NOT\s+IN|<>|!=|NOT\s+EXISTS", s, re.I):
                out.append(F("exclusion_not_preserved", f"exclusion on '{f.column}' lost its negation"))
        elif f.kind == "numeric":
            for v in f.values:
                if not isinstance(v, tuple) and not re.search(rf"(?<![\d.]){re.escape(str(v))}(?:\.0+)?(?![\d])", s):
                    out.append(F("filter_not_preserved", f"threshold {v} on '{f.column}' is missing"))
        elif f.kind == "null_state":
            want = "IS NULL" if f.op == "null" else "IS NOT NULL"
            if not re.search(rf"{re.escape(col)}\"?\s+{want}", s, re.I):
                out.append(F("filter_not_preserved", f"'{f.column}' {want} is missing"))
        elif f.kind == "exists":
            if "exists" not in sl:
                out.append(F("filter_not_preserved", f"existence test on '{f.column}' is missing"))
    if spec.time is not None:
        for b, is_hi in ((str(spec.time.lo), False), (str(spec.time.hi), True)):
            if len(b) >= 10:
                probe = b                      # day-level bound, used as-is
            elif is_hi:
                probe = _next_month(b) + "-"   # month-level end is inclusive: SQL uses the next month's 1st
            else:
                probe = b + "-"
            if b and probe not in s:
                out.append(F("time_not_preserved", f"time bound {b} is missing from the query"))
                break

    # ---- grouping, ranking ------------------------------------------------------
    gm = re.search(r"GROUP BY (.*?)(?: HAVING | ORDER BY | LIMIT |$)", s, re.I)
    gtxt = (gm.group(1).lower() if gm else "")
    for d in spec.dims:
        if _phys(ds, d.column).lower() not in gtxt:
            out.append(F("grouping_not_preserved", f"'{d.column}' is not in GROUP BY"))
    if spec.limit and not re.search(rf"LIMIT\s+{spec.limit}\b", s, re.I) and "row_number" not in sl:
        out.append(F("ranking_not_preserved", f"top-{spec.limit} was not applied"))

    # ---- joins / fan-out --------------------------------------------------------
    allowed = {j.table.lower() for j in spec.joins if not j.semi}
    if getattr(ds, "rel", None) is not None:
        for t in re.findall(r"\bJOIN\s+\"?(\w+)\"?", outer, re.I):
            if t.lower() not in allowed and not _is_hop(spec, ds, t):
                out.append(F("unplanned_join", f"query joins '{t}' which the question does not need"))
    for j in spec.joins:
        if j.semi and re.search(rf"\bJOIN\s+\"?{re.escape(j.table)}\"?\b", outer, re.I):
            out.append(F("fanout_join", f"one-to-many table '{j.table}' is joined directly and would multiply rows"))

    # ---- row shape --------------------------------------------------------------
    simple = spec.intent in ("direct_kpi", "breakdown", "top_n", "trend")
    if simple and not spec.share:
        exp_cols = len(spec.dims) + spec.n_time_dims + len(spec.metrics)
        if columns and len(columns) != exp_cols:
            out.append(F("unexpected_columns",
                         f"{len(columns)} columns returned, {exp_cols} expected "
                         f"({len(spec.dims) + spec.n_time_dims} label + {len(spec.metrics)} measure)"))
        if spec.shape == "scalar" and len(rows) > 1:
            out.append(F("shape_violation", f"a single figure was expected but {len(rows)} rows were returned"))
        if spec.shape in ("grouped", "trend", "ranking") and len(rows) == 1 and len(columns) == len(spec.metrics) \
                and spec.dims:
            out.append(F("shape_violation", "a breakdown was expected but a single figure was returned"))
        if spec.limit and len(rows) > spec.limit:
            out.append(F("shape_violation", f"{len(rows)} rows returned for top-{spec.limit}"))

        # ---- the written answer must report what was executed ----------------
        parts = explanation.split("\n\n")
        body = parts[1] if len(parts) > 1 else ""
        body = body.split("Caveats:")[0]
        if body and rows:
            allowed_n: List[float] = [float(len(rows))]
            if spec.limit:
                allowed_n.append(float(spec.limit))
            for r in rows:
                for c in r:
                    if isinstance(c, (int, float)) and not isinstance(c, bool):
                        allowed_n.append(float(c))
                    elif isinstance(c, str):
                        allowed_n += _nums(c)
            allowed_n += _nums(spec.question)
            if spec.time is not None:
                allowed_n += [float(x) for x in re.findall(r"\d+", f"{spec.time.lo} {spec.time.hi}")]
            allowed_n += [float(len(rows)), float(len(spec.dims))]
            for n in _nums(body):
                if not any(abs(n - a) <= max(0.011, 0.006 * abs(a)) for a in allowed_n):
                    out.append(F("answer_not_faithful",
                                 f"the written answer states {n:g}, which is not in the executed result"))
                    break
    return out


def _next_month(period: str) -> str:
    try:
        y, m = (int(x) for x in period.split("-")[:2])
    except ValueError:
        return period
    return f"{y + (m == 12):04d}-{(m % 12) + 1:02d}"


def _is_hop(spec, ds, table: str) -> bool:
    rel = getattr(ds, "rel", None)
    if rel is None:
        return False
    t = table.lower()
    for j in spec.joins:
        if j.semi:
            continue
        for src in rel.sources.values():
            if src.table.lower() == j.table.lower():
                if any(st.edge.parent_table.lower() == t for st in src.steps):
                    return True
    return False
