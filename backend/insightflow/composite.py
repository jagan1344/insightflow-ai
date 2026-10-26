"""Composite questions whose formula is stated by the wording itself.

Each composite is answered from two sub-questions that go through the full pipeline (planning,
SQL checks, vetoes, semantic verification). The parts are combined only when both are answered
as single numbers; otherwise the composite is clarified. The formula is always stated.

  pct_rows    "What percentage of bookings were cancelled?"
              100 * [How many bookings were cancelled?] / [How many bookings were there?]
  share       "What share of total booking amount came from Captain's Inn?"
              100 * [total booking amount for Captain's Inn] / [total booking amount]
  ratio       "... (total fare divided by total distance)"   (only an explicit 'divided by')
              [total fare] / [total distance], with the question's shared qualifier on both
  difference  "... from Q1 2025 to Q2 2025 (Q2 minus Q1)", "how many more ... in March than in February"
              [... in the later-named period] - [... in the other]; the order must be stated

A ratio written only as "X per Y" is NOT treated as a composite: its definition (sum over sum or
mean of per-row ratios) is not established by the wording.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

_PCT = r"(?:percentage|percent|share|proportion|fraction)"
_MONTHS = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_PERIOD = rf"(?:q[1-4]\s+(?:19|20)\d{{2}}|{_MONTHS}\s+(?:19|20)\d{{2}}|(?<![\d-])(?:19|20)\d{{2}}(?![\d-]))"


@dataclass
class Composite:
    kind: str
    a: str
    b: str
    formula: str          # SQL template with {A} and {B}
    describe: str


def _clean(s: str) -> str:
    return re.sub(r"\s{2,}", " ", s).strip(" ,")


def _is_row_noun(np: str, ds) -> bool:
    from .plan.planner import _is_anchor_noun
    last = re.findall(r"[a-z]+", np.lower())
    return bool(last) and _is_anchor_noun(last[-1], ds)


def detect(question: str, ds) -> Optional[Composite]:
    if ds is None or getattr(ds, "kind", "demo") == "demo":
        return None
    q = question.strip()
    ql = q.lower()

    # explicit ratio: "(total A divided by total B)"
    m = re.search(r"\(?\s*(?:the\s+)?(?:total|sum\s+of)\s+([a-z][a-z_ \-]*?)\s+(?:divided\s+by|over)\s+"
                  r"(?:the\s+)?(?:total|sum\s+of)\s+([a-z][a-z_ \-]*?)\s*\)?\s*\??\s*$", ql)
    if m:
        qual = ""
        mq = re.match(r"^\s*(across|among|for|in|of)\s+(.+?),", ql)
        if mq:
            qual = f" for {mq.group(2)}"
        a, b = m.group(1).strip(), m.group(2).strip()
        return Composite("ratio", f"What is the total {a}{qual}?", f"What is the total {b}{qual}?",
                         "SELECT 1.0 * ({A}) / NULLIF(({B}), 0) AS value",
                         f"total {a} divided by total {b}{qual}")

    # percentage of rows meeting a condition
    m = re.match(rf"^\s*(?:what|which)\s+(?:is\s+the\s+|was\s+the\s+)?{_PCT}\s+of\s+(?:all\s+|the\s+|our\s+)?"
                 r"(.+?)\s+(were|was|are|is|had|have|has|got|did)\s+(.+?)\s*\??\s*$", q, flags=re.I)
    if m and _is_row_noun(m.group(1), ds) and not re.search(r"\b(?:from|of)\b", m.group(1), flags=re.I):
        np, aux, cond = m.group(1), m.group(2), m.group(3)
        return Composite("pct_rows", f"How many {np} {aux} {cond}?", f"How many {np} were there?",
                         "SELECT 100.0 * ({A}) / NULLIF(({B}), 0) AS value",
                         f"100 x (number of {np} that {aux} {cond}) / (number of {np})")

    # share of a total that comes from a restriction
    m = re.match(rf"^\s*(?:what|which)\s+(?:is\s+the\s+|was\s+the\s+)?{_PCT}\s+of\s+(?:the\s+|our\s+)?(?:total\s+)?"
                 r"(.+?)\s+(?:came|comes|come|was|is|were|are|went|goes)?\s*(?:from|on|for|in|at|to)\s+(.+?)\s*\??\s*$",
                 q, flags=re.I)
    if m and not _is_row_noun(m.group(1), ds):
        mp = re.sub(r"^(?:the|our)\s+", "", m.group(1).strip(), flags=re.I)
        rest = m.group(2).strip()
        return Composite("share", f"What is the total {mp} for {rest}?", f"What is the total {mp}?",
                         "SELECT 100.0 * ({A}) / NULLIF(({B}), 0) AS value",
                         f"100 x (total {mp} for {rest}) / (total {mp})")

    # difference between two explicitly ordered periods
    periods = [(mm.group(0), mm.start()) for mm in re.finditer(_PERIOD, ql)]
    distinct = []
    for p, pos in periods:
        if p not in [d for d, _ in distinct]:
            distinct.append((p, pos))
    cue = re.search(r"\b(?:minus|differ(?:ence|ed)?|change(?:d)?|more\s*\(?or\s+fewer\)?|fewer\s*\(?or\s+more\)?|"
                    r"compare(?:d)?\s+(?:with|to))\b", ql)
    if cue and len(distinct) == 2:
        later = earlier = None
        mp = re.search(rf"\(\s*([^()]*?)\s+minus\s+([^()]*?)\s*\)", ql)
        if mp:
            x, y = mp.group(1).strip(), mp.group(2).strip()
            for p, _pos in distinct:
                if x and (p == x or p.startswith(x) or x in p):
                    later = p
                elif y and (p == y or p.startswith(y) or y in p):
                    earlier = p
        if later is None or earlier is None:
            mft = re.search(rf"\bfrom\s+({_PERIOD})\s+to\s+({_PERIOD})", ql)
            mth = re.search(rf"({_PERIOD})\s+than\s+(?:in\s+|during\s+)?({_PERIOD})", ql)
            if mft:
                earlier, later = mft.group(1), mft.group(2)
            elif mth:
                later, earlier = mth.group(1), mth.group(2)
        if later is None or earlier is None or later == earlier:
            return None                      # the order of the difference is not stated: do not guess
        base = re.sub(r"\([^()]*minus[^()]*\)", " ", q, flags=re.I)
        base = re.sub(rf"\b(?:in|during|for|from|to|than\s+in|than|with|and|vs\.?|versus)?\s*{_PERIOD}", " ", base, flags=re.I)
        base = re.sub(r"\b(?:by\s+)?how\s+much\s+did\b", "what was", base, flags=re.I)
        base = re.sub(r"\bhow\s+did\b", "what was", base, flags=re.I)
        base = re.sub(r"\bhow\s+many\s+more\s*\(?or\s+fewer\)?|\bhow\s+many\s+fewer\s*\(?or\s+more\)?", "how many", base, flags=re.I)
        base = re.sub(r"\b(?:change|changed|differ|differed|compare|compared)\b(?:\s+(?:from|with|to))?"
                      r"(?:\s+those(?:\s+[a-z]+)?)?", " ", base, flags=re.I)
        base = _clean(base.rstrip("?. "))
        if len(base.split()) < 3:
            return None
        return Composite("difference", f"{base} in {later}?", f"{base} in {earlier}?",
                         "SELECT ({A}) - ({B}) AS value", f"({base} in {later}) minus ({base} in {earlier})")
    return None
