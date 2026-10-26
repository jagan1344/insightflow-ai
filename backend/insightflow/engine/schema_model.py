"""Explicit schema semantic model for one SQLite database (deterministic, inspectable).

Facts established by the schema (types, primary keys, declared foreign keys, NOT NULL) are kept apart
from inferred semantics (date columns, 0/1 booleans, measures, units, inferred foreign keys). Nothing in
this module invents a business definition: metrics are only (aggregate, column) pairs whose types allow it.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .words import col_words, stem, table_words

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?$")
_ID_SUFFIX = ("id", "cd", "code", "no", "num", "key", "nbr", "ref")
MONEY = {"amount", "price", "fare", "cost", "fee", "revenue", "sales", "value", "usd", "eur", "gbp", "premium",
         "charge", "spend", "salary", "wage", "tip", "subtotal", "rent", "deposit", "concession", "payment", "paid",
         "total", "balance", "refund", "discount", "credit", "debit", "income", "tax"}
UNIT_WORDS = {"kwh": "kWh", "km": "km", "mi": "mi", "kg": "kg", "lb": "lb", "min": "minute", "minute": "minute",
              "hr": "hour", "hour": "hour", "sec": "second", "second": "second", "gb": "GB", "mb": "MB",
              "pct": "percent", "percent": "percent", "sqft": "sq ft", "ft": "ft", "day": "day"}


@dataclass
class Column:
    table: str
    name: str
    sql_type: str
    pk: bool
    not_null: bool
    n_rows: int = 0
    n_distinct: int = 0
    n_null: int = 0
    values: List[str] = field(default_factory=list)      # distinct text values (categorical columns only)
    kind: str = "text"     # inferred: id | measure | boolean | date | category | text
    unit: Optional[str] = None
    money: bool = False
    words: List[str] = field(default_factory=list)       # canonical stems of the name

    @property
    def ref(self) -> str:
        return f"{self.table}.{self.name}"


@dataclass(frozen=True)
class Edge:
    child: str
    child_col: str
    parent: str
    parent_col: str
    declared: bool
    nullable: bool

    def describe(self) -> str:
        return f"{self.child}.{self.child_col} -> {self.parent}.{self.parent_col}" + ("" if self.declared else " (inferred)")


@dataclass(frozen=True)
class Path:
    """Join path from the anchor table to `table`: a list of (edge, direction) with direction 'up'
    (many-to-one, child -> parent: cannot multiply anchor rows) or 'down' (one-to-many: fans out)."""
    table: str
    steps: Tuple[Tuple[Edge, str], ...]

    @property
    def fans_out(self) -> bool:
        return any(d == "down" for _e, d in self.steps)

    @property
    def inferred(self) -> bool:
        return any(not e.declared for e, _d in self.steps)

    @property
    def role(self) -> str:
        """The anchor-side FK column of the first step ('pickup_zone_cd'); names the role of a lookup."""
        return self.steps[0][0].child_col if self.steps and self.steps[0][1] == "up" else ""

    def describe(self) -> str:
        return " ; ".join(e.describe() + ("" if d == "up" else " [one-to-many]") for e, d in self.steps) or "(base table)"


@dataclass
class SchemaModel:
    db_path: str
    anchor: str
    tables: Dict[str, Dict[str, Column]]
    table_rows: Dict[str, int]
    edges: List[Edge]
    paths: Dict[str, List[Path]]          # table -> all simple paths from the anchor (<= 3 steps)

    # ------------------------------------------------------------------ queries
    def col(self, table: str, name: str) -> Column:
        return self.tables[table][name]

    def columns(self) -> List[Column]:
        return [c for t in self.tables.values() for c in t.values()]

    def reachable(self) -> List[str]:
        return [t for t in self.tables if t == self.anchor or self.paths.get(t)]

    def describe(self) -> dict:
        return dict(
            anchor=self.anchor,
            tables={t: {c.name: dict(sql_type=c.sql_type, pk=c.pk, not_null=c.not_null, kind=c.kind, unit=c.unit,
                                     money=c.money, words=c.words, n_distinct=c.n_distinct, n_null=c.n_null)
                        for c in cols.values()} for t, cols in self.tables.items()},
            edges=[dict(edge=e.describe(), declared=e.declared, nullable=e.nullable) for e in self.edges],
            paths={t: [p.describe() for p in ps] for t, ps in self.paths.items()},
            established="sql types, primary keys, declared foreign keys, NOT NULL",
            inferred="column kinds (id/measure/boolean/date/category/text), units, money-likeness, undeclared foreign keys")


# ---------------------------------------------------------------------- building
def _affinity(t: str) -> str:
    t = (t or "").upper()
    if "INT" in t:
        return "INTEGER"
    if any(k in t for k in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if any(k in t for k in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    if any(k in t for k in ("NUM", "DEC")):
        return "NUMERIC"
    return "TEXT" if not t else "NUMERIC"


def ordinal(c: "Column") -> bool:
    """A small-range integer measure (grade level, model year) that can also label groups."""
    return c.kind == "measure" and "INT" in (c.sql_type or "").upper() and not c.money and 0 < c.n_distinct <= 30


def _id_like(name: str) -> bool:
    toks = [x for x in re.split(r"[^a-z0-9]+", name.lower()) if x]
    return bool(toks) and toks[-1] in _ID_SUFFIX


def _classify(con, table: str, c: Column, fk_cols: Set[str]) -> None:
    q = f'"{table}"'
    qc = f'"{c.name}"'
    c.n_rows = con.execute(f"SELECT COUNT(*) FROM {q}").fetchone()[0]
    c.n_null = con.execute(f"SELECT COUNT(*) FROM {q} WHERE {qc} IS NULL").fetchone()[0]
    c.n_distinct = con.execute(f"SELECT COUNT(DISTINCT {qc}) FROM {q}").fetchone()[0]
    sample = [r[0] for r in con.execute(f"SELECT DISTINCT {qc} FROM {q} WHERE {qc} IS NOT NULL LIMIT 400")]
    toks = [x for x in re.split(r"[^a-z0-9]+", c.name.lower()) if x]
    c.words = col_words(c.name)
    for i, t in enumerate(toks):
        u = UNIT_WORDS.get(t) or UNIT_WORDS.get(stem(t)) or (UNIT_WORDS.get(t[:-1]) if t.endswith("s") else None)
        if u and not (i and toks[i - 1] == "per"):     # per_min_rate is a rate, not a quantity in minutes
            c.unit = u
    if c.pk or c.name in fk_cols:
        c.kind = "id"
        return
    aff = _affinity(c.sql_type)
    if aff in ("INTEGER", "REAL", "NUMERIC") and all(isinstance(v, (int, float)) for v in sample):
        if sample and set(sample) <= {0, 1}:
            c.kind = "boolean"
        elif _id_like(c.name):
            c.kind = "id"
        else:
            c.kind = "measure"
            c.money = bool(set(stem(t) for t in toks) & {stem(m) for m in MONEY}) or "amt" in toks
        return
    if sample and all(isinstance(v, str) and _ISO_DATE.match(v) for v in sample[:50]):
        c.kind = "date"
        return
    if _id_like(c.name) and c.n_distinct > 0.9 * max(1, c.n_rows - c.n_null):
        c.kind = "id"
        return
    if c.n_distinct <= 200 or c.n_distinct <= 0.2 * max(1, c.n_rows):
        c.kind = "category"
        c.values = [str(v) for v in sample][:400]
    else:
        c.kind = "text"
        c.values = [str(v) for v in sample][:400] if c.n_distinct <= 400 else []


def _contained(con, ct, cc, pt, pc) -> bool:
    n = con.execute(f'SELECT COUNT(*) FROM "{ct}" WHERE "{cc}" IS NOT NULL').fetchone()[0]
    if n == 0:
        return False
    miss = con.execute(f'SELECT COUNT(*) FROM "{ct}" c WHERE c."{cc}" IS NOT NULL AND NOT EXISTS '
                       f'(SELECT 1 FROM "{pt}" p WHERE p."{pc}" = c."{cc}")').fetchone()[0]
    return miss == 0


def _name_evidence(child_col: str, parent: str, parent_col: str) -> bool:
    """The child column names the parent: same name as the parent key, or its non-suffix words name the
    parent table, or (role-prefixed codes) it ends with the same key suffix as a TEXT parent key."""
    if child_col.lower() == parent_col.lower():
        return True
    ctoks = [x for x in re.split(r"[^a-z0-9]+", child_col.lower()) if x]
    ptoks = [x for x in re.split(r"[^a-z0-9]+", parent_col.lower()) if x]
    core = [stem(t) for t in ctoks[:-1]]
    tw = set(table_words(parent))
    if core and (core[-1] in tw or any(len(c) >= 3 and any(w.startswith(c) for w in tw) for c in core[-1:])):
        return True
    c = core[-1] if core else ""
    if 2 <= len(c) <= 4 and not set(c[1:]) & set("aeiouy"):     # vowel-less abbreviation: stn -> station
        if any(w[0] == c[0] and len(w) > len(c) and _subseq(c, w) for w in tw):
            return True
    return False


def _subseq(a: str, b: str) -> bool:
    it = iter(b)
    return all(ch in it for ch in a)


def build(db_path: str, anchor: str) -> SchemaModel:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '\\_%' ESCAPE '\\'")]
        declared: List[Edge] = []
        info = {}
        for t in names:
            cols = con.execute(f'PRAGMA table_info("{t}")').fetchall()
            info[t] = cols
            for r in con.execute(f'PRAGMA foreign_key_list("{t}")'):
                ptab, ccol, pcol = r[2], r[3], r[4]
                if ptab in names:
                    if pcol is None:
                        pk = [c[1] for c in con.execute(f'PRAGMA table_info("{ptab}")') if c[5]]
                        pcol = pk[0] if len(pk) == 1 else None
                    if pcol:
                        nn = any(c[1] == ccol and c[3] for c in cols)
                        declared.append(Edge(t, ccol, ptab, pcol, True, not nn))
        fk_cols = {t: {e.child_col for e in declared if e.child == t} for t in names}
        tables: Dict[str, Dict[str, Column]] = {}
        rows = {}
        for t in names:
            pks = [c[1] for c in info[t] if c[5]]
            tables[t] = {}
            for cid, nm, typ, notnull, _d, pk in info[t]:
                col = Column(t, nm, typ or "", bool(pk) and len(pks) == 1, bool(notnull) or bool(pk))
                _classify(con, t, col, fk_cols[t])
                tables[t][nm] = col
            rows[t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        # inferred FKs: id-like child column, parent single-column unique key, name evidence, full containment
        inferred: List[Edge] = []
        have = {(e.child, e.child_col) for e in declared}
        for t in names:
            for c in tables[t].values():
                if (t, c.name) in have or c.pk or not _id_like(c.name):
                    continue
                cands = []
                for p in names:
                    if p == t:
                        continue
                    for pc in tables[p].values():
                        if not pc.pk or _affinity(pc.sql_type) != _affinity(c.sql_type):
                            continue
                        if _name_evidence(c.name, p, pc.name) or (
                                _affinity(pc.sql_type) == "TEXT" and pc.name.split("_")[-1] == c.name.split("_")[-1]
                                and c.n_distinct >= 3):
                            if _contained(con, t, c.name, p, pc.name):
                                cands.append((p, pc.name))
                if len(cands) == 1:
                    inferred.append(Edge(t, c.name, cands[0][0], cands[0][1], False, not c.not_null and c.n_null > 0))
                    c.kind = "id"
        edges = declared + inferred
    finally:
        con.close()
    m = SchemaModel(db_path, anchor, tables, rows, edges, {})
    m.paths = _paths(m)
    return m


def _paths(m: SchemaModel, max_len: int = 3) -> Dict[str, List[Path]]:
    out: Dict[str, List[Path]] = {}

    def walk(cur: str, visited: Set[str], steps: List[Tuple[Edge, str]]):
        if len(steps) >= max_len:
            return
        for e in m.edges:
            for here, there, d in ((e.child, e.parent, "up"), (e.parent, e.child, "down")):
                if here != cur or there in visited:
                    continue
                # never climb back up after fanning out (child -> other parent of the child is a sibling join)
                if steps and steps[-1][1] == "down" and d == "up":
                    continue
                st = steps + [(e, d)]
                out.setdefault(there, []).append(Path(there, tuple(st)))
                walk(there, visited | {there}, st)
    walk(m.anchor, {m.anchor}, [])
    for t in out:
        out[t].sort(key=lambda p: (len(p.steps), p.fans_out))
    return out


_CACHE: Dict[Tuple[str, str, float], SchemaModel] = {}


def get(db_path: str, anchor: str) -> SchemaModel:
    import os
    key = (db_path, anchor, os.path.getmtime(db_path))
    if key not in _CACHE:
        _CACHE[key] = build(db_path, anchor)
    return _CACHE[key]
