"""Adaptive clarification: ask only when the ambiguity changes the answer.

For each resolvable ambiguity (several date columns, several equally short
join paths) every candidate interpretation is planned, compiled and
executed read-only. Then:

  * all candidates give the same result  -> the ambiguity is immaterial:
    answer with the first interpretation (and say so); no question asked
  * results differ -> ask ONE targeted question that lists each option
    with the value it would produce, so the user can choose informedly

Only the first ambiguity item is expanded (one question at a time); the
rest of the plan (filters, measure, dims) is preserved because candidates
are produced by re-planning the SAME question with one choice fixed.
"""
from __future__ import annotations

import copy
import re
import sqlite3
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from ..plan.planner import Planner
from ..plan.compiler import SQLCompiler


@dataclass
class Candidate:
    label: str
    ds: object
    sql: str
    rows: List[tuple]


@dataclass
class Resolution:
    kind: str                       # "equivalent" | "clarify" | "none"
    candidates: List[Candidate] = field(default_factory=list)
    prompt: str = ""
    ambiguity: str = ""


def _run(db_path: str, sql: str, limit: int = 200) -> Optional[List[tuple]]:
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            return [tuple(r) for r in con.execute(sql).fetchmany(limit)]
        finally:
            con.close()
    except sqlite3.Error:
        return None


def _norm(rows: List[tuple]):
    out = []
    for r in rows:
        out.append(tuple(round(v, 6) if isinstance(v, float) else v for v in r))
    return sorted(out, key=repr)


def _same(a: List[tuple], b: List[tuple]) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(_norm(a), _norm(b)):
        if len(x) != len(y):
            return False
        for u, v in zip(x, y):
            if isinstance(u, float) or isinstance(v, float):
                try:
                    if abs(float(u) - float(v)) > 1e-6 * max(abs(float(u)), abs(float(v)), 1.0):
                        return False
                except (TypeError, ValueError):
                    return False
            elif u != v:
                return False
    return True


def _date_variants(ds, cols: List[str]):
    for c in cols:
        d2 = copy.copy(ds)
        reordered = {c: ds.columns[c]}
        reordered.update({k: v for k, v in ds.columns.items() if k != c})
        d2.columns = reordered
        d2.date_choice = c
        yield f"by {c}", d2


def _path_variants(ds, flat: str):
    from ..knowledge.rel_context import DimSource, RelContext
    rel = ds.rel
    src = rel.sources[flat]
    res = rel.schema.resolve(rel.anchor, src.table)
    for p in res.paths:
        rel2 = copy.copy(rel)
        rel2.sources = dict(rel.sources)
        for fl, s in rel.sources.items():
            if s.table == src.table and s.kind == "ambiguous":
                rel2.sources[fl] = DimSource(
                    fl, s.table, s.column, "safe", p.steps, p.nullable)
        d2 = copy.copy(ds)
        d2.rel = rel2
        yield "via " + p.describe(), d2


def _alt_variants(ds, flat: str):
    """The path the planner chose, plus each longer safe alternative."""
    from ..knowledge.rel_context import DimSource
    rel = ds.rel
    src = rel.sources[flat]
    yield "via " + " -> ".join(
        f"{s.edge.child_table}.{s.edge.child_col}" for s in src.steps), ds
    for alt in src.alt_paths:
        rel2 = copy.copy(rel)
        rel2.sources = dict(rel.sources)
        for fl, s in rel.sources.items():
            if s.table == src.table and s.kind == "safe":
                rel2.sources[fl] = DimSource(
                    fl, s.table, s.column, "safe", alt.steps, alt.nullable,
                    numeric=s.numeric, date=s.date)
        d2 = copy.copy(ds)
        d2.rel = rel2
        yield "via " + alt.describe(), d2


