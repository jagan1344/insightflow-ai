"""Relational schema discovery and safe join-path resolution.

Goal: let the planner/compiler reason over an arbitrary multi-table SQLite
database without any schema-specific code.

Relationships come from two sources only:
  * declared  - FOREIGN KEY constraints (PRAGMA foreign_key_list)
  * inferred  - a child column is accepted as a foreign key ONLY when ALL of
      (1) the parent column is a single-column key (PK or fully unique, non-null),
      (2) every non-null child value exists in the parent column (containment),
      (3) there is NAME evidence linking the child column to that parent
          (same name as the parent key, or a token of the child column name
          matches the parent table's stem),
      (4) exactly one parent satisfies 1-3 for that child column
          (otherwise the column is left unlinked rather than guessed).
  Similar names alone, or value containment alone (small-integer columns
  are "contained" in nearly any key range), never create an edge.

Join paths are classified so the compiler can avoid silent row fan-out:
  * a step child->parent (many-to-one) is SAFE: it cannot multiply fact rows
  * a step parent->child (one-to-many) FANS OUT the anchor rows
  * a nullable foreign key on a safe step means INNER JOIN would drop rows
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass(frozen=True)
class Edge:
    child_table: str
    child_col: str
    parent_table: str
    parent_col: str
    status: str            # "declared" | "inferred"
    nullable: bool = False

    def key(self) -> Tuple[str, str, str, str]:
        return (self.child_table, self.child_col,
                self.parent_table, self.parent_col)


@dataclass(frozen=True)
class Step:
    edge: Edge
    direction: str         # "up": child->parent (safe) | "down": parent->child (fan-out)

    @property
    def from_table(self) -> str:
        return self.edge.child_table if self.direction == "up" \
            else self.edge.parent_table

    @property
    def to_table(self) -> str:
        return self.edge.parent_table if self.direction == "up" \
            else self.edge.child_table


@dataclass(frozen=True)
class JoinPath:
    steps: Tuple[Step, ...]

    @property
    def safe(self) -> bool:
        return all(s.direction == "up" for s in self.steps)

    @property
    def nullable(self) -> bool:
        return any(s.direction == "up" and s.edge.nullable
                   for s in self.steps)

    @property
    def inferred(self) -> bool:
        return any(s.edge.status == "inferred" for s in self.steps)

    def describe(self) -> str:
        return " -> ".join(
            f"{s.from_table}.{s.edge.child_col if s.direction == 'up' else s.edge.parent_col}"
            f"={s.to_table}.{s.edge.parent_col if s.direction == 'up' else s.edge.child_col}"
            for s in self.steps)


@dataclass
class PathResolution:
    kind: str              # "same" | "unique" | "ambiguous" | "fanout" | "none"
    paths: List[JoinPath] = field(default_factory=list)

    @property
    def path(self) -> Optional[JoinPath]:
        return self.paths[0] if self.kind in ("unique", "fanout") and self.paths else None


@dataclass
class TableInfo:
    name: str
    columns: Dict[str, str]                  # col -> declared type
    pk: Tuple[str, ...]
    not_null: Set[str]
    unique_cols: Set[str]                    # single columns with no duplicates, no NULLs
    row_count: int
    declared_keys: Set[str] = field(default_factory=set)   # PK / UNIQUE constraint


_STOP_TOKENS = {"id", "key", "no", "ref", "fk", "pk", "code", "num", "number"}


def _tokens(name: str) -> List[str]:
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return [t for t in re.split(r"[^a-zA-Z0-9]+", name.lower()) if t]


def _stems(word: str) -> Set[str]:
    """All plausible singular forms (plural rules are ambiguous:
    'warehouses' -> warehouse, but 'boxes' -> box)."""
    w = word.lower()
    out = {w}
    if w.endswith("ies") and len(w) > 4:
        out.add(w[:-3] + "y")
    if w.endswith("es") and len(w) > 4:
        out.add(w[:-2])
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        out.add(w[:-1])
    return out


def _table_stems(table: str) -> Set[str]:
    toks = [t for t in _tokens(table) if t not in _STOP_TOKENS]
    out: Set[str] = set()
    for t in toks:
        out |= _stems(t)
    if toks:
        out |= _stems("".join(toks))
    return out


def _name_evidence(child_col: str, parent_table: str, parent_col: str) -> bool:
    if child_col.lower() == parent_col.lower():
        return True
    stems = _table_stems(parent_table)
    for t in _tokens(child_col):
        if t in _STOP_TOKENS:
            continue
        tss = _stems(t)
        for s in stems:
            if s in tss:
                return True
            # abbreviation: "cust" ~ "customer", "shp" is too short to trust
            if any(len(ts) >= 4 and s.startswith(ts) for ts in tss):
                return True
    return False


class RelationalSchema:
    def __init__(self, tables: Dict[str, TableInfo], edges: List[Edge]):
        self.tables = tables
        self.edges = edges
        self.unlinked_candidates: List[Tuple[str, str, str]] = []

    # ------------------------------------------------------------------
    @classmethod
    def discover(cls, db_path: str,
                 exclude: Optional[Set[str]] = None) -> "RelationalSchema":
        """`exclude`: tables to ignore (e.g. other uploaded datasets and
        registry metadata that share the physical database)."""
        con = sqlite3.connect(db_path)
        try:
            return cls._discover(con, exclude or set())
        finally:
            con.close()

    @classmethod
    def _discover(cls, con: sqlite3.Connection,
                  exclude: Set[str]) -> "RelationalSchema":
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name")
            if r[0] not in exclude]
        tables: Dict[str, TableInfo] = {}
        for t in names:
            info = con.execute(f'PRAGMA table_info("{t}")').fetchall()
            cols = {r[1]: (r[2] or "") for r in info}
            pk = tuple(r[1] for r in sorted(
                (r for r in info if r[5]), key=lambda r: r[5]))
            nn = {r[1] for r in info if r[3] or r[5]}
            n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            uniq: Set[str] = set()
            for c in cols:
                if len(pk) == 1 and c == pk[0]:
                    uniq.add(c); continue
                if n == 0:
                    continue
                d, nul = con.execute(
                    f'SELECT COUNT(DISTINCT "{c}"), '
                    f'SUM("{c}" IS NULL) FROM "{t}"').fetchone()
                if d == n and not nul:
                    uniq.add(c)
            dk: Set[str] = set(pk) if len(pk) == 1 else set()
            for ix in con.execute(f'PRAGMA index_list("{t}")').fetchall():
                if ix[2]:                      # unique index
                    icols = [r[2] for r in con.execute(f'PRAGMA index_info("{ix[1]}")')]
                    if len(icols) == 1:
                        dk.add(icols[0])
            tables[t] = TableInfo(t, cols, pk, nn, uniq, n, dk)

        edges: List[Edge] = []
        declared: Set[Tuple[str, str]] = set()
        for t in names:
            for r in con.execute(f'PRAGMA foreign_key_list("{t}")').fetchall():
                _id, _seq, ptab, ccol, pcol = r[0], r[1], r[2], r[3], r[4]
                if ptab not in tables:
                    continue
                if pcol is None:
                    pk = tables[ptab].pk
                    pcol = pk[0] if len(pk) == 1 else None
                if pcol is None:
                    continue
                edges.append(Edge(t, ccol, ptab, pcol, "declared",
                                   ccol not in tables[t].not_null))
                declared.add((t, ccol))

        schema = cls(tables, edges)
        for t, ti in tables.items():
            for c, ctype in ti.columns.items():
                if (t, c) in declared:
                    continue
                cands = []
                for p, pi in tables.items():
                    if p == t:
                        continue   # self-references are not inferred
                    for pc in pi.unique_cols:
                        if not _name_evidence(c, p, pc):
                            continue
                        if not _types_compatible(ctype, pi.columns[pc]):
                            continue
                        if _contained(con, t, c, p, pc):
                            cands.append((p, pc))
                if len(cands) > 1:
                    # A declared key (PK/UNIQUE) is stronger evidence than a
                    # column that merely happens to be duplicate-free today.
                    strong = [(p, pc) for p, pc in cands
                              if pc in tables[p].declared_keys]
                    if len(strong) == 1:
                        cands = strong
                if len(cands) == 1:
                    p, pc = cands[0]
                    edges.append(Edge(t, c, p, pc, "inferred",
                                       c not in ti.not_null and
                                       _has_nulls(con, t, c)))
                elif len(cands) > 1:
                    schema.unlinked_candidates.append(
                        (t, c, "|".join(f"{p}.{pc}" for p, pc in cands)))
        schema.edges = edges
        return schema

    # ------------------------------------------------------------------
    def role(self, table: str) -> str:
        """bridge | entity | isolated, from FK structure only. Whether a
        table is the 'fact' table of a question is decided by where the
        bound measure lives, not by a global label."""
        out = [e for e in self.edges if e.child_table == table]
        inc = [e for e in self.edges if e.parent_table == table]
        ti = self.tables[table]
        if len(out) >= 2 and set(ti.pk) >= {e.child_col for e in out} \
                and len(ti.columns) <= len(out) + 1:
            return "bridge"
        if not out and not inc:
            return "isolated"
        return "entity"

    def edges_between(self, a: str, b: str) -> List[Edge]:
        return [e for e in self.edges
                if {e.child_table, e.parent_table} == {a, b}]

    def resolve(self, src: str, dst: str, max_depth: int = 4) -> PathResolution:
        if src == dst:
            return PathResolution("same", [JoinPath(())])
        found: List[JoinPath] = []

        def walk(cur: str, visited: Set[str], steps: List[Step]) -> None:
            if len(steps) >= max_depth:
                return
            for e in self.edges:
                if e.child_table == cur:
                    nxt, d = e.parent_table, "up"
                elif e.parent_table == cur:
                    nxt, d = e.child_table, "down"
                else:
                    continue
                if nxt in visited:
                    continue
                st = steps + [Step(e, d)]
                if nxt == dst:
                    found.append(JoinPath(tuple(st)))
                else:
                    walk(nxt, visited | {nxt}, st)

        walk(src, {src}, [])
        # An explicit bridge (many-to-many) table is the schema's own
        # statement of an association; prefer paths through one over paths
        # that merely meet at a shared parent ("zig-zag" via a dimension).
        bridged = [p for p in found
                   if any(self.role(st.from_table) == "bridge" or
                          self.role(st.to_table) == "bridge" for st in p.steps)]
        if bridged and len(bridged) < len(found):
            m0 = min(len(p.steps) for p in found)
            if any(len(p.steps) == m0 for p in bridged):
                found = [p for p in found
                         if p in bridged or len(p.steps) > m0]
        safe = [p for p in found if p.safe]
        if safe:
            m = min(len(p.steps) for p in safe)
            best = [p for p in safe if len(p.steps) == m]
            return PathResolution("unique" if len(best) == 1 else "ambiguous",
                                  best)
        if found:
            m = min(len(p.steps) for p in found)
            best = [p for p in found if len(p.steps) == m]
            return PathResolution("fanout" if len(best) == 1 else "ambiguous",
                                  best)
        return PathResolution("none", [])

    def as_dict(self) -> dict:
        return {
            "tables": {t: {"pk": list(i.pk), "rows": i.row_count,
                            "role": self.role(t)}
                       for t, i in self.tables.items()},
            "edges": [dict(child=f"{e.child_table}.{e.child_col}",
                           parent=f"{e.parent_table}.{e.parent_col}",
                           status=e.status, nullable=e.nullable)
                      for e in self.edges],
        }


def _types_compatible(a: str, b: str) -> bool:
    def fam(t: str) -> str:
        t = (t or "").upper()
        if "INT" in t:
            return "int"
        if any(k in t for k in ("CHAR", "TEXT", "CLOB")):
            return "text"
        if any(k in t for k in ("REAL", "FLOA", "DOUB", "NUM", "DEC")):
            return "num"
        return "any"
    fa, fb = fam(a), fam(b)
    return fa == fb or "any" in (fa, fb)


def _contained(con: sqlite3.Connection, ct: str, cc: str,
               pt: str, pc: str) -> bool:
    n = con.execute(f'SELECT COUNT(*) FROM "{ct}" WHERE "{cc}" IS NOT NULL'
                    ).fetchone()[0]
    if n == 0:
        return False
    miss = con.execute(
        f'SELECT COUNT(*) FROM "{ct}" c WHERE c."{cc}" IS NOT NULL AND '
        f'NOT EXISTS (SELECT 1 FROM "{pt}" p WHERE p."{pc}" = c."{cc}")'
    ).fetchone()[0]
    return miss == 0


def _has_nulls(con: sqlite3.Connection, t: str, c: str) -> bool:
    return con.execute(
        f'SELECT 1 FROM "{t}" WHERE "{c}" IS NULL LIMIT 1').fetchone() is not None


# ---------------------------------------------------------------------------
# Change detection + cached discovery (schema-change resilience)
# ---------------------------------------------------------------------------

def foreign_tables(db_path: str, anchor: str) -> Set[str]:
    """Registry metadata and tables of OTHER uploaded datasets that share
    the physical database; they are not part of the anchor's schema."""
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("SELECT table_name FROM _datasets").fetchall()
        return {r[0] for r in rows if r[0] != anchor} | {"_datasets"}
    except sqlite3.Error:
        return set()
    finally:
        con.close()


