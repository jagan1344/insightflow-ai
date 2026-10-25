"""Question-wording audit of the executed SQL ("did we answer THIS question?").

Plan fidelity compares the plan with the SQL, and both come from the same
reading of the question. The audit compares the raw wording with the SQL
and the result SHAPE, without using the planner's decisions as evidence:

  aggregation_cue    "average" -> AVG, "how many" -> COUNT, "total" -> SUM/COUNT,
                     "maximum/minimum" -> MAX/MIN (or ORDER BY ... LIMIT)
  unrequested_grouping   a scalar-sounding question ("Total X", "How many")
                     answered with a GROUP BY / many rows: it answers a
                     different question even though the groups add up
  measure_not_named  the measure was chosen by default, not by the wording
  month_not_applied  a month/quarter named in the question has no matching
                     date literal in the SQL

Each finding is a *violation* (answer would address a different question).
This is heuristic evidence, English-only, and can both miss errors and
over-trigger on unusual phrasing; it is a veto layer, not a proof.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

_MONTHS = ["january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december"]

_GROUP_CUE = re.compile(
    r"\b(by|per|each|every|across|breakdown|broken\s+down|split|grouped|"
    r"group|which|top|bottom|rank|ranking|best|worst|highest|lowest|"
    r"compare|comparison|versus|vs|share|contribution|trend|over\s+time|"
    r"monthly|weekly|daily|quarterly|yearly|annual|annually|list|show|"
    r"breakdowns?|distribution|growth|change|rolling|moving|cumulative|"
    r"drop|decline|why|driver|drivers|contributed|distinct\s+\w+\s+and)\b")
_SCALAR_CUE = re.compile(
    r"^\s*(?:what\s+(?:is|was|are|were)\s+(?:the\s+)?|how\s+many\s+|"
    r"how\s+much\s+|total\s+|sum\s+of\s+|number\s+of\s+|count\s+of\s+|"
    r"average\s+|avg\s+|mean\s+|maximum\s+|minimum\s+|max\s+|min\s+)")


@dataclass
class AuditFinding:
    name: str
    detail: str


def grouped_sql_present(s: str) -> bool:
    return re.search(r"\bgroup by\b|\bover\s*\(", s) is not None


def _has_agg(sql_l: str, fn: str) -> bool:
    return re.search(rf"\b{fn}\s*\(", sql_l) is not None


def audit(question: str, sql: str, plan, catalog, n_rows: int,
          intent_ok_kinds=("direct_kpi", "breakdown", "top_n", "trend",
                           "distinct_count", "null_count", "extremum")
          ) -> List[AuditFinding]:
    out: List[AuditFinding] = []
    if not sql or plan is None or plan.intent_kind not in intent_ok_kinds:
        return out
    q = question.lower()
    # "paid BY students FROM Ohio": an agent constraint, not a grouping cue
    q_cues = re.sub(r"\bby\s+[a-z_\-]+(?:\s+[a-z_\-]+)?\s+"
                    r"(?:from|with|who|whose|living|based|born|located)\b",
                    " ", q)
    s = re.sub(r"\s+", " ", sql.lower())
    kinds_agg = {m.aggregation for m in plan.measures}

    # ---- aggregation wording -------------------------------------------
    avg_cue = re.search(r"\b(average|avg|mean)\b", q)
    cnt_cue = re.search(r"\b(how\s+many|number\s+of|count\s+of|count)\b", q)
    max_cue = re.search(r"\b(maximum|max)\b", q)
    min_cue = re.search(r"\b(minimum|min)\b", q)
    if avg_cue and not (_has_agg(s, "avg") or "avg" in kinds_agg
                        or "ratio" in kinds_agg or "derived" in kinds_agg
                        or ("/" in s and _has_agg(s, "count"))):
        out.append(AuditFinding(
            "aggregation_cue", "question asks for an average but the query "
            "does not compute one"))
    named_sum = False
    if catalog is not None:
        for m in plan.measures:
            k = catalog.get(m.kpi_id)
            if k is not None and any(
                    re.search(rf"(?<![a-z0-9]){re.escape(a.lower())}(?![a-z0-9])", q)
                    for a in k.aliases):
                named_sum = True            # "how many units were sold"
    if cnt_cue and not (_has_agg(s, "count") or "count" in kinds_agg
                        or "count_distinct" in kinds_agg or named_sum):
        out.append(AuditFinding(
            "aggregation_cue", "question asks for a count but the query "
            "does not count"))
    if max_cue and not (_has_agg(s, "max") or "order by" in s):
        out.append(AuditFinding("aggregation_cue",
                                "question asks for a maximum; query has no MAX"))
    if min_cue and not (_has_agg(s, "min") or "order by" in s):
        out.append(AuditFinding("aggregation_cue",
                                "question asks for a minimum; query has no MIN"))

    # ---- ratio / percentage wording --------------------------------------
    if re.search(r"\b(percent|percentage|proportion|fraction|ratio|share\s+of)\b", q):
        ok = (getattr(plan, "share_of_total", False)
              or "ratio" in kinds_agg or "derived" in kinds_agg
              or re.search(r"[a-z)]\s*/\s*[a-z(]", s) is not None
              or (catalog is not None and any(
                  (catalog.get(m.kpi_id) is not None and any(
                      re.search(rf"\b{w}\b", a.lower()) for a in catalog.get(m.kpi_id).aliases
                      for w in ("percent", "percentage", "proportion", "ratio", "rate", "share")))
                  for m in plan.measures)))
        if not ok:
            out.append(AuditFinding(
                "ratio_cue", "the question asks for a percentage/share/ratio but "
                "the query returns a plain total or count"))

    # ---- top / bottom N wording ------------------------------------------
    mt = re.search(r"\b(top|bottom)\s+(\d+)\b", q)
    if mt and not plan.top_n and "limit" not in s \
            and "row_number" not in s:
        out.append(AuditFinding(
            "top_n_not_applied",
            f"'{mt.group(0)}' is in the question but the query does not rank or limit"))

    # ---- "each X" asks for one row per X --------------------------------
    me = re.search(r"\b(?:for\s+|in\s+|from\s+|does\s+|do\s+|has\s+|have\s+)?each\s+[a-z_]+", q_cues)
    if me and not grouped_sql_present(s) and not getattr(plan, "top_n", None):
        out.append(AuditFinding(
            "missing_grouping",
            f"'{me.group(0).strip()}' asks for one figure per item but the query "
            "returns a single figure"))

    # ---- result shape ----------------------------------------------------
    grouped = re.search(r"\bgroup by\b", s) is not None
    if grouped and _SCALAR_CUE.search(q) and not _GROUP_CUE.search(q_cues) \
            and not plan.top_n:
        out.append(AuditFinding(
            "unrequested_grouping",
            "the question reads as a single figure but the query returns one "
            "row per group"))

    # ---- measure chosen by default --------------------------------------
    implicit_ok = (any(f.kind.startswith("metric_") for f in plan.filters)
                   or plan.relative_stat is not None)
    if catalog is not None and not implicit_ok:
        for m in plan.measures:
            k = catalog.get(m.kpi_id)
            if k is None or k.aggregation == "count":
                continue          # synthetic, or a count implied by the wording
            names = [a.lower() for a in k.aliases] + [k.display_name.lower()]
            if not any(re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", q)
                       for a in names if a):
                out.append(AuditFinding(
                    "measure_not_named",
                    f"the question never names '{k.display_name}'; it was "
                    f"assumed"))
                break

    # ---- more figures than were asked for ---------------------------------
    if catalog is not None and len(plan.measures) > 1:
        cnt_kpis = [m for m in plan.measures
                    if (catalog.get(m.kpi_id) is not None
                        and catalog.get(m.kpi_id).aggregation == "count")]
        if cnt_kpis and not cnt_cue and len(cnt_kpis) < len(plan.measures):
            out.append(AuditFinding(
                "extra_measure",
                "a count was added that the question did not ask for"))

    # ---- month / quarter named but not applied ---------------------------
    for i, mname in enumerate(_MONTHS, 1):
        pat = rf"\b{mname}\b"
        if mname == "may":
            pat = r"\b(?:in|of|during|for|since|until|through)\s+may\b"
        if re.search(pat, q) and f"-{i:02d}" not in s \
                and "strftime" not in s and "substr" not in s:
            out.append(AuditFinding(
                "month_not_applied",
                f"'{mname}' is named but no matching date constraint was applied"))
            break
    return out
