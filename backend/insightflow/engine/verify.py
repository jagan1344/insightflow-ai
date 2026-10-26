"""Verify a typed Query against the schema model before any SQL is generated."""
from __future__ import annotations

from typing import List

from .ir import Agg, Arith, BoolOp, Cmp, Col, Exists, InSet, IsNull, Lit, Not, Query
from .schema_model import SchemaModel, ordinal

AGG_KINDS = {"sum": {"measure"}, "avg": {"measure"}, "min": {"measure", "date"}, "max": {"measure", "date"},
             "count_distinct": {"id", "category", "text", "measure", "date", "boolean"}, "count": {"id", "category", "text", "measure", "date", "boolean"}}


def verify(q: Query, m: SchemaModel) -> List[str]:
    """Returns violations (empty = the plan may be compiled)."""
    v: List[str] = []
    if not q.measures:
        v.append("no measure")

    def kind(c: Col) -> str:
        return m.col(c.table, c.column).kind

    def expr(x, inside_exists=False):
        if isinstance(x, Col):
            if x.path is not None and x.path.fans_out and not inside_exists:
                v.append(f"{x.table}.{x.column} is on a one-to-many path; using it outside EXISTS would multiply rows")
        elif isinstance(x, Agg):
            if x.arg is not None:
                if isinstance(x.arg, Col) and kind(x.arg) not in AGG_KINDS.get(x.func, set()):
                    v.append(f"{x.func.upper()} is not valid for {x.arg.column} ({kind(x.arg)})")
                if isinstance(x.arg, Arith):
                    for side in (x.arg.left, x.arg.right):
                        if isinstance(side, Col) and kind(side) != "measure":
                            v.append(f"{side.column} ({kind(side)}) is not numeric")
                expr(x.arg)
            elif x.func != "count":
                v.append(f"{x.func} needs an argument")
            if x.where is not None:
                pred(x.where)
        elif isinstance(x, Arith):
            expr(x.left); expr(x.right)

    def pred(p, inside_exists=False):
        if isinstance(p, Cmp):
            k = kind(p.col)
            if p.op in (">", ">=", "<", "<=") and k not in ("measure", "date"):
                v.append(f"ordered comparison on {p.col.column} ({k})")
            if k == "date" and not isinstance(p.value.value, str):
                v.append(f"date column {p.col.column} compared with a number")
            if not inside_exists:
                expr(p.col)
        elif isinstance(p, (InSet, IsNull)):
            if not inside_exists:
                expr(p.col)
        elif isinstance(p, BoolOp):
            for i in p.items:
                pred(i, inside_exists)
        elif isinstance(p, Not):
            pred(p.item, inside_exists)
        elif isinstance(p, Exists):
            if not p.path.fans_out:
                v.append(f"EXISTS over a many-to-one path {p.path.describe()}")
            if p.pred is not None:
                pred(p.pred, True)

    for mm in q.measures:
        expr(mm.expr)
    for f in q.filters:
        pred(f)
    for g in q.group_by:
        expr(g)
        if kind(g) == "measure" and not ordinal(m.col(g.table, g.column)):
            v.append(f"grouping by the numeric column {g.column}")
    if q.time_bucket and kind(q.time_bucket[0]) != "date":
        v.append(f"time series over the non-date column {q.time_bucket[0].column}")
    if q.share_of_total and not (q.group_by or q.time_bucket):
        v.append("share of total without groups")
    if q.limit and not (q.group_by or q.time_bucket):
        v.append("ranking without a grouping")
    return v
