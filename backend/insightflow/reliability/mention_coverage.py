"""Question -> SQL mention coverage (observable evidence, planner-independent).

The plan-fidelity and intent-coverage signals compare the plan with the SQL
(or a legacy parse with the SQL). If the planner silently DROPS part of the
question, plan and SQL agree with each other and both look perfect. This
check compares the raw question against the data instead:

  * build a vocabulary of categorical values from every table connected to
    the anchor table through the discovered relationship graph
  * find those values mentioned in the question (word-bounded, longest-first)
  * a mentioned value that the generated SQL never references means part of
    the question was not answered

The result is evidence, not a probability: it can only veto an answer.
"""
from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..knowledge.relational import (RelationalSchema, discover_cached,
                                    fingerprint, foreign_tables)

_STOP = {"the", "and", "for", "all", "any", "each", "every", "per", "other",
         "total", "average", "none", "null", "unknown", "yes", "no", "true",
         "false", "new", "top", "last", "this", "next", "year", "month",
         "week", "day", "which", "what", "how", "many", "much", "by", "of"}
_MAX_DISTINCT = 5000
_cache: Dict[Tuple[str, float, str], Dict[str, List[Tuple[str, str]]]] = {}


@dataclass
class Unrepresented:
    value: str
    where: List[str]          # ["table.column", ...]


def _vocabulary(db_path: str, anchor: str) -> Dict[str, List[Tuple[str, str]]]:
    foreign = foreign_tables(db_path, anchor)
    key = (db_path, fingerprint(db_path, foreign), anchor)
    if key in _cache:
        return _cache[key]
    vocab: Dict[str, List[Tuple[str, str]]] = {}
    schema = discover_cached(db_path, anchor)
    if anchor not in schema.tables:
        _cache[key] = vocab
        return vocab
    comp = {anchor}
    changed = True
    while changed:
        changed = False
        for e in schema.edges:
            if (e.child_table in comp) != (e.parent_table in comp):
                comp |= {e.child_table, e.parent_table}
                changed = True
    con = sqlite3.connect(db_path)
    try:
        for t in sorted(comp):
            ti = schema.tables[t]
            for col, ctype in ti.columns.items():
                if not any(k in (ctype or "").upper()
                           for k in ("CHAR", "TEXT", "CLOB")):
                    continue
                rows = con.execute(
                    f'SELECT DISTINCT "{col}" FROM "{t}" WHERE "{col}" IS NOT NULL '
                    f'LIMIT {_MAX_DISTINCT + 1}').fetchall()
                if len(rows) > _MAX_DISTINCT:
                    continue
                for (v,) in rows:
                    s = str(v).strip().lower()
                    if len(s) < 3 or s in _STOP or re.fullmatch(r"[\d\W_]+", s) \
                            or re.match(r"\d{4}-\d{2}(-\d{2})?", s):
                        continue
                    vocab.setdefault(s, []).append((t, col))
    finally:
        con.close()
    if len(_cache) > 16:
        _cache.clear()
    _cache[key] = vocab
    return vocab


def unrepresented_mentions(question: str, sql: str, db_path: str,
                           anchor_table: str) -> List[Unrepresented]:
    try:
        vocab = _vocabulary(db_path, anchor_table)
    except Exception:
        return []
    if not vocab:
        return []
    ql = question.lower()
    sql_l = sql.lower().replace("''", "'")
    taken: List[Tuple[int, int]] = []
    out: List[Unrepresented] = []
    for v in sorted(vocab, key=lambda s: (-len(s), s)):
        m = re.search(rf"(?<![a-z0-9]){re.escape(v)}(?![a-z0-9])", ql)
        if not m:
            continue
        span = (m.start(), m.end())
        if any(span[0] < e and s < span[1] for s, e in taken):
            continue
        taken.append(span)
        if v not in sql_l:
            out.append(Unrepresented(v, sorted({f"{t}.{c}" for t, c in vocab[v]})))
    return out


def unrepresented_table_nouns(question: str, sql: str, rel) -> List[str]:
    """Entity nouns in the question that name another table (e.g. 'parcels'
    when the base table is 'shipments') yet appear nowhere in the SQL.
    Counting/aggregating a different entity than the base table would be
    answered with the wrong grain."""
    if rel is None or not sql:
        return []
    from ..knowledge.rel_context import fk_noun_column, parent_nouns
    ql = question.lower()
    sql_l = re.sub(r"\s+", " ", sql.lower())
    out = []
    for t in rel.schema.tables:
        if t == rel.anchor:
            continue
        for noun in parent_nouns(t):
            if not re.search(rf"(?<![a-z0-9]){re.escape(noun)}(?![a-z0-9])", ql):
                continue
            if re.search(rf"(?<![a-z0-9_]){re.escape(t.lower())}(?![a-z0-9_])", sql_l):
                break
            fk = fk_noun_column(rel, noun)
            if fk and fk.lower() in sql_l:
                break
            out.append(noun)
            break
    return out


def unrepresented_column_mentions(question: str, sql: str, ds) -> List[str]:
    """Anchor columns named in the question (space-normalised, whole
    phrase) that the SQL never touches, e.g. 'not including copay' answered
    with SUM(fee). Dimension/date/measure columns alike."""
    if ds is None or ds.kind == "demo" or not sql:
        return []
    ql = " " + re.sub(r"[^a-z0-9]+", " ", question.lower()) + " "
    sql_l = sql.lower()
    out = []
    for c, info in ds.columns.items():
        if info.role == "id":
            continue
        if getattr(ds, "rel", None) is not None and ds.rel.source(c) is not None:
            continue                     # joined dims are covered elsewhere
        phrase = " " + re.sub(r"[^a-z0-9]+", " ", c.lower()).strip() + " "
        if len(phrase.strip()) < 3 or phrase not in ql:
            continue
        if c.lower() in sql_l:
            continue
        out.append(c)
    return out