def resolve(question: str, unavailable: List[str], ds, catalog,
            db_path: str) -> Resolution:
    amb = next((u for u in unavailable
                if u.startswith(("ambiguous_date_column:",
                                 "ambiguous_join_path:",
                                 "alternative_path:"))), None)
    if amb is None:
        return Resolution("none")
    others = [u for u in unavailable if u != amb and not u.startswith(
        ("ambiguous_date_column:", "ambiguous_join_path:", "alternative_path:"))]
    if others:
        return Resolution("none")            # something else is unanswerable
    variants = []
    if amb.startswith("alternative_path:"):
        flat = amb.split(":", 1)[1]
        if getattr(ds, "rel", None) is None or flat not in ds.rel.sources:
            return Resolution("none")
        variants = list(_alt_variants(ds, flat))
    elif amb.startswith("ambiguous_date_column:"):
        variants = list(_date_variants(ds, amb.split(":", 1)[1].split("|")))
    else:
        flat = _flat_from(amb, ds)
        if flat is None or getattr(ds, "rel", None) is None:
            return Resolution("none")
        variants = list(_path_variants(ds, flat))
    cands: List[Candidate] = []
    for label, d2 in variants:
        plan = Planner(d2, catalog).plan(question)
        left = [u for u in plan.unavailable
                if u.startswith(("ambiguous_date_column:", "ambiguous_join_path:",
                                 "alternative_path:"))]
        if left or not plan.is_answerable():
            continue
        sql = SQLCompiler(d2, catalog).compile(plan)
        if not sql:
            continue
        rows = _run(db_path, sql)
        if rows is None:
            continue
        cands.append(Candidate(label, d2, sql, rows))
    if len(cands) < 2:
        return Resolution("none")
    if all(_same(cands[0].rows, c.rows) for c in cands[1:]):
        return Resolution("equivalent", cands, ambiguity=amb)
    opts = "; ".join(f"{c.label} -> {_brief(c.rows)}" for c in cands)
    return Resolution(
        "clarify", cands, ambiguity=amb,
        prompt=("This question can be read more than one way and the answer "
                f"depends on it: {opts}. Which did you mean?"))


def _brief(rows: List[tuple]) -> str:
    if not rows:
        return "no rows"
    def f(v):
        return f"{v:,.2f}" if isinstance(v, float) else str(v)
    if len(rows) == 1:
        return f(rows[0][-1])
    shown = ", ".join(f"{f(r[0])}: {f(r[-1])}" for r in rows[:6])
    return f"{len(rows)} groups ({shown}{', ...' if len(rows) > 6 else ''})"


def _flat_from(amb: str, ds) -> Optional[str]:
    # "ambiguous_join_path:<value-or-col>=..." -> find the ambiguous flat col
    key = amb.split(":", 1)[1].split("=", 1)[0].lower()
    rel = ds.rel
    for flat, s in rel.sources.items():
        if s.kind == "ambiguous" and flat.lower() == key:
            return flat
    # value mention: locate the column that holds this value
    for flat, s in rel.sources.items():
        if s.kind != "ambiguous":
            continue
        try:
            con = sqlite3.connect(f"file:{ds_db_path()}?mode=ro", uri=True)
            hit = con.execute(
                f'SELECT 1 FROM "{s.table}" WHERE lower("{s.column}")=? LIMIT 1',
                (key,)).fetchone()
            con.close()
            if hit:
                return flat
        except sqlite3.Error:
            pass
    return None


def ds_db_path() -> str:
    from ..config import settings
    u = settings.database_url
    return u.split(":///", 1)[1] if ":///" in u else u


def weak_value_check(question: str, plan, ds, catalog, db_path: str):
    """A categorical value that is also an ordinary participle/adjective
    ("held" vs status='Held') written in lower case: run the question with
    and without that filter; ask only if the answers differ."""
    cands = []
    for f in plan.filters:
        if f.kind == "eq" and isinstance(f.value, str) and " " not in f.value.strip():
            lo = f.value.lower()
            from ..reliability.mention_coverage import _IRREGULAR_PAST, _FUNCTION_WORDS
            if (re.search(r"(ed|ing)$", lo) or lo in _IRREGULAR_PAST or lo in _FUNCTION_WORDS) \
                    and re.search(rf"\b{re.escape(lo)}\b", question) \
                    and not re.search(rf"\b{re.escape(f.value)}\b", question):
                cands.append(f)
    if not cands:
        return None
    f0 = cands[0]
    p2 = copy.deepcopy(plan)
    p2.filters = [f for f in p2.filters if f is not f0 and not (f.kind == f0.kind and f.column == f0.column and f.value == f0.value)]
    comp = SQLCompiler(ds, catalog)
    sql1, sql2 = comp.compile(plan), SQLCompiler(ds, catalog).compile(p2)
    if not sql1 or not sql2:
        return None
    r1, r2 = _run(db_path, sql1), _run(db_path, sql2)
    if r1 is None or r2 is None or _same(r1, r2):
        return None
    return Resolution(
        "clarify", [Candidate(f"'{f0.value}' as the value of {f0.column}", ds, sql1, r1),
                    Candidate(f"'{f0.value.lower()}' as ordinary wording", ds, sql2, r2)],
        ambiguity=f"weak_value:{f0.column}",
        prompt=(f"'{f0.value.lower()}' could mean the value '{f0.value}' of {f0.column} "
                f"-> {_brief(r1)}, or just ordinary wording -> {_brief(r2)}. Which did you mean?"))