def fingerprint(db_path: str, exclude: Optional[Set[str]] = None) -> str:
    """DDL version + per-table row counts (+ column lists). Changes when a
    table/column/key is added, dropped or altered, or data is added/removed."""
    exclude = exclude or set()
    con = sqlite3.connect(db_path)
    try:
        ver = con.execute("PRAGMA schema_version").fetchone()[0]
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name") if r[0] not in exclude]
        parts = []
        for n in names:
            c = con.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]
            parts.append(f"{n}={c}")
        return f"{ver}:" + ",".join(parts)
    finally:
        con.close()


_schema_cache: Dict[Tuple[str, str], RelationalSchema] = {}


def discover_cached(db_path: str, anchor: str) -> RelationalSchema:
    ex = foreign_tables(db_path, anchor)
    key = (db_path, fingerprint(db_path, ex))
    sch = _schema_cache.get(key)
    if sch is None:
        sch = RelationalSchema.discover(db_path, ex)
        if len(_schema_cache) > 16:
            _schema_cache.clear()
        _schema_cache[key] = sch
    return sch


def schema_snapshot(db_path: str, anchor: str) -> dict:
    ex = foreign_tables(db_path, anchor)
    sch = discover_cached(db_path, anchor)
    return {"tables": {t: sorted(i.columns) for t, i in sch.tables.items()
                       if t not in ex},
            "edges": sorted("%s.%s->%s.%s" % e.key() for e in sch.edges)}


def snapshot_diff(old: dict, new: dict) -> str:
    out = []
    ot, nt = old["tables"], new["tables"]
    for t in sorted(set(nt) - set(ot)):
        out.append(f"table added: {t}")
    for t in sorted(set(ot) - set(nt)):
        out.append(f"table dropped: {t}")
    for t in sorted(set(ot) & set(nt)):
        for c in sorted(set(nt[t]) - set(ot[t])):
            out.append(f"column added: {t}.{c}")
        for c in sorted(set(ot[t]) - set(nt[t])):
            out.append(f"column dropped: {t}.{c}")
    for e in sorted(set(new["edges"]) - set(old["edges"])):
        out.append(f"relationship added: {e}")
    for e in sorted(set(old["edges"]) - set(new["edges"])):
        out.append(f"relationship removed: {e}")
    return "; ".join(out) or "metadata changed"
