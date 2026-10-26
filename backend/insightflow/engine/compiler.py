"""Compile a verified Query into read-only, parameterised SQLite SQL.

Joins: many-to-one columns are reached with LEFT JOINs along their recorded path (cannot multiply rows);
one-to-many conditions only appear inside EXISTS / NOT EXISTS (cannot multiply rows). A column on a
one-to-many path outside EXISTS is refused (the verifier rejects it first). Identifiers are checked
against the schema model; literals are bound as parameters; divisions are NULLIF-guarded."""
from __future__ import annotations

from typing import Dict, List, Tuple

from .ir import Agg, Arith, BoolOp, Cmp, Col, Exists, InSet, IsNull, Lit, Not, Query
from .schema_model import Path, SchemaModel


class CompileError(Exception):
    pass


def _qi(name: str) -> str:
    if '"' in name or "\x00" in name:
        raise CompileError(f"invalid identifier {name!r}")
    return f'"{name}"'


_BUCKET = {
    "month": "substr({c},1,7)", "year": "substr({c},1,4)", "day": "substr({c},1,10)",
    "quarter": "substr({c},1,4) || '-Q' || ((CAST(substr({c},6,2) AS INTEGER) + 2) / 3)",
    "week": "strftime('%Y-W%W', {c})",
}


