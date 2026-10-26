"""Checks that compare the question's wording with the executed SQL (language rules, no schema names).

comparator_not_preserved   "1000 or more" / "at least 4.8" / "above 40" but the SQL compares that number with
                           '=' or the opposite direction
negated_value_kept         a value the question negates ("not paid in cash", "leaving out Commercial") is kept
                           by a positive equality / IN in the SQL
rate_not_computed          "rate", "percentage", "share", "proportion" or "ratio" wording but the SQL divides nothing
vague_metric               "doing best", "performing" etc. while no measure of the data is named in the question
"""
from __future__ import annotations

import re
from typing import List

from .preserve import SemanticFinding as F

_NUM = r"(\d+(?:\.\d+)?)"
_GE = re.compile(rf"(?:at\s+least|no\s+less\s+than|minimum\s+of)\s+{_NUM}|{_NUM}\s*(?:\+|(?:or|and)\s+(?:more|higher|greater|above|over|up))\b")
_LE = re.compile(rf"(?:at\s+most|no\s+more\s+than|maximum\s+of)\s+{_NUM}|{_NUM}\s*(?:or|and)\s+(?:less|lower|fewer|below|under)\b")
_GT = re.compile(rf"(?:more|greater|larger|bigger|higher|longer)\s+than\s+{_NUM}|(?:above|over|exceeding)\s+{_NUM}")
_LT = re.compile(rf"(?:less|fewer|smaller|lower|shorter)\s+than\s+{_NUM}|(?:below|under)\s+{_NUM}")
_NEG = r"(?:not|never|excluding|except(?:\s+for)?|other\s+than|apart\s+from|leaving\s+out|leave\s+out|without|isn't|aren't|wasn't|weren't|didn't)"
_RATE = re.compile(r"\b(rate|percentage|percent|proportion|share|ratio|fraction)\b|%")
_VAGUE = re.compile(r"\b(?:doing\s+(?:best|worst|well|badly|poorly)|perform(?:ing|ance|s)?|best|worst|strongest|weakest|healthiest)\b")


def _ops_for(sql: str, num: str) -> List[str]:
    n = re.escape(num)
    alts = {n}
    if "." in num:
        alts.add(re.escape(num.rstrip("0").rstrip(".")))
    else:
        alts.add(n + r"\.0+")
    pat = "|".join(sorted(alts, key=len, reverse=True))
    return re.findall(rf"(>=|<=|<>|!=|=|>|<)\s*'?(?:{pat})'?(?![\d.])", sql)


def _inside_negation(sql: str, pos: int) -> bool:
    """True when position `pos` lies inside a NOT EXISTS (...) / NOT (...) / NOT IN (...) scope."""
    for m in re.finditer(r"\bNOT\s+(?:EXISTS\s*|IN\s*)?\(", sql, flags=re.I):
        if m.end() > pos:
            break
        depth = 1
        for ch in sql[m.end():pos]:
            depth += (ch == "(") - (ch == ")")
            if depth == 0:
                break
        if depth > 0:
            return True
    return False


def check_wording(question: str, sql: str, plan=None, ds=None, catalog=None) -> List[F]:
    q = question.lower()
    s = re.sub(r"\s+", " ", sql or "")
    out: List[F] = []
    for rx, want in ((_GE, {">=", ">"}), (_LE, {"<=", "<"}), (_GT, {">", ">="}), (_LT, {"<", "<="})):
        for m in rx.finditer(q):
            num = next(g for g in m.groups() if g)
            ops = _ops_for(s, num)
            if ops and not (set(ops) & want):
                out.append(F("comparator_not_preserved",
                             f"the question compares with {num} ('{m.group(0)}') but the query uses "
                             f"'{ops[0]} {num}'"))
    if ds is not None and getattr(ds, "kind", "demo") != "demo":
        try:
            from ..plan.planner import _value_index, _value_mentions
            for lo, cands in _value_mentions(question, _value_index(ds)):
                i = q.find(lo)
                if i < 0 or not re.search(rf"\b{_NEG}\b(?:\s+[a-z'\-]+){{0,4}}\s*$", q[max(0, i - 60):i]):
                    continue
                for _c, orig in cands:
                    v = re.escape(str(orig).replace("'", "''"))
                    hits = [h for h in list(re.finditer(rf"(?<![<>!])=\s*'{v}'", s)) +
                            list(re.finditer(rf"(?<!NOT )IN\s*\([^)]*'{v}'", s, flags=re.I))
                            if not _inside_negation(s, h.start())]
                    if hits:
                        out.append(F("negated_value_kept",
                                     f"the question excludes '{orig}' but the query keeps only rows equal to it"))
                        break
        except Exception:
            pass
    if _RATE.search(q) and "/" not in s and not re.search(r"rate|ratio|pct|percent|share", s, flags=re.I):
        out.append(F("rate_not_computed",
                     "the question asks for a rate, share or percentage but the query divides nothing"))
    if _VAGUE.search(q) and catalog is not None and plan is not None:
        named = False
        for m in (getattr(plan, "measures", None) or []):
            k = catalog.get(getattr(m, "kpi_id", ""))
            for a in (k.aliases if k else []):
                if len(a) > 2 and re.search(rf"(?<![a-z0-9]){re.escape(a.lower())}(?![a-z0-9])", q):
                    named = True
        if not named:
            out.append(F("vague_metric",
                         "the question asks who is doing best or performing, but names no measure; "
                         "the query picked one by default"))
    return out
