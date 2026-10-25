"""Relational context for an anchor ("fact") table.

Turns the relationship graph into what the planner/compiler need:

  * `sources`: flat dimension names -> physical (table, column) plus the
    join steps that reach it from the anchor
  * every source is classified:
      safe       reachable by exactly one many-to-one chain (no fan-out)
      fanout     only reachable through a one-to-many / bridge hop; may be
                 used as a FILTER (semi-join) but never as a GROUP BY
      ambiguous  more than one equally short join path, or the same column
                 name exists in several tables -> must be clarified
  * role aliases: when a parent table is referenced twice by the anchor
    (origin_hub / dest_hub), each foreign-key column becomes its own
    dimension so users can say "by origin hub"

No schema-specific names appear here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .relational import Edge, JoinPath, RelationalSchema, Step, discover_cached

_TEXT = ("CHAR", "TEXT", "CLOB")


@dataclass
class DimSource:
    flat: str
    table: str
    column: str
    kind: str                         # safe | fanout | ambiguous
    steps: Tuple[Step, ...] = ()
    nullable: bool = False
    candidates: List[str] = field(default_factory=list)   # for ambiguous
    via_fk: str = ""                  # role alias: the anchor FK column
    numeric: bool = False             # numeric attribute of a many-to-one parent


@dataclass
class RelContext:
    anchor: str
    schema: RelationalSchema
    sources: Dict[str, DimSource] = field(default_factory=dict)
    fk_columns: Dict[str, Edge] = field(default_factory=dict)   # anchor FK cols
    anchor_nouns: List[str] = field(default_factory=list)

    def source(self, flat: str) -> Optional[DimSource]:
        return self.sources.get(flat)


_NUM = ("INT", "REAL", "NUM", "DEC", "FLOA", "DOUB")


def _is_numeric(t: str) -> bool:
    return any(k in (t or "").upper() for k in _NUM)


def _is_text(t: str) -> bool:
    return any(k in (t or "").upper() for k in _TEXT)


def _display_column(schema: RelationalSchema, table: str) -> Optional[str]:
    ti = schema.tables[table]
    keys = set(ti.pk) | {e.child_col for e in schema.edges
                         if e.child_table == table}
    texts = [c for c, t in ti.columns.items() if _is_text(t) and c not in keys]
    for c in texts:
        if re.search(r"name|label|title", c.lower()):
            return c
    for c in texts:
        if c in ti.unique_cols:
            return c
    return texts[0] if texts else None


def build_rel_context(db_path: str, anchor: str) -> Optional[RelContext]:
    schema = discover_cached(db_path, anchor)
    if anchor not in schema.tables:
        return None
    if not any(e.child_table == anchor or e.parent_table == anchor
               for e in schema.edges):
        return None                       # flat table: nothing relational
    ctx = RelContext(anchor=anchor, schema=schema)
    ctx.fk_columns = {e.child_col: e for e in schema.edges
                      if e.child_table == anchor}

    stem = re.sub(r"[^a-z0-9]+", " ", anchor.lower()).strip()
    ctx.anchor_nouns = sorted({stem, stem.rstrip("s")} - {""})

    # --- classify every other table ------------------------------------
    per_table: Dict[str, "object"] = {}
    for t in schema.tables:
        if t == anchor:
            continue
        res = schema.resolve(anchor, t)
        if res.kind != "none":
            per_table[t] = res

    cand_by_name: Dict[str, List[Tuple[str, str]]] = {}
    for t, res in per_table.items():
        ti = schema.tables[t]
        keys = set(ti.pk) | {e.child_col for e in schema.edges
                             if e.child_table == t}
        for c, ctype in ti.columns.items():
            if _is_text(ctype) and c not in keys:
                cand_by_name.setdefault(c, []).append((t, c))
    anchor_cols = set(schema.tables[anchor].columns)

    for name, tcs in cand_by_name.items():
        clash = len(tcs) > 1 or name in anchor_cols
        for t, c in tcs:
            res = per_table[t]
            if clash:
                cands = [f"{tt}.{cc}" for tt, cc in tcs]
                ctx.sources[name] = DimSource(
                    name, t, c, "ambiguous", (), False, cands)
                continue
            if res.kind == "unique":
                p = res.path
                ctx.sources[name] = DimSource(
                    name, t, c, "safe", p.steps, p.nullable)
            elif res.kind == "fanout":
                ctx.sources[name] = DimSource(
                    name, t, c, "fanout", res.path.steps)
            else:   # ambiguous path
                via = [p.describe() for p in res.paths]
                ctx.sources[name] = DimSource(
                    name, t, c, "ambiguous", (), False,
                    [f"{t}.{c} via {v}" for v in via])

    # --- numeric attributes of many-to-one parents (measures / filters) ---
    num_by_name: Dict[str, List[Tuple[str, str]]] = {}
    for t, res in per_table.items():
        if res.kind != "unique":
            continue
        ti = schema.tables[t]
        keys = set(ti.pk) | {e.child_col for e in schema.edges
                             if e.child_table == t}
        for c, ctype in ti.columns.items():
            if _is_numeric(ctype) and c not in keys:
                num_by_name.setdefault(c, []).append((t, c))
    taken = set(anchor_cols) | set(ctx.sources)
    for name, tcs in num_by_name.items():
        if len(tcs) > 1 or name in taken:
            continue                       # clash: not exposed (never guessed)
        t, c = tcs[0]
        p = per_table[t].path
        ctx.sources[name] = DimSource(name, t, c, "safe", p.steps,
                                      p.nullable, numeric=True)

    # --- role aliases: parent referenced by several anchor FK columns ----
    by_parent: Dict[str, List[Edge]] = {}
    for e in ctx.fk_columns.values():
        by_parent.setdefault(e.parent_table, []).append(e)
    for parent, es in by_parent.items():
        if len(es) < 2:
            continue
        disp = _display_column(schema, parent)
        if not disp:
            continue
        for e in es:
            ctx.sources[e.child_col] = DimSource(
                e.child_col, parent, disp, "safe",
                (Step(e, "up"),), e.child_col not in
                schema.tables[anchor].not_null, via_fk=e.child_col)
    return ctx


def _singular(w: str) -> str:
    w = w.lower()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("s") and len(w) > 3 and not w.endswith("ss"):
        return w[:-1]
    return w


def parent_nouns(table: str) -> List[str]:
    t = re.sub(r"[^a-z0-9]+", " ", table.lower()).strip()
    words = t.split()
    if not words:
        return []
    last = words[-1]
    return sorted({t, " ".join(words[:-1] + [_singular(last)]),
                   last, _singular(last)})


def fk_noun_column(rel: RelContext, noun: str) -> Optional[str]:
    """Anchor FK column whose parent table is called `noun` (singular or
    plural, e.g. 'patients' -> patient_id). None when absent or when the
    anchor has several FKs to that parent (role-playing: must be named)."""
    n = _singular(noun.lower().replace("_", " "))
    hits = []
    for col, e in rel.fk_columns.items():
        if n in {_singular(x) for x in parent_nouns(e.parent_table)}:
            hits.append(col)
    return hits[0] if len(hits) == 1 else None


def table_noun_dimension(rel: RelContext, noun: str) -> Optional[str]:
    """'doctors' -> the flat display dimension of table doctors (safe path
    only)."""
    n = _singular(noun.lower().replace("_", " "))
    for t in rel.schema.tables:
        if t == rel.anchor:
            continue
        if n not in {_singular(x) for x in parent_nouns(t)}:
            continue
        disp = _display_column(rel.schema, t)
        for flat, src in rel.sources.items():
            if src.table == t and src.column == disp and src.kind == "safe" \
                    and not src.via_fk:
                return flat
    return None
