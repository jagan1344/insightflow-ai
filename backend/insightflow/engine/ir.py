"""Typed query representation (bounded, validated expression tree) produced by grounding and consumed by
verification and the SQL compiler. Every node that comes from the question carries the evidence span."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union

from .schema_model import Path


@dataclass(frozen=True)
class Col:
    table: str
    column: str
    path: Optional[Path] = None           # None: a column of the anchor table

    def key(self) -> str:
        return f"{self.table}.{self.column}" + (f"@{self.path.role}" if self.path is not None and self.path.role else "")


@dataclass(frozen=True)
class Lit:
    value: object


@dataclass(frozen=True)
class Agg:
    func: str                              # sum | avg | min | max | count | count_distinct
    arg: Optional["Expr"] = None           # None only for count(*)
    where: Optional["Pred"] = None         # conditional aggregate (CASE WHEN ...)


@dataclass(frozen=True)
class Arith:
    op: str                                # + - * /
    left: "Expr"
    right: "Expr"


Expr = Union[Col, Lit, Agg, Arith]


@dataclass(frozen=True)
class Cmp:
    col: Col
    op: str                                # = <> > >= < <=
    value: Lit


@dataclass(frozen=True)
class InSet:
    col: Col
    values: Tuple[object, ...]
    negated: bool = False                  # NOT IN keeps NULL rows (stated as an assumption)


@dataclass(frozen=True)
class IsNull:
    col: Col
    negated: bool = False


@dataclass(frozen=True)
class Exists:
    path: Path                             # one-to-many path from the anchor
    pred: Optional["Pred"] = None          # predicate on columns of the path's tables
    negated: bool = False


@dataclass(frozen=True)
class BoolOp:
    op: str                                # and | or
    items: Tuple["Pred", ...]


@dataclass(frozen=True)
class Not:
    item: "Pred"


Pred = Union[Cmp, InSet, IsNull, Exists, BoolOp, Not]


@dataclass
class Measure:
    name: str
    expr: Expr
    unit: Optional[str] = None


@dataclass
class Evidence:
    span: str                              # words of the question
    grounded_to: str                       # schema element / operation
    reason: str


@dataclass
class Query:
    measures: List[Measure] = field(default_factory=list)
    filters: List[Pred] = field(default_factory=list)
    group_by: List[Col] = field(default_factory=list)
    time_bucket: Optional[Tuple[Col, str]] = None          # (date column, month|quarter|year|week|day)
    order_desc: Optional[bool] = None                      # order by the first measure
    limit: Optional[int] = None
    share_of_total: bool = False                           # first measure as % of its grand total (per group)
    shape: str = "scalar"                                  # scalar | grouped | ranked | series
    evidence: List[Evidence] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    ambiguities: List[str] = field(default_factory=list)
    choices: List[Tuple[str, Tuple[str, ...]]] = field(default_factory=list)   # structured ambiguities: (key, readings)
    unresolved: List[str] = field(default_factory=list)
    unsupported: List[str] = field(default_factory=list)

    def cols(self) -> List[Col]:
        out: List[Col] = []

        def e(x):
            if isinstance(x, Col):
                out.append(x)
            elif isinstance(x, Agg):
                if x.arg is not None:
                    e(x.arg)
                if x.where is not None:
                    p(x.where)
            elif isinstance(x, Arith):
                e(x.left); e(x.right)

        def p(x):
            if isinstance(x, (Cmp, InSet, IsNull)):
                out.append(x.col)
            elif isinstance(x, BoolOp):
                for i in x.items:
                    p(i)
            elif isinstance(x, Not):
                p(x.item)
        for m in self.measures:
            e(m.expr)
        for f in self.filters:
            p(f)
        out += self.group_by
        if self.time_bucket:
            out.append(self.time_bucket[0])
        return out
