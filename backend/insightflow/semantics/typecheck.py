"""Semantic type checking of a SemanticSpec BEFORE its SQL is trusted.

Each rule rejects an interpretation that is mechanically executable but means
something else than the question. Findings are 'violation' (do not answer)
or 'note' (recorded assumption, shown in diagnostics)."""
from __future__ import annotations

import re
from typing import List

from .preserve import SemanticFinding as F


def typecheck(spec, question: str, ds) -> List[F]:
    out: List[F] = []
    q = question.lower()
    rel = getattr(ds, "rel", None)

    for u in spec.unresolved:
        out.append(F("unresolved_reference",
                     f"the question has an unresolved part ({u}) but an answer was produced"))

    for mt in spec.metrics:
        agg = mt.aggregation
        for g in mt.columns:
            if g.origin == "ungrounded":
                continue
            if g.semantic_type == "flag" and agg in ("sum", "avg", "min", "max", "ratio", "derived"):
                out.append(F("flag_used_as_quantity",
                             f"'{g.column}' is a yes/no indicator, not an amount; "
                             f"{agg.upper()} of it answers a different question"))
            if g.semantic_type == "id" and agg in ("sum", "avg", "min", "max"):
                out.append(F("identifier_used_as_quantity",
                             f"'{g.column}' is an identifier; {agg.upper()} of it is meaningless"))

    # a count of another entity must be a DISTINCT count of that entity's key
    m = re.search(r"\bhow\s+many\s+(distinct\s+|unique\s+|different\s+)?([a-z]+)", q)
    if m and rel is not None:
        from ..knowledge.rel_context import parent_nouns
        from ..plan.planner import _is_anchor_noun
        noun = m.group(2)
        other = {n for t in rel.schema.tables if t != rel.anchor for n in parent_nouns(t)}
        if noun in other and not _is_anchor_noun(noun, ds) \
                and not any(mt.aggregation == "count_distinct" for mt in spec.metrics) \
                and not any(mt.columns and mt.columns[0].origin == "related" for mt in spec.metrics):
            out.append(F("entity_count_mismatch",
                         f"'how many {noun}' asks about {noun}, but the query counts "
                         f"{ds.table} rows"))

    rs, sh = spec.requested_shape, spec.shape
    if rs == "scalar" and sh in ("grouped", "ranking", "trend"):
        out.append(F("shape_scalar_expected",
                     f"the question reads as one figure but the plan is a {sh}"))
    if rs in ("grouped", "trend") and sh == "scalar" and spec.intent not in ("distinct_count", "null_count", "extremum"):
        out.append(F("shape_breakdown_expected",
                     f"the question asks for a {rs} breakdown but the plan is a single figure"))
    if rs == "ranking" and sh in ("scalar", "grouped") and re.search(r"\b(top|bottom)\s+\d+\b", q):
        out.append(F("shape_ranking_expected", "the question asks for a top/bottom list that the plan does not rank"))

    if spec.time is not None:
        if spec.time.role_basis == "guessed":
            out.append(F("date_role_guessed",
                         f"'{spec.time.column}' was chosen among several date columns without any basis"))
        from ..plan.planner import _mentioned_date_col
        named = _mentioned_date_col(question, ds)
        if named and named != spec.time.column and spec.time.role_basis != "governed":
            out.append(F("date_role_mismatch",
                         f"the wording points at '{named}' but the time filter uses '{spec.time.column}'"))

    for d in spec.dims:
        if d.origin == "related" and rel is not None:
            s = rel.source(d.column)
            if s is not None and s.kind != "safe":
                out.append(F("unsafe_grouping_path",
                             f"grouping by '{d.column}' goes through a {s.kind} relationship"))
    for j in spec.joins:
        if not j.safe and not j.semi:
            out.append(F("unsafe_join", f"join to '{j.table}' via {j.via} is not a safe many-to-one path"))
    for a in spec.assumptions:
        out.append(F("assumption", a, "note"))
    return out