class Compiler:
    def __init__(self, model: SchemaModel):
        self.m = model

    def compile(self, q: Query) -> Tuple[str, List[object]]:
        self.params: List[object] = []
        self.joins: List[str] = []
        self.alias: Dict[Tuple, str] = {}
        self.n = 0
        sel, grp = [], []
        for c in q.group_by:
            e = self.col(c)
            sel.append(f"{e} AS {_qi(c.column)}")
            grp.append(e)
        if q.time_bucket:
            c, unit = q.time_bucket
            e = _BUCKET[unit].format(c=self.col(c))
            sel.append(f"{e} AS {_qi(unit)}")
            grp.append(e)
        mexprs = []
        for i, m in enumerate(q.measures):
            e = self.expr(m.expr)
            if q.share_of_total and i == 0:
                e2 = self.expr(m.expr)            # generated again so its parameters are bound in order
                e = f"({e}) * 100.0 / NULLIF(SUM({e2}) OVER (), 0)"
            mexprs.append(e)
            sel.append(f"{e} AS {_qi(m.name)}")
        where = [self.pred(f) for f in q.filters]
        sql = f"SELECT {', '.join(sel)} FROM {_qi(self.m.anchor)} AS t0"
        if self.joins:
            sql += " " + " ".join(self.joins)
        if where:
            sql += " WHERE " + " AND ".join(f"({w})" for w in where)
        if grp:
            sql += " GROUP BY " + ", ".join(grp)
        if q.order_desc is not None and mexprs:
            sql += f" ORDER BY {_qi(q.measures[0].name)} {'DESC' if q.order_desc else 'ASC'}"
            if q.group_by:
                sql += ", " + ", ".join(_qi(c.column) for c in q.group_by)
        elif q.time_bucket:
            sql += f" ORDER BY {_qi(q.time_bucket[1])}"
        if q.limit:
            sql += " LIMIT ?"
            self.params.append(int(q.limit))
        return sql, self.params

    # ------------------------------------------------------------------ pieces
    def _check(self, table: str, column: str) -> None:
        if table not in self.m.tables or column not in self.m.tables[table]:
            raise CompileError(f"unknown column {table}.{column}")

    def _up_alias(self, path: Path) -> str:
        """LEFT JOIN along the many-to-one steps of `path`; return the alias of its last table."""
        prev = "t0"
        key: Tuple = ()
        for e, d in path.steps:
            if d != "up":
                raise CompileError(f"one-to-many path {path.describe()} used outside EXISTS")
            key = key + ((e.child, e.child_col, e.parent, e.parent_col),)
            if key not in self.alias:
                self.n += 1
                a = f"j{self.n}"
                self.alias[key] = a
                self.joins.append(f"LEFT JOIN {_qi(e.parent)} AS {a} ON {a}.{_qi(e.parent_col)} = {prev}.{_qi(e.child_col)}")
            prev = self.alias[key]
        return prev

    def col(self, c: Col, scope: Dict[str, str] = None) -> str:
        self._check(c.table, c.column)
        if scope and c.table in scope:
            return f"{scope[c.table]}.{_qi(c.column)}"
        if c.path is None:
            if c.table != self.m.anchor:
                raise CompileError(f"{c.table}.{c.column} has no join path")
            return f"t0.{_qi(c.column)}"
        return f"{self._up_alias(c.path)}.{_qi(c.column)}"

    def lit(self, v: Lit) -> str:
        self.params.append(v.value)
        return "?"

    def expr(self, x, scope=None) -> str:
        if isinstance(x, Col):
            return self.col(x, scope)
        if isinstance(x, Lit):
            return self.lit(x)
        if isinstance(x, Arith):
            l, r = self.expr(x.left, scope), self.expr(x.right, scope)
            if x.op == "/":
                return f"(({l}) * 1.0 / NULLIF(({r}), 0))"
            if x.op not in "+-*":
                raise CompileError(f"operator {x.op}")
            return f"(({l}) {x.op} ({r}))"
        if isinstance(x, Agg):
            if x.func == "count" and x.arg is None:
                return "COUNT(*)" if x.where is None else f"COUNT(CASE WHEN {self.pred(x.where, scope)} THEN 1 END)"
            a = self.expr(x.arg, scope)
            if x.where is not None:
                a = f"CASE WHEN {self.pred(x.where, scope)} THEN {a} END"
            f = {"sum": "SUM", "avg": "AVG", "min": "MIN", "max": "MAX", "count": "COUNT"}.get(x.func)
            if x.func == "count_distinct":
                return f"COUNT(DISTINCT {a})"
            if f is None:
                raise CompileError(f"aggregate {x.func}")
            return f"{f}({a})"
        raise CompileError(f"expression {type(x).__name__}")

    def pred(self, p, scope=None) -> str:
        if isinstance(p, Cmp):
            if p.op not in ("=", "<>", ">", ">=", "<", "<="):
                raise CompileError(p.op)
            return f"{self.col(p.col, scope)} {p.op} {self.lit(p.value)}"
        if isinstance(p, InSet):
            c = self.col(p.col, scope)
            qs = ", ".join(self.lit(Lit(v)) for v in p.values)
            return f"({c} IS NULL OR {c} NOT IN ({qs}))" if p.negated else f"{c} IN ({qs})"
        if isinstance(p, IsNull):
            return f"{self.col(p.col, scope)} IS {'NOT ' if p.negated else ''}NULL"
        if isinstance(p, BoolOp):
            return "(" + f" {p.op.upper()} ".join(self.pred(i, scope) for i in p.items) + ")"
        if isinstance(p, Not):
            return f"NOT ({self.pred(p.item, scope)})"
        if isinstance(p, Exists):
            return self.exists(p)
        raise CompileError(f"predicate {type(p).__name__}")

    def exists(self, p: Exists) -> str:
        steps = list(p.path.steps)
        k = 0
        while k < len(steps) and steps[k][1] == "up":
            k += 1
        up, down = steps[:k], steps[k:]
        if not down or any(d != "down" for _e, d in down):
            raise CompileError(f"EXISTS needs a one-to-many path, got {p.path.describe()}")
        outer = self._up_alias(Path(up[-1][0].parent if up else self.m.anchor, tuple(up))) if up else "t0"
        frm, conds, scope = [], [], {}
        prev = outer
        for i, (e, _d) in enumerate(down):
            a = f"x{self.n}_{i}"
            frm.append(f"{_qi(e.child)} AS {a}")
            conds.append(f"{a}.{_qi(e.child_col)} = {prev}.{_qi(e.parent_col)}")
            scope[e.child] = a
            prev = a
        if p.pred is not None:
            conds.append(self.pred(p.pred, scope))
        self.n += 1
        body = f"SELECT 1 FROM {', '.join(frm)} WHERE {' AND '.join(conds)}"
        return f"{'NOT ' if p.negated else ''}EXISTS ({body})"


def inline(sql: str, params: List[object]) -> str:
    """Display form with literals substituted (evidence only; execution always uses parameters)."""
    out, i = [], 0
    for ch in sql:
        if ch == "?" and i < len(params):
            v = params[i]; i += 1
            out.append("NULL" if v is None else str(v) if isinstance(v, (int, float)) else "'" + str(v).replace("'", "''") + "'")
        else:
            out.append(ch)
    return "".join(out)
