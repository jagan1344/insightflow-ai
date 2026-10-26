"""Question -> typed Query. Every content word must be accounted for by a grounded element (value, column,
table, role, date, number) or an operator cue; anything left over is reported as unresolved. Competing
candidates are kept as ambiguities, never resolved arbitrarily. Each decision is recorded as Evidence."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from . import lexicon as L
from .ir import Agg, Arith, BoolOp, Cmp, Col, Evidence, Exists, InSet, IsNull, Lit, Measure, Not, Query
from .schema_model import Path, SchemaModel, ordinal
from .words import DERIV, FUNCTION, UNITS, canon, participle, table_words

# ------------------------------------------------------------------ vocabulary of operations (language only)
HEADLESS = {canon(w) for w in ("result", "record", "entry", "log", "detail", "info", "fact", "event", "history")}
LIGHT = {canon(w) for w in """
have has had get got make made do did take took come came go went happen occur show see give record recorded
log logged list tell want need know look find book put use using used involve involved handle handled process
processed place placed create created submit submitted include included contain contained
actually currently still ever already overall altogether across all entire whole our us we company
business data dataset table record records entry entries row rows item items thing things kind kinds type types last
""".split()} - {canon("item"), canon("items"), canon("type"), canon("types"), canon("kind")}
FILLER = {"please", "also", "just", "i", "e", "eg", "ie", "etc", "currently", "actually", "ever", "so", "far"}

AGG_CUES = [
    (r"\bhow\s+much\b", "sum"), (r"\btotals?\b", "sum"), (r"\bsum(?:\s+of)?\b", "sum"), (r"\bcombined\b", "sum"),
    (r"\baverage\b|\bavg\b|\bmean\b|\btypical\b", "avg"),
    (r"\bhow\s+many\b", "count"), (r"\bnumber\s+of\b", "count"), (r"\bcount(?:\s+of)?\b", "count"),
    (r"\bvolume\b", "count"),
    (r"\bmaximum\b|\bmax\b|\blargest\b|\bbiggest\b|\bhighest\b", "max"),
    (r"\bminimum\b|\bmin\b|\bsmallest\b|\blowest\b", "min"),
]
DISTINCT_CUE = r"\b(?:distinct|unique|different)\b"
GROUP_CUES = r"\b(?:broken\s+(?:out|down)\s+by|split\s+by|grouped\s+by|break\s+(?:it\s+)?down\s+by|for\s+each|for\s+every|by\s+each|in\s+each|by|per|each|every)\b"
NEG_CUES = (r"\b(?:not|no|never|without|excluding|exclude|except(?:\s+for)?|other\s+than|apart\s+from|"
            r"leaving\s+out|leave\s+out|skip|skipping|ignore|ignoring|omit|omitting|non)\b")
NULL_AFTER = (r"^\s*(?:(?:is|was|are|were|has\s+been|have\s+been)\s+)?(?:missing|unknown|blank|empty|null|unrecorded|unset|"
              r"left\s+blank|not\s+(?:recorded|known|set|entered|given|provided|filled\s+in|captured|on\s+file|assigned)|"
              r"(?:isn't|wasn't|aren't|weren't|hasn't\s+been|haven't\s+been)\s+(?:recorded|known|set|entered|on\s+file|assigned))\b")
NULL_BEFORE = (r"(?:\bno|\bwithout\s+(?:an?\s+|any\s+)?|\bmissing|\bunknown|\b(?:do|does|did)\s+not\s+have\s+(?:an?\s+|any\s+)?|"
               r"\bnever\s+(?:got|had|received|was\s+given)\s+(?:an?\s+|any\s+)?|\bhas\s+no|\bhave\s+no|\bhad\s+no)\s*$")
NOTNULL_AFTER = r"^\s*(?:(?:is|was|are|were)\s+)?(?:on\s+file|recorded|known|present|set|provided|filled\s+in)\b"
PCT_CUE = r"\b(?:percentage|percent|share|proportion|fraction)\b|%"
TOP_CUE = r"\b(?:top|bottom|best|worst|leading)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b"
WHICH_N = r"\b(?:which|what)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b"
RANK_DESC = r"\b(?:most|highest|largest|biggest|top|greatest|best)\b"
RANK_ASC = r"\b(?:least|lowest|smallest|fewest|bottom|worst)\b"
BUCKET_CUES = [(r"\bmonthly\b|\bmonth[\s-]+by[\s-]+month\b|\b(?:by|per|each|every|a)\s+month\b|\bmonth\s+over\s+month\b", "month"),
               (r"\bquarterly\b|\b(?:by|per|each|every|a)\s+quarter\b", "quarter"),
               (r"\byearly\b|\bannually\b|\b(?:by|per|each|every|a)\s+year\b|\byear\s+over\s+year\b", "year"),
               (r"\bweekly\b|\b(?:by|per|each|every|a)\s+week\b", "week"),
               (r"\bdaily\b|\b(?:by|per|each|every|a)\s+day\b", "day"),
               (r"\bover\s+time\b|\btrend(?:s|ed|ing)?\b", "month")]      # unit not stated: month, as an assumption
COMPARE = r"\b(?:vs\.?|versus|compared?\s+(?:to|with)|compare|minus|difference|change[ds]?|more|fewer|less)\b"
NUMWORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
POLARITY = {"ok", "good", "valid", "success", "successful", "pass", "passed", "active", "standing", "complet", "clean", "met"}
ANTONYM = r"\b(?:faulty|failed|failing|failure|broken|bad|invalid|incomplete|problem|problems|issue|issues|declined|rejected|unsuccessful|errors?|missed|miss|misses|breached)\b"
POSITIVE = r"\b(?:ok|okay|good|valid|successful|success|passed|working|clean|complete)\b"

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
YEAR = r"((?:19|20)\d{2})"


def _mon(s: str) -> int:
    s = s.lower()[:3]
    return next(i for m, i in MONTHS.items() if m.startswith(s))


def _nxt(y: int, m: int) -> str:
    return f"{y + (m == 12):04d}-{(m % 12) + 1:02d}-01"


@dataclass
class Tok:
    text: str
    low: str
    can: str
    s: int
    e: int


@dataclass
class Period:
    lo: str
    hi: str           # exclusive
    label: str
    i0: int
    i1: int


@dataclass
class Mention:
    i0: int
    i1: int
    kind: str          # col | table | value
    cands: list        # ColEntry / TableEntry / ValueEntry
    text: str


@dataclass
class Grounding:
    query: Query
    mentions: List[Mention] = field(default_factory=list)
    periods: List[Period] = field(default_factory=list)
    consumed: Dict[int, str] = field(default_factory=dict)


class Grounder:
    def __init__(self, model: SchemaModel, lex: L.Lexicon, prefer: Optional[Dict[str, int]] = None):
        self.m, self.lex = model, lex
        self.prefer = dict(prefer or {})      # reading chosen for a structured ambiguity (key -> index)

    # ------------------------------------------------------------------ helpers
    def _tok(self, q: str) -> List[Tok]:
        return [Tok(m.group(0), m.group(0).lower(), m.group(0).lower() if m.group(0).lower() in FUNCTION else canon(m.group(0)),
                    m.start(), m.end())
                for m in re.finditer(r"[A-Za-z0-9]+(?:\.[0-9]+)?", q)]

    def _span(self, s: int, e: int) -> Tuple[int, int]:
        idx = [i for i, t in enumerate(self.t) if t.s >= s and t.e <= e]
        return (idx[0], idx[-1] + 1) if idx else (-1, -1)

    def _use(self, i0: int, i1: int, why: str) -> None:
        for i in range(i0, i1):
            self.used.setdefault(i, why)

    def _free(self, i0: int, i1: int) -> bool:
        return all(i not in self.used for i in range(i0, i1))

    def _text(self, i0: int, i1: int) -> str:
        return self.q[self.t[i0].s:self.t[i1 - 1].e] if 0 <= i0 < i1 <= len(self.t) else ""

    def _ev(self, i0, i1, what, why):
        self.Q.evidence.append(Evidence(self._text(i0, i1), what, why))

    def _col(self, e) -> Col:
        return Col(e.table, e.column, e.path)

    # ------------------------------------------------------------------ main
    def ground(self, question: str) -> Grounding:
        q = question.strip()
        q = re.sub(r"(?<=\d),(?=\d{3}\b)", "", q)
        q = re.sub(r"\b(\w+)n't\b", lambda m: {"wo": "will", "ca": "can", "sha": "shall"}.get(m.group(1).lower(), m.group(1)) + " not", q, flags=re.I)
        q = q.replace("%", " percent ")
        q = re.sub(r"\b([A-Za-z]+)-(in|out|up|off|on)\b", r"\1\2", q)
        self.q, self.ql = q, q.lower()
        self.t = self._tok(q)
        self.used: Dict[int, str] = {}
        self.ctx: Set[int] = set()
        self.extra: list = []
        self.Q = Query()
        self.G = Grounding(self.Q)
        self._values()
        self._periods()
        self._numbers_and_limits()
        self._schema_mentions()
        self._assemble()
        self._account()
        return self.G

    # ------------------------------------------------------------------ values
    def _values(self) -> None:
        found = []
        for lo, ents in sorted(self.lex.values.items(), key=lambda kv: -len(kv[0])):
            pat = rf"(?<![A-Za-z0-9]){re.escape(lo)}(?:s|es)?(?![A-Za-z0-9])"
            for m in re.finditer(pat, self.ql):
                orig = self.q[m.start():m.start() + len(lo)]
                if lo in FUNCTION and orig != ents[0].text:
                    continue
                if len(lo) <= 3 and all(e.text.isupper() for e in ents) and orig != orig.upper():
                    continue
                i0, i1 = self._span(m.start(), m.end())
                if i0 < 0 or not self._free(i0, i1):
                    continue
                if orig.islower() and ents[0].text[:1].isupper() and " " not in lo and participle(orig):
                    key = f"val:{i0}"
                    if key not in self.prefer:
                        self.Q.ambiguities.append(f"'{orig}' could be the stored value {ents[0].table}.{ents[0].column} = "
                                                  f"'{ents[0].text}' or just a verb")
                        self.Q.choices.append((key, (f"{ents[0].column} = '{ents[0].text}'", f"'{orig}' as a verb")))
                    elif self.prefer[key] == 1:
                        self._use(i0, i1, "verb")
                        continue
                if any(re.fullmatch(rx, lo) for rx, _u in BUCKET_CUES):
                    own = {w for e in ents for w in self.m.col(e.table, e.column).words} | \
                          {w for e in ents for w in (canon(x) for x in e.table.split("_"))}
                    if not (i1 < len(self.t) and self.t[i1].can in own):
                        self.Q.ambiguities.append(f"'{orig}' could mean a {lo} time series or the stored value "
                                                  f"{ents[0].table}.{ents[0].column} = '{ents[0].text}'")
                        self._use(i0, i1, "value")
                        continue
                self._use(i0, i1, "value")
                found.append(Mention(i0, i1, "value", ents, orig))
        self.G.mentions += found

    # ------------------------------------------------------------------ dates
    def _add_period(self, s, e, lo, hi, label):
        i0, i1 = self._span(s, e)
        if i0 < 0 or not self._free(i0, i1):
            return
        self._use(i0, i1, "date")
        self.G.periods.append(Period(lo, hi, label, i0, i1))

    def _periods(self) -> None:
        ql = self.ql
        # month ranges: "january through june 2025", "from january to june 2025"
        for m in re.finditer(rf"\b(?:from\s+|between\s+)?{MON}\s+(?:{YEAR}\s+)?(?:through|thru|to|until|-|and)\s+{MON}\s+{YEAR}\b", ql):
            y1 = int(m.group(2) or m.group(4)); y2 = int(m.group(4))
            self._add_period(m.start(), m.end(), f"{y1:04d}-{_mon(m.group(1)):02d}-01", _nxt(y2, _mon(m.group(3))), m.group(0))
        # quarter pairs sharing a year: "q1 vs q2 2025"
        for m in re.finditer(rf"\bq([1-4])\s+(?:and|vs\.?|versus|to|or|compared\s+(?:to|with))\s+q([1-4])\s+(?:of\s+)?{YEAR}\b", ql):
            y = int(m.group(3))
            for qn, (a, b) in ((m.group(1), (m.start(), m.start() + 2)), (m.group(2), (m.start(2) - 1, m.end(2)))):
                n = int(qn)
                self.G.periods.append(Period(f"{y:04d}-{3 * n - 2:02d}-01", _nxt(y, 3 * n), f"q{n} {y}", *self._span(a, b)))
            self._use(*self._span(m.start(), m.end()), "date")
        # month pairs sharing a year: "april vs may 2025"
        for m in re.finditer(rf"\b{MON}\s+(?:and|vs\.?|versus|or|compared\s+(?:to|with))\s+{MON}\s+{YEAR}\b", ql):
            if not self._free(*self._span(m.start(), m.end())):
                continue
            y = int(m.group(3))
            for mon, (a, b) in ((m.group(1), m.span(1)), (m.group(2), m.span(2))):
                k = _mon(mon)
                self.G.periods.append(Period(f"{y:04d}-{k:02d}-01", _nxt(y, k), f"{mon} {y}", *self._span(a, b)))
            self._use(*self._span(m.start(), m.end()), "date")
        for m in re.finditer(rf"\b(?:the\s+)?(first|second|1st|2nd)\s+half\s+(?:of\s+)?{YEAR}\b|\bh([12])\s+{YEAR}\b", ql):
            y = int(m.group(2) or m.group(4)); h = 1 if (m.group(1) or "").startswith(("first", "1")) or m.group(3) == "1" else 2
            self._add_period(m.start(), m.end(), f"{y:04d}-{1 if h == 1 else 7:02d}-01", f"{y if h == 1 else y + 1:04d}-{7 if h == 1 else 1:02d}-01", m.group(0))
        for m in re.finditer(rf"\b(?:q([1-4])|(first|second|third|fourth)\s+quarter)\s+(?:of\s+)?{YEAR}\b", ql):
            n = int(m.group(1)) if m.group(1) else ["first", "second", "third", "fourth"].index(m.group(2)) + 1
            y = int(m.group(3))
            self._add_period(m.start(), m.end(), f"{y:04d}-{3 * n - 2:02d}-01", _nxt(y, 3 * n), m.group(0))
        for m in re.finditer(r"\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b", ql):
            d = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            import datetime as _d
            nx = (_d.date.fromisoformat(d) + _d.timedelta(days=1)).isoformat()
            self._add_period(m.start(), m.end(), d, nx, d)
        for m in re.finditer(rf"\b{MON}\.?\s+{YEAR}\b", ql):
            k, y = _mon(m.group(1)), int(m.group(2))
            self._add_period(m.start(), m.end(), f"{y:04d}-{k:02d}-01", _nxt(y, k), m.group(0))
        for m in re.finditer(rf"\b(?:from|between)\s+{YEAR}\s+(?:to|and|through|until)\s+{YEAR}\b|\b{YEAR}\s*(?:-|through|to)\s*{YEAR}\b", ql):
            a = int(m.group(1) or m.group(3)); b = int(m.group(2) or m.group(4))
            self._add_period(m.start(), m.end(), f"{a:04d}-01-01", f"{b + 1:04d}-01-01", m.group(0))
        for m in re.finditer(rf"\b(before|after|since|until|through)\s+{YEAR}\b", ql):
            y = int(m.group(2)); w = m.group(1)
            lo, hi = ("0001-01-01", f"{y:04d}-01-01") if w == "before" else (f"{y + 1:04d}-01-01", "9999-12-31") if w == "after" \
                else (f"{y:04d}-01-01", "9999-12-31") if w == "since" else ("0001-01-01", f"{y + 1:04d}-01-01")
            self._add_period(m.start(), m.end(), lo, hi, m.group(0))
        for m in re.finditer(rf"(?<![\d-]){YEAR}(?![\d-])", ql):
            if re.search(r"\b(?:over|above|under|below|than|exceeding|least|most|of|to|minimum|maximum|=)\s*$", ql[:m.start()]):
                continue                            # "enrollments over 2000": a number, not the year 2000
            y = int(m.group(1))
            self._add_period(m.start(), m.end(), f"{y:04d}-01-01", f"{y + 1:04d}-01-01", m.group(0))
        for m in re.finditer(rf"\b(?:in|during|of|for|since|until|before|after)\s+{MON}\b(?!\s*\.?\s*(?:19|20)\d\d)", ql):
            a, b = self._span(m.start(1), m.end(1))
            if a >= 0 and self._free(a, b):
                self._use(a, b, "date")
                self.Q.unresolved.append(f"'{self.t[a].text}' has no year; which year is meant?")
        self.G.periods.sort(key=lambda p: p.i0)
        if re.search(r"\b(?:last|this|next|previous|past|current)\s+(?:\d+\s+)?(?:year|quarter|month|week|day)s?\b|\byesterday\b|\btoday\b|\bytd\b", ql):
            self.Q.unsupported.append("relative dates (last/this/next period) are not resolved against a reference date")

    # ------------------------------------------------------------------ numbers, comparators, limits
    def _numbers_and_limits(self) -> None:
        ql = self.ql
        self.limits = []
        for rx in (TOP_CUE, WHICH_N, r"\b(?:the\s+)?(\d+|three|five|ten)\s+(?:highest|largest|biggest|most|lowest|smallest|fewest|least|top|best|worst)\b"):
            for m in re.finditer(rx, ql):
                n = m.group(1)
                n = int(n) if n.isdigit() else NUMWORD.get(n)
                i0, i1 = self._span(m.start(), m.end())
                if n and i0 >= 0 and self._free(i0, i1):
                    self.limits.append((n, i0, i1, m.group(0)))
                    self._use(i0, i1, "limit")
        self.nums = []
        GE = r"at\s+least|no\s+less\s+than|minimum\s+of|a\s+minimum\s+of"
        GT = r"more\s+than|greater\s+than|over|above|exceeding|higher\s+than|larger\s+than|bigger\s+than|heavier\s+than|longer\s+than|older\s+than|later\s+than|after"
        LE = r"at\s+most|no\s+more\s+than|maximum\s+of|up\s+to"
        LT = r"less\s+than|fewer\s+than|under|below|lower\s+than|smaller\s+than|lighter\s+than|shorter\s+than|younger\s+than|cheaper\s+than|before"
        EQ = r"exactly|equal\s+to|equals|of|=|is|at"
        pre = rf"(?:({GE})|({GT})|({LE})|({LT})|({EQ}))\s+"
        for m in re.finditer(rf"(?:{pre})?(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])(\s*(?:\+|or\s+(?:more|higher|greater|above|over|up|longer|later|heavier)|and\s+(?:up|above|over)|or\s+(?:less|fewer|lower|below|under|shorter)|and\s+(?:below|under)))?", ql):
            i0, i1 = self._span(m.start(6), m.end(6))
            if i0 < 0 or not self._free(i0, i1):
                continue
            op = ">=" if m.group(1) else ">" if m.group(2) else "<=" if m.group(3) else "<" if m.group(4) else "="
            suf = (m.group(7) or "").strip()
            if suf:
                op = ">=" if re.search(r"\+|more|higher|greater|above|over|up|longer|later|heavier", suf) else "<="
            explicit = bool(m.group(1) or m.group(2) or m.group(3) or m.group(4) or suf)
            j0, j1 = self._span(m.start(), m.end())
            self.nums.append(dict(value=float(m.group(6)), op=op, i0=j0, i1=j1, explicit=explicit, num_i=i0))
            self._use(j0 if explicit else i0, j1 if explicit else i1, "number")

    # ------------------------------------------------------------------ schema mentions
    def _match(self, allowed: Set[str], required: Set[str], i: int) -> Optional[Tuple[int, Set[str]]]:
        got, j, last = set(), i, None
        while j < len(self.t):
            if j in self.used:
                break
            c = self.t[j].can
            pre = [w for w in allowed if 3 <= len(w) <= 4 and len(self.t[j].low) > len(w) and self.t[j].low.startswith(w)]
            der = [w for w in allowed if len(c) >= 4 and any(w == c + sfx for sfx in DERIV)]
            neg = j == i and self.t[j].low.startswith(("un", "non")) and canon(self.t[j].low[2:] if self.t[j].low.startswith("un") else self.t[j].low[3:]) in allowed
            if c in allowed or pre or der or neg:
                got.add(c if c in allowed else pre[0] if pre else der[0] if der else
                        canon(self.t[j].low[2:] if self.t[j].low.startswith("un") else self.t[j].low[3:])); last = j
            elif c in ("of", "the") and last is not None and j + 1 < len(self.t):
                pass
            else:
                break
            j += 1
        if last is None or not required <= got:
            return None
        return last + 1, got

    def _schema_mentions(self) -> None:
        cands = []
        for e in self.lex.cols:
            allowed = set(e.words) | set(e.role_words)
            kind = self.m.col(e.table, e.column).kind
            req = set(e.core)
            if kind == "boolean" and req - POLARITY - LIGHT - FUNCTION:
                req = req - POLARITY - LIGHT          # helmet_used: "helmet"; sla_met: "SLA"
            elif kind == "measure" and req - UNITS - FUNCTION:
                req = req - UNITS                     # score_pct: "score"; dur_min: "duration"
            for i in range(len(self.t)):
                lo = self.t[i].low
                unneg = lo.startswith("un") and canon(lo[2:]) in allowed or lo.startswith("non") and canon(lo[3:]) in allowed
                if i in self.used or not (self.t[i].can in allowed or unneg or any(
                        3 <= len(w) <= 4 and len(lo) > len(w) and lo.startswith(w) for w in allowed) or any(
                        len(self.t[i].can) >= 4 and w == self.t[i].can + sfx for w in allowed for sfx in DERIV)):
                    continue
                r = self._match(allowed, req, i)
                if r:
                    end, got = r
                    rolehit = len(got & set(e.role_words))
                    cands.append((end - i, len(got) + rolehit, i, end, "col", e))
        for te in self.lex.tables:
            allowed = set(te.words) | set(te.role_words)
            req = set(te.words[-1:])
            if len(te.words) > 1 and te.words[-1] in HEADLESS and not any(
                    o.table != te.table and set(te.words[:-1]) & set(o.words) for o in self.lex.tables):
                req = set(te.words[:-1])              # exam_results: "exams"
            for i in range(len(self.t)):
                if self.t[i].can not in allowed or i in self.used:
                    continue
                r = self._match(allowed, req, i)
                if r:
                    end, got = r
                    cands.append((end - i, len(got) - 0.5, i, end, "table", te))
        cands.sort(key=lambda c: (-c[0], -c[1], c[2]))
        taken: Dict[Tuple[int, int], Mention] = {}
        for ln, sc, i, end, kind, e in cands:
            key = (i, end)
            if key in taken:
                mm = taken[key]
                if mm.kind == kind and mm.score == sc:
                    mm.cands.append(e)
                continue
            if not self._free(i, end):
                continue
            mm = Mention(i, end, kind, [e], self._text(i, end))
            mm.score = sc
            lo = self.t[i].low
            mm.unneg = kind == "col" and lo.startswith(("un", "non")) and lo not in ("unit", "units", "union", "unique", "none") \
                and self.t[i].can not in set(e.words)
            taken[key] = mm
            self._use(i, end, kind)
        self.G.mentions += list(taken.values())
        # unit words: "duration in minutes" (the unit of the column just named), "fare per kilometre" (a column named by
        # its unit, when exactly one numeric column has that unit)
        for i, t in enumerate(self.t):
            if i in self.used or i == 0 or t.can not in UNITS or self.t[i - 1].low not in ("in", "per"):
                continue
            ucols = [c for c in self.lex.cols if self.m.col(c.table, c.column).kind == "measure" and self.m.col(c.table, c.column).unit
                     and canon(self.m.col(c.table, c.column).unit) == t.can and not (c.path is not None and c.path.fans_out)]
            prev = [x for x in taken.values() if x.i1 == i - 1 and x.kind == "col"]
            if self.t[i - 1].low == "in" and prev and any(c in prev[0].cands for c in ucols):
                self._use(i - 1, i + 1, "unit")
            elif self.t[i - 1].low == "per" and len(ucols) == 1:
                mm = Mention(i, i + 1, "col", [ucols[0]], t.text); mm.score = 1
                self.G.mentions.append(mm)
                self._use(i, i + 1, "col")
        self.G.mentions.sort(key=lambda x: x.i0)

    # ------------------------------------------------------------------ assembly
    def _near(self, rx: str, i0: int, i1: int, before: int = 4, after: int = 0) -> Optional[re.Match]:
        s = self.t[max(0, i0 - before)].s if before else self.t[i0].s
        e = self.t[min(len(self.t), i1 + after) - 1].e if after else self.t[i0].s
        return re.search(rx, self.ql[s:e] if before else self.ql[self.t[i1 - 1].e:e])

    def _neg_before(self, i0: int, window: int = 5) -> Optional[Tuple[int, int]]:
        lo = max(0, i0 - window)
        seg_s, seg_e = self.t[lo].s, self.t[i0].s
        best = None
        for m in re.finditer(NEG_CUES, self.ql[seg_s:seg_e]):
            mid = self.ql[seg_s + m.end():seg_e]
            if re.search(r"\b(?:and|but|or|,|which|that)\b|,", mid) and not re.match(r"\s*(?:\w+\s+){0,1}$", mid):
                continue
            best = self._span(seg_s + m.start(), seg_s + m.end())
        return best

    def _choose_path(self, ents, i0: int, i1: int):
        """Several candidates for one mention: keep those whose role / table words appear next to it."""
        if len({e.key if hasattr(e, "key") else (e.table, e.column, e.path and e.path.role) for e in ents}) <= 1:
            return ents[0], None
        near = {self.t[j].can for j in range(max(0, i0 - 3), min(len(self.t), i1 + 3))}
        best = []
        for e in ents:
            p = e.path
            rw = set(L._role_words(p, e.table)) if p is not None else set()
            cw = set(self.m.col(e.table, e.column).words) if hasattr(e, "column") else set()
            tw = set(self.lex.model and [w for w in (canon(x) for x in re.split(r"[^a-z0-9]+", e.table.lower())) if w])
            hit = len(rw & near) * 2 + len((cw | tw) & near)
            best.append((hit, e))
        best.sort(key=lambda x: -x[0])
        if best[0][0] > 0 and (len(best) == 1 or best[0][0] > best[1][0]):
            w = best[0][1]
            for j in range(max(0, i0 - 3), min(len(self.t), i1 + 3)):
                if self.t[j].can in (set(L._role_words(w.path, w.table)) if w.path else set()) | \
                        set(self.m.col(w.table, w.column).words if hasattr(w, "column") and w.column else []) | {canon(x) for x in w.table.split("_")}:
                    self.ctx.add(j)
                    if j not in self.used:
                        self.used[j] = "context"
            return w, None
        labels = [f"{getattr(e, 'table', '')}.{getattr(e, 'column', '')}" + (f" via {e.path.role}" if e.path is not None and e.path.role else "") for e in ents]
        key = f"path:{i0}:{i1}"
        if key in self.prefer and self.prefer[key] < len(ents):
            return ents[self.prefer[key]], None
        if key not in {k for k, _ in self.Q.choices}:
            self.Q.choices.append((key, tuple(labels)))
        return None, labels

    def _pred_for(self, e, p) -> object:
        """Wrap a predicate on a column of `e`'s table: EXISTS when the table is reached one-to-many."""
        if e.path is not None and e.path.fans_out:
            return Exists(e.path, p if not isinstance(p, InSet) or not p.negated else InSet(p.col, p.values, False))
        return p

    def _assemble(self) -> None:
        Q, m = self.Q, self.m
        ql = self.ql
        conds: List[Tuple[int, object]] = []          # (token position, predicate)
        cols_m = [x for x in self.G.mentions if x.kind == "col"]
        tabs_m = [x for x in self.G.mentions if x.kind == "table"]
        vals_m = [x for x in self.G.mentions if x.kind == "value"]

        # values -> equality / exclusion (EXISTS for one-to-many tables)
        groups: Dict[str, List] = {}
        for vm in vals_m:
            ents = vm.cands
            by_col = {}
            for e in ents:
                by_col.setdefault((e.table, e.column, e.path.role if e.path else "", id(e.path)), e)
            ents = list(by_col.values())
            e, amb = self._choose_path(ents, vm.i0, vm.i1)
            if e is None:
                Q.ambiguities.append(f"'{vm.text}' could be " + " or ".join(amb))
                continue
            for cm in self.G.mentions:
                if cm.kind == "col" and cm.i0 == vm.i1 and any((c.table, c.column) == (e.table, e.column) for c in cm.cands):
                    cm.ctx = True
            neg = self._neg_before(vm.i0)
            if neg:
                self._use(*neg, "negation")
            col = Col(e.table, e.column, e.path if e.path and not e.path.fans_out else e.path)
            groups.setdefault((col.key(), bool(neg), id(e.path)), []).append((vm, e, col))
        for (_k, neg, _p), items in groups.items():
            vm, e, col = items[0]
            vals = tuple(dict.fromkeys(x[1].text for x in items))
            if e.path is not None and e.path.fans_out:
                inner = InSet(Col(e.table, e.column, None), vals)
                p = Exists(e.path, inner, negated=neg)
            else:
                p = InSet(col, vals, negated=neg)
                if neg:
                    Q.assumptions.append(f"rows with no {e.column} are kept when excluding {', '.join(vals)}")
            conds.append((vm.i0, p))
            self._ev(vm.i0, items[-1][0].i1, f"{e.table}.{e.column} {'NOT IN' if neg else 'IN'} {vals}", "stored value")

        # columns: classify by kind and context
        measures_c, dims_c, dates_c, bools_c, ids_c = [], [], [], [], []
        for cm in cols_m:
            if getattr(cm, "ctx", False):
                continue
            e, amb = self._choose_path(cm.cands, cm.i0, cm.i1)
            if e is None:
                # several columns share these words; a measure context may still decide later
                kinds = {m.col(x.table, x.column).kind for x in cm.cands}
                cm.amb = amb
                if kinds == {"measure"}:
                    measures_c.append(cm)
                elif kinds == {"date"}:
                    dates_c.append(cm)
                else:
                    Q.ambiguities.append(f"'{cm.text}' could be " + " or ".join(amb))
                continue
            cm.e = e; cm.amb = None
            k = m.col(e.table, e.column).kind
            if getattr(cm, "unneg", False) and k not in ("boolean", "date"):
                Q.unresolved.append(f"'{cm.text}' negates {e.column}, which is not a yes/no or date column")
                continue
            {"measure": measures_c, "date": dates_c, "boolean": bools_c, "id": ids_c}.get(k, dims_c).append(cm)

        # booleans -> conditions with polarity
        for bm in bools_c:
            e = bm.e
            words = set(m.col(e.table, e.column).words)
            pol = bool(words & POLARITY)
            neg = self._neg_before(bm.i0, 4)
            v = 1
            ant = self._near(ANTONYM, bm.i0, bm.i1, before=3) or (re.search(ANTONYM, ql[self.t[bm.i1 - 1].e:self.t[min(len(self.t), bm.i1 + 2) - 1].e]) if bm.i1 < len(self.t) else None)
            if pol:
                has_word = bool(words & POLARITY & {self.t[j].can for j in range(bm.i0, bm.i1)}) or \
                    any(participle(self.t[j].low) and self.t[j].can in words for j in range(bm.i0, bm.i1)) or \
                    bool(getattr(bm, "unneg", False))
                posw = self._near(POSITIVE, bm.i0, bm.i1, before=3)
                if ant:
                    v = 0
                elif not (has_word or posw):
                    Q.ambiguities.append(f"'{bm.text}' does not say which value of {e.column} is meant")
                    continue
            if neg:
                v = 1 - v
                self._use(*neg, "negation")
            if getattr(bm, "unneg", False):
                v = 1 - v                              # "unpaid", "unresolved"
            if ant:
                for j in range(max(0, bm.i0 - 3), min(len(self.t), bm.i1 + 2)):
                    if re.fullmatch(ANTONYM.replace(r"\b", ""), self.t[j].low):
                        self.used.setdefault(j, "polarity")
            if re.match(r"^\s*(?:[a-z]+\s+)?(?:included|as\s+well|too)\b", ql[self.t[bm.i1 - 1].e:]) or \
                    re.search(r"\b(?:including|incl|plus|even)\s+(?:the\s+|all\s+)?$", ql[:self.t[bm.i0].s]):
                self._ev(bm.i0, bm.i1, f"{e.column}: no condition", "inclusion phrase ('... included')")
                for j in range(bm.i1, min(len(self.t), bm.i1 + 3)):
                    if self.t[j].low in ("included", "too", "well", "as", "ones"):
                        self.used.setdefault(j, "inclusion")
                continue
            p = self._pred_for(e, Cmp(Col(e.table, e.column, None if e.path and e.path.fans_out else e.path), "=", Lit(v)))
            if isinstance(p, Exists) and neg:
                p = Exists(e.path, Cmp(Col(e.table, e.column, None), "=", Lit(1 - v)), False)
            conds.append((bm.i0, p))
            self._ev(bm.i0, bm.i1, f"{e.table}.{e.column} = {v}", "0/1 column" + (" (negated)" if neg else ""))

        # NULL conditions on any mentioned column (incl. FK ids and table nouns of parents)
        def null_check(mm, col_e, is_table=False):
            after = ql[self.t[mm.i1 - 1].e:]
            before = ql[:self.t[mm.i0].s]
            nn = re.match(NOTNULL_AFTER, after)
            isn = re.match(NULL_AFTER, after) or re.search(NULL_BEFORE, before)
            if not (isn or nn):
                return None
            negated = bool(nn and not isn)
            outer = re.search(r"\b(?:skip|skipping|leave\s+out|leaving\s+out|exclude|excluding|ignore|ignoring|omit|without|except)\b[^.?]{0,60}$", before[:self.t[mm.i0].s])
            if outer and isn:
                negated = not negated
            for rx, where in ((NULL_AFTER, "after"), (NOTNULL_AFTER, "after"), (NULL_BEFORE, "before")):
                mt = re.match(rx, after) if where == "after" else re.search(rx, before)
                if mt:
                    s0 = self.t[mm.i1 - 1].e + mt.start() if where == "after" else mt.start()
                    s1 = self.t[mm.i1 - 1].e + mt.end() if where == "after" else mt.end()
                    a, b = self._span(s0, s1)
                    if a >= 0:
                        for j in range(a, b):
                            self.used.setdefault(j, "null")
            return IsNull(Col(col_e.table, col_e.column, col_e.path), negated)

        for cm in [c for c in cols_m if getattr(c, "e", None) is not None]:
            k = m.col(cm.e.table, cm.e.column).kind
            if k == "boolean":
                continue
            p = null_check(cm, cm.e)
            if p is not None:
                if cm.e.path is not None and cm.e.path.fans_out:
                    Q.unsupported.append(f"a missing value on the one-to-many table {cm.e.table}")
                    continue
                if cm.e.path is not None and cm.e.path.steps[-1][0].nullable:
                    Q.unsupported.append(f"'{cm.text}' is missing either when {cm.e.table} has no row or when the value is empty; these cannot be told apart")
                    continue
                conds.append((cm.i0, p)); cm.null = True
                self._ev(cm.i0, cm.i1, f"{cm.e.table}.{cm.e.column} IS {'NOT ' if p.negated else ''}NULL", "missing-value phrasing")
        for tm in tabs_m:
            te = tm.cands[0]
            if te.path is None or te.path.fans_out or len(te.path.steps) != 1:
                continue
            fk = te.path.steps[0][0]
            fake = L.ColEntry(m.anchor, fk.child_col, None, [], [], "id")
            p = null_check(tm, fake, True)
            if p is not None:
                conds.append((tm.i0, p)); tm.null = True
                self._ev(tm.i0, tm.i1, f"{m.anchor}.{fk.child_col} IS {'NOT ' if p.negated else ''}NULL", "no linked " + te.table)

        timed = bool(self.G.periods) or any(re.search(rx, ql) for rx, _u in BUCKET_CUES)
        # existence of related rows on a one-to-many table ("had an issue", "with no tags", "were returned")
        for tm in tabs_m:
            tes = [te for te in tm.cands if te.path is not None and te.path.fans_out]
            if not tes or len({te.table for te in tes}) > 1 or getattr(tm, "null", False):
                continue
            te = tes[0]
            pre = ql[self.t[max(0, tm.i0 - 3)].s:self.t[tm.i0].s]
            cue = re.search(r"\b(?:with|had|has|have|having|without|no|any|an?|least\s+one|one\s+or\s+more|some)\s+(?:any\s+|an?\s+)?$", pre)
            verb = any(participle(self.t[j].low) for j in range(tm.i0, tm.i1))
            if not (cue or verb):
                continue
            if any(isinstance(p, Exists) and p.path == te.path for _pos, p in conds):
                tm.cond = True                         # a condition on that table already says it
                continue
            neg = self._neg_before(tm.i0, 4)
            if neg:
                self._use(*neg, "negation")
            conds.append((tm.i0, Exists(te.path, None, negated=bool(neg))))
            tm.cond = True
            self._ev(tm.i0, tm.i1, f"{'NOT ' if neg else ''}EXISTS {te.table}", "related rows (one-to-many)")
        # verb forms of date columns without a period: 'not shipped' -> ship date IS NULL
        for cm in [c for c in dates_c if getattr(c, "e", None) is not None]:
            e = cm.e
            if timed or not any(participle(self.t[j].low) for j in range(cm.i0, cm.i1)):
                continue
            if any(self.t[j].text[:1].isupper() and j > 0 for j in range(cm.i0, cm.i1)):
                Q.unresolved.append(f"'{cm.text}' looks like part of a name, not a statement about {cm.e.column}")
                cm.cond = True
                continue
            if e.path is not None and (e.path.fans_out or e.path.steps[-1][0].nullable):
                continue
            col = m.col(e.table, e.column)
            neg = self._neg_before(cm.i0, 4) or (getattr(cm, "unneg", False) and (cm.i0, cm.i0))
            nullable = col.n_null > 0 or not col.not_null
            if neg and nullable:
                self._use(*neg, "negation")
                conds.append((cm.i0, IsNull(self._col(e), False))); cm.cond = True
                self._ev(cm.i0, cm.i1, f"{e.table}.{e.column} IS NULL", "event has not happened (no date)")
            elif not neg and nullable:
                conds.append((cm.i0, IsNull(self._col(e), True))); cm.cond = True
                self._ev(cm.i0, cm.i1, f"{e.table}.{e.column} IS NOT NULL", "event has happened (date present)")
            elif not neg:
                cm.cond = True                         # every row has this date: descriptive only
                self._ev(cm.i0, cm.i1, f"{e.table}.{e.column}: no condition", "every row has this date")
        # verb forms of count columns: 'never reopened' -> reopen_cnt = 0
        for cm in [c for c in measures_c if getattr(c, "e", None) is not None]:
            e = cm.e
            col = m.col(e.table, e.column)
            if canon("count") not in col.words or not any(participle(self.t[j].low) for j in range(cm.i0, cm.i1)):
                continue
            if e.path is not None and e.path.fans_out:
                continue
            neg = self._neg_before(cm.i0, 4)
            if neg:
                self._use(*neg, "negation")
            conds.append((cm.i0, Cmp(self._col(e), "=" if neg else ">", Lit(0)))); cm.cond = True
            self._ev(cm.i0, cm.i1, f"{e.table}.{e.column} {'=' if neg else '>'} 0", "verb form of a count column")

        # numeric comparisons -> nearest numeric column (measure) by position, or by unit
        for n in self.nums:
            if not n["explicit"]:
                continue
            best = None
            for cm in measures_c:
                if getattr(cm, "e", None) is None:
                    continue
                d = min(abs(cm.i1 - n["i0"]), abs(n["i1"] - cm.i0))
                if best is None or d < best[0]:
                    best = (d, cm)
            unit_tok = self.t[n["num_i"] + 1].can if n["num_i"] + 1 < len(self.t) else ""
            if unit_tok in UNITS and (n["num_i"] + 1) not in self.used and not (best and best[1].e is not None and
                    m.col(best[1].e.table, best[1].e.column).unit and canon(m.col(best[1].e.table, best[1].e.column).unit) == unit_tok):
                best = None                            # '30 minutes' names its column by unit, whatever is nearer
            if best is None or best[0] > 4:
                ucols = [c for c in self.lex.cols if m.col(c.table, c.column).kind == "measure" and m.col(c.table, c.column).unit
                         and canon(m.col(c.table, c.column).unit) == unit_tok]
                if len(ucols) == 1:
                    e = ucols[0]
                    cm = Mention(n["num_i"], n["num_i"] + 1, "col", [e], self._text(n["num_i"], n["num_i"] + 2)); cm.e = e
                    best = (0, cm)
                    self.used.setdefault(n["num_i"] + 1, "unit")
            if best is not None and best[0] > 1 and not any(m.col(best[1].e.table, best[1].e.column).unit and
                                                            canon(m.col(best[1].e.table, best[1].e.column).unit) == unit_tok for _ in [0]):
                best = None                            # "enrollments over 2000": over 2000 of what?
            if best is None or best[0] > 4:
                Q.unresolved.append(f"the number {n['value']:g} is not attached to a numeric column")
                continue
            cm = best[1]; cm.cmp = True; e = cm.e
            if n["num_i"] + 1 < len(self.t) and m.col(e.table, e.column).unit and \
                    self.t[n["num_i"] + 1].can in (canon(m.col(e.table, e.column).unit), canon(m.col(e.table, e.column).unit) + "s"):
                self.used.setdefault(n["num_i"] + 1, "unit")
            val = int(n["value"]) if n["value"] == int(n["value"]) else n["value"]
            p = self._pred_for(e, Cmp(Col(e.table, e.column, None if e.path and e.path.fans_out else e.path), n["op"], Lit(val)))
            conds.append((n["i0"], p))
            self._ev(n["i0"], n["i1"], f"{e.table}.{e.column} {n['op']} {val}", "comparison")

        # dates: role
        anchor_dates = [c for c in m.tables[m.anchor].values() if c.kind == "date"]
        named = [cm for cm in dates_c if getattr(cm, "e", None) is not None]
        role_col = None
        if named:
            roles = {(x.e.table, x.e.column) for x in named}
            if len(roles) == 1:
                role_col = self._col(named[0].e)
        if role_col is None and len(anchor_dates) == 1:
            role_col = Col(m.anchor, anchor_dates[0].name, None)
        if role_col is None and not named:
            # verbs that name a date column ("signed" -> signed_dt)
            hits = []
            for c in anchor_dates:
                core = [w for w in c.words if w not in L.GENERIC]
                for j, t in enumerate(self.t):
                    if j not in self.used and core and t.can in core:
                        hits.append((c, j))
            if len({c.name for c, _ in hits}) == 1:
                role_col = Col(m.anchor, hits[0][0].name, None)
                for _c, j in hits:
                    self.used[j] = "date role"
        role_default = None     # several date columns: never pick one silently (see GROUNDING_DESIGN.md, date roles)
        cands = [Col(m.anchor, c.name, None) for c in anchor_dates]
        if self.G.periods and not named:
            p0 = self.G.periods[0].i0
            for tm in tabs_m:
                te = tm.cands[0]
                if te.path is not None and not te.path.fans_out and 0 <= p0 - tm.i1 <= 2:
                    cands += [Col(te.table, c.name, te.path) for c in m.tables[te.table].values() if c.kind == "date"]
        if len(cands) > len(anchor_dates) and role_col is not None and not named:
            role_col = None                         # "events held in March": the event's date is a candidate too
        if role_col is None and "date" in self.prefer and self.prefer["date"] < len(cands):
            role_col = cands[self.prefer["date"]]   # one reading of a date ambiguity
        date_labels = tuple(f"{c.table}.{c.column}" if c.path is not None else c.column for c in cands)
        periods = self.G.periods
        bucketed = any(re.search(rx, ql) for rx, _u in BUCKET_CUES)
        comparing = len(periods) >= 2 and re.search(COMPARE, ql) and not bucketed   # "2023 vs 2024, each year": a series

        # ---------------- measures
        aggs = []
        for rx, fn in AGG_CUES:
            for mt in re.finditer(rx, ql):
                i0, i1 = self._span(mt.start(), mt.end())
                if i0 >= 0 and self._free(i0, i1):
                    aggs.append((i0, i1, fn))
        aggs.sort()
        distinct = re.search(DISTINCT_CUE, ql)
        pct = next((mt for mt in re.finditer(PCT_CUE, ql) if self._free(*self._span(mt.start(), mt.end()))), None)

        def take(i0, i1, why):
            self._use(i0, i1, why)

        def additive(e) -> bool:
            c = m.col(e.table, e.column)
            raw = set(re.split(r"[^a-z0-9]+", c.name.lower()))
            return c.kind == "measure" and not ({canon(x) for x in raw} & {canon(x) for x in (
                "rating", "rate", "score", "percent", "pct", "ratio", "temperature", "avg", "average", "age", "price")}
                or raw & {"lat", "lon", "lng"})

        gtargets = self._group_targets()
        meas_free = [cm for cm in measures_c if not (getattr(cm, "cmp", False) or getattr(cm, "null", False)
                                                     or getattr(cm, "cond", False) or id(cm) in gtargets)]
        # explicit products / ratios between measure mentions
        expr_pairs = []
        for a, b in zip(meas_free, meas_free[1:]):
            mid = ql[self.t[a.i1 - 1].e:self.t[b.i0].s]
            if re.fullmatch(r"\s*(?:times|multiplied\s+by|x|\*)\s*(?:the\s+)?", mid):
                expr_pairs.append(("*", a, b, mid))
            elif re.fullmatch(r"\s*(?:divided\s+by|over|/|per)\s*(?:the\s+)?(?:total\s+)?", mid):
                expr_pairs.append(("/", a, b, mid))
            elif re.fullmatch(r"\s*(?:minus|less|-)\s*(?:the\s+)?(?:total\s+)?", mid):
                expr_pairs.append(("-", a, b, mid))
            elif re.fullmatch(r"\s*(?:plus|\+)\s*(?:the\s+)?(?:total\s+)?", mid):
                expr_pairs.append(("+", a, b, mid))

        def ent(cm):
            if getattr(cm, "e", None) is not None:
                return cm.e
            return None

        cue = None
        if aggs:
            cue = aggs[0]
        measure: Optional[Measure] = None
        if expr_pairs:
            op, a, b, mid = expr_pairs[0]
            ea, eb = ent(a), ent(b)
            if ea is None or eb is None:
                Q.ambiguities.append("an operand of the expression is ambiguous")
            elif any(x.path is not None and x.path.fans_out for x in (ea, eb)):
                Q.unsupported.append("an expression over a one-to-many table")
            else:
                ca, cb = self._col(ea), self._col(eb)
                for j in range(a.i1, b.i0):
                    self.used.setdefault(j, "operator")
                fn = cue[2] if cue else None
                if op == "*":
                    if fn in (None, "sum", "count"):
                        measure = Measure(f"sum_{ea.column}_x_{eb.column}", Agg("sum", Arith("*", ca, cb)), None)
                        if fn is None:
                            Q.assumptions.append("the product is summed over the rows")
                    elif fn == "avg":
                        measure = Measure(f"avg_{ea.column}_x_{eb.column}", Agg("avg", Arith("*", ca, cb)))
                    self._ev(a.i0, b.i1, f"SUM({ea.column} * {eb.column})", "product computed per row, then aggregated")
                elif op == "/":
                    measure = Measure(f"{ea.column}_per_{eb.column}", Arith("/", Agg("sum", ca), Agg("sum", cb)))
                    self._ev(a.i0, b.i1, f"SUM({ea.column}) / SUM({eb.column})", "ratio of totals as stated")
                else:
                    if fn not in (None, "sum"):
                        Q.unsupported.append(f"{fn} of a sum or difference")
                    else:
                        word = "minus" if op == "-" else "plus"
                        measure = Measure(f"{ea.column}_{word}_{eb.column}", Arith(op, Agg("sum", ca), Agg("sum", cb)))
                        self._ev(a.i0, b.i1, f"SUM({ea.column}) {op} SUM({eb.column})", "totals combined as stated")
                        if any(m.col(x.table, x.column).n_null for x in (ea, eb)):
                            Q.assumptions.append("missing values count as nothing in each total")
                if cue:
                    take(cue[0], cue[1], "aggregation")
                for x in (a, b):
                    x.used_as_measure = True
        if measure is None:
            # the measure column the cue refers to: the next measure mention after the cue, else the nearest one
            cm = None
            if cue:
                after = [x for x in meas_free if x.i0 >= cue[1]]
                before = [x for x in meas_free if x.i1 <= cue[0]]
                cm = after[0] if after else (before[-1] if before else None)
            elif len(meas_free) == 1:
                cm = meas_free[0]
            elif len(meas_free) > 1:
                cm = meas_free[0]
            if cm is not None and cue and cue[2] == "count" and any(cue[1] <= x.i0 < cm.i0 for x in tabs_m):
                cm = None                              # "how many tickets have ... <measure>": rows are counted
            if cm is not None and ent(cm) is None:
                # ambiguous measure words; still ambiguous
                Q.ambiguities.append(f"'{cm.text}' could be " + " or ".join(cm.amb))
                cm = None
            fn = cue[2] if cue else None
            if cm is not None:
                e = ent(cm)
                if e.path is not None and e.path.fans_out:
                    Q.unsupported.append(f"a measure on the one-to-many table {e.table} (needs that table as the base)")
                elif e.path is not None and fn in ("sum", "avg", None, "count"):
                    Q.ambiguities.append(f"{e.column} describes {e.table}; aggregate it over {e.table} itself, or once per "
                                         f"{m.anchor} row (weighted by {m.anchor})?")
                else:
                    c = self._col(e)
                    if fn in ("max", "min", "avg", "sum"):
                        measure = Measure(f"{fn}_{e.column}", Agg(fn, c), m.col(e.table, e.column).unit)
                        take(cue[0], cue[1], "aggregation")
                    elif fn == "count":
                        # "how many units / kWh / minutes": the quantity is summed, never counted
                        if not m.col(e.table, e.column).money:
                            measure = Measure(f"sum_{e.column}", Agg("sum", c), m.col(e.table, e.column).unit)
                            take(cue[0], cue[1], "aggregation")
                            self._ev(cue[0], cm.i1, f"SUM({e.column})", "'how many <quantity>' sums the quantity")
                        else:
                            Q.ambiguities.append(f"'how many' with the money column {e.column}: a count of rows or a sum?")
                    elif fn is None:
                        if additive(e):
                            measure = Measure(f"sum_{e.column}", Agg("sum", c), m.col(e.table, e.column).unit)
                            Q.assumptions.append(f"{e.column} is summed (no aggregation word was given)")
                        else:
                            Q.unresolved.append(f"no aggregation was stated for {e.column}, which is not additive")
                    cm.used_as_measure = True
                    if measure:
                        self._ev(cm.i0, cm.i1, f"{measure.expr.func.upper()}({e.table}.{e.column})" if isinstance(measure.expr, Agg) else str(measure.expr), "measure column")
        # counts of rows or entities
        if measure is None and (cue and cue[2] == "count" or (distinct and not meas_free)):
            target = None
            after_t = [x for x in tabs_m if (cue is None or x.i0 >= cue[1]) and not getattr(x, "null", False)
                       and not getattr(x, "cond", False) and id(x) not in self.group_claimed]
            after_c = [x for x in dims_c + ids_c if (cue is None or x.i0 >= cue[1]) and getattr(x, "e", None) is not None
                       and not getattr(x, "null", False) and id(x) not in self.group_claimed]
            if distinct and (after_c or after_t):
                nxt = sorted(after_c + after_t, key=lambda x: x.i0)[0]
                if nxt.kind == "col":
                    e = nxt.e
                    if e.path is not None and e.path.fans_out:
                        Q.unsupported.append(f"distinct count over the one-to-many table {e.table}")
                    else:
                        measure = Measure(f"distinct_{e.column}", Agg("count_distinct", self._col(e)))
                        nxt.used_as_measure = True
                else:
                    te = nxt.cands[0]
                    if te.path is None:
                        measure = Measure("row_count", Agg("count"))
                    elif not te.path.fans_out and len(te.path.steps) == 1:
                        fk = te.path.steps[0][0]
                        measure = Measure(f"distinct_{fk.child_col}", Agg("count_distinct", Col(m.anchor, fk.child_col, None)))
                    else:
                        Q.unsupported.append(f"counting {te.table} from {m.anchor}")
                    nxt.used_as_measure = True
                distinct_span = self._span(distinct.start(), distinct.end())
                take(*distinct_span, "distinct")
            elif after_t:
                te = after_t[0].cands[0]
                if te.path is None:
                    measure = Measure("row_count", Agg("count"))
                elif not te.path.fans_out and len(te.path.steps) == 1 and not self._linked(after_t[0]) and not conds:
                    Q.ambiguities.append(f"'{after_t[0].text}': all {te.table} in the data, or only those that appear in "
                                         f"{m.anchor}?")
                elif not te.path.fans_out and len(te.path.steps) == 1:
                    fk = te.path.steps[0][0]
                    measure = Measure(f"distinct_{fk.child_col}", Agg("count_distinct", Col(m.anchor, fk.child_col, None)))
                    Q.assumptions.append(f"'{after_t[0].text}' counted as distinct {fk.child_col} values on {m.anchor}")
                else:
                    Q.unsupported.append(f"counting {te.table} rows from {m.anchor}")
                after_t[0].used_as_measure = True
            else:
                measure = Measure("row_count", Agg("count"))
                Q.assumptions.append(f"counting {m.anchor} rows")
            if cue:
                take(cue[0], cue[1], "aggregation")
            if measure:
                self._ev(cue[0] if cue else 0, cue[1] if cue else 0, measure.expr.func.upper(), "count")
        if measure is None and not Q.unsupported and not Q.ambiguities:
            # a bare anchor noun with a percentage / grouping and no measure ("share of orders by city")
            if not meas_free and not aggs:
                aw = set(table_words(m.anchor))
                if any(x.cands[0].path is None or aw <= set(x.cands[0].words) for x in tabs_m):
                    measure = Measure("row_count", Agg("count"))
                    Q.assumptions.append(f"counting {m.anchor} rows")
        if measure is None and not Q.unsupported:
            Q.unresolved.append("no measure could be grounded")

        # ---------------- percentages / shares
        grouping = self._grouping(dims_c, tabs_m, ids_c)
        if pct and measure is not None:
            ps, pe = self._span(pct.start(), pct.end())
            take(ps, pe, "percentage")
            if grouping:
                Q.share_of_total = True
                self._ev(ps, pe, "share of the grand total per group", "percentage with grouping")
            else:
                # conditions stated after the subject ('of delivered orders') are the numerator condition
                pivot = self._pct_pivot(ps)
                num = [p for pos, p in conds if pos >= pivot]
                base = [p for pos, p in conds if pos < pivot]
                if not num:
                    Q.unresolved.append("the percentage has no condition for its numerator")
                else:
                    w = num[0] if len(num) == 1 else BoolOp("and", tuple(num))
                    ex = measure.expr
                    if isinstance(ex, Agg) and ex.func in ("sum", "count"):
                        numer = Agg(ex.func, ex.arg, w)
                        measure = Measure("percent", Arith("*", Lit(100.0), Arith("/", numer, ex)), "percent")
                        conds = [(0, p) for p in base]
                        self._ev(ps, pe, "100 * (with condition) / (all)", "percentage of rows or of a total")
                    else:
                        Q.unsupported.append("a percentage of a non-additive measure")

        # ---------------- periods
        filters = [p for _pos, p in conds]
        if periods:
            if role_col is None:
                if len(cands) > 1:
                    Q.ambiguities.append("the question gives a period but not which date: " + ", ".join(date_labels))
                    Q.choices.append(("date", date_labels))
                elif not anchor_dates:
                    Q.unsupported.append("no date column on the base table")
            elif comparing and measure is not None and isinstance(measure.expr, Agg) and measure.expr.where is None:
                ms = []
                for p in periods[:2]:
                    w = BoolOp("and", (Cmp(role_col, ">=", Lit(p.lo)), Cmp(role_col, "<", Lit(p.hi))))
                    ms.append(Measure(f"{measure.name}_{re.sub(r'[^a-z0-9]+', '_', p.label)}", Agg(measure.expr.func, measure.expr.arg, w), measure.unit))
                Q.measures = ms
                if re.search(r"\b(?:minus|difference|change[ds]?|differ|more|fewer|less|how\s+much\s+(?:higher|lower))\b", ql):
                    later = max(periods[:2], key=lambda p: p.lo) if not re.search(r"\(\s*\w+\s+minus", ql) else periods[0]
                    other = [p for p in periods[:2] if p is not later][0]
                    li = periods.index(later)
                    Q.measures.append(Measure("difference", Arith("-", ms[li].expr, ms[1 - li].expr), measure.unit))
                    Q.assumptions.append(f"difference = {later.label} minus {other.label}")
                for mt in re.finditer(COMPARE, ql):
                    a, b = self._span(mt.start(), mt.end())
                    take(a, b, "comparison")
                self._ev(periods[0].i0, periods[1].i1, f"{role_col.column}: {periods[0].label} vs {periods[1].label}", "period comparison")
                measure = None
            else:
                lo = min(p.lo for p in periods); hi = max(p.hi for p in periods)
                if bucketed and len(periods) > 1:
                    for mt in re.finditer(r"\b(?:vs\.?|versus|compared?\s+(?:to|with)|and)\b", ql):
                        a, b = self._span(mt.start(), mt.end())
                        if a >= 0 and self._free(a, b):
                            take(a, b, "periods shown as a series")
                    Q.assumptions.append("the named periods are shown as one series over their full range")
                if len(periods) > 1 and not bucketed and not re.search(r"\b(?:from|through|to|until|between|thru)\b", ql):
                    Q.ambiguities.append("several periods are named; a comparison or a range?")
                filters.append(BoolOp("and", (Cmp(role_col, ">=", Lit(lo)), Cmp(role_col, "<", Lit(hi)))))
                self._ev(periods[0].i0, periods[-1].i1, f"{role_col.column} in [{lo}, {hi})", "period on the chosen date column")
        if measure is not None:
            Q.measures = [measure]
        Q.filters = filters + self.extra
        if role_default is not None and (periods or any(re.search(rx, ql) for rx, _u in BUCKET_CUES)):
            Q.assumptions.append(f"dates refer to {role_default.column}, the only date every {m.anchor} row has")

        # ---------------- grouping, time buckets, ranking
        Q.group_by = grouping
        for rx, unit in BUCKET_CUES:
            mt = re.search(rx, ql)
            if mt:
                a, b = self._span(mt.start(), mt.end())
                if a >= 0 and self._free(a, b):
                    if role_col is None:
                        if len(cands) > 1:
                            Q.ambiguities.append(f"'{mt.group(0)}' does not say which date: " + ", ".join(date_labels))
                            if ("date", date_labels) not in Q.choices:
                                Q.choices.append(("date", date_labels))
                        else:
                            Q.unsupported.append("no date column for a time series")
                    else:
                        Q.time_bucket = (role_col, unit)
                        self._ev(a, b, f"{unit} of {role_col.column}", "time series")
                        if re.fullmatch(r"over\s+time|trend\w*", mt.group(0)):
                            Q.assumptions.append("no time unit was stated; shown by month")
                    take(a, b, "time bucket")
                break
        if self.limits:
            n, a, b, txt = self.limits[0]
            Q.limit = n
            for g in Q.group_by:
                if m.col(g.table, g.column).n_null or (g.path is not None and any(st[0].nullable for st in g.path.steps)):
                    Q.filters.append(IsNull(g, True))
                    Q.assumptions.append(f"rows with no {g.column} are not ranked")
            Q.order_desc = not re.search(RANK_ASC, txt)
            if not Q.group_by:
                Q.unresolved.append(f"'{txt}' ranks something, but no group was grounded")
        rk = re.search(r"\b(?:the\s+)?(most|highest|largest|biggest|least|lowest|smallest|fewest)\b", ql)
        if rk:
            a, b = self._span(rk.start(), rk.end())
            if a >= 0 and self._free(a, b) and Q.group_by:
                Q.order_desc = rk.group(1) in ("most", "highest", "largest", "biggest")
                if Q.limit is None and re.search(r"\bwhich\s+\w+", ql) and not re.search(r"\beach\b|\bevery\b", ql):
                    Q.limit = 1
                take(a, b, "ranking")
        Q.shape = "ranked" if Q.limit else "series" if Q.time_bucket else "grouped" if Q.group_by else "scalar"

    def _avg_cue(self) -> bool:
        return bool(re.search(r"\baverage\b|\bavg\b|\bmean\b|\btypical\b", self.ql))

    def _linked(self, x) -> bool:
        """Words after an entity noun that tie it to the base rows: 'customers who placed orders', 'members that
        borrowed', 'riders with rentals', or the base table's own noun anywhere in the question."""
        if any(y.kind == "table" and y.cands[0].path is None for y in self.G.mentions):
            return True
        nxt = [t.low for t in self.t[x.i1:x.i1 + 2]]
        return bool(nxt) and (nxt[0] in ("who", "that", "which", "with", "having") or participle(nxt[0]))

    def _agentive(self, a: int, b: int) -> bool:
        """'taken by students', 'opened by Ava': a participle before a bare 'by' names who did it, not a grouping."""
        return b - a == 1 and self.t[a].low == "by" and a > 0 and participle(self.t[a - 1].low)

    def _group_targets(self) -> Set[int]:
        """Small-range integer columns named right after a grouping cue ('by grade level') when something else is
        being measured: they label groups and are not the measure."""
        out = set()
        has_cue = any(re.search(rx, self.ql) for rx, fn in AGG_CUES if fn == "count")
        self.group_claimed = set()
        for mt in re.finditer(GROUP_CUES, self.ql):
            a, b = self._span(mt.start(), mt.end())
            if a < 0 or not self._free(a, b) or self._agentive(a, b):
                continue
            nxt = [x for x in self.G.mentions if b <= x.i0 <= b + 3 and x.kind in ("col", "table") and not getattr(x, "ctx", False)]
            if nxt:
                self.group_claimed.add(id(nxt[0]))
            if not nxt or nxt[0].kind != "col" or getattr(nxt[0], "e", None) is None:
                continue
            x = nxt[0]
            others = [y for y in self.G.mentions if y is not x and y.kind == "col" and getattr(y, "e", None) is not None
                      and self.m.col(y.e.table, y.e.column).kind == "measure"]
            if ordinal(self.m.col(x.e.table, x.e.column)) and (has_cue or others):
                out.add(id(x))
        return out

    def _pct_pivot(self, pct_tok: int) -> int:
        """Token index after the subject of 'percentage of <subject> <verb> ...'."""
        for j in range(pct_tok, len(self.t)):
            if self.t[j].low in ("were", "was", "are", "is", "had", "have", "has", "got", "did", "that", "which", "came",
                                 "come", "arrived", "went", "ended", "showed", "turned") and j > pct_tok + 1:
                return j
        return pct_tok

    def _grouping(self, dims_c, tabs_m, ids_c) -> List[Col]:
        out = []
        ql = self.ql
        spans = []
        for mt in re.finditer(GROUP_CUES, ql):
            a, b = self._span(mt.start(), mt.end())
            if a >= 0 and self._free(a, b) and not self._agentive(a, b):
                spans.append((a, b, 3))
        for _n, a, b, _txt in self.limits:      # "top 3 start stations": the ranked entity is the group
            spans.append((a, b, 0))
        for a, b, reach in spans:
            if not self._free(a, b) and reach:
                continue
            cands = [x for x in self.G.mentions if x.i0 >= b and x.i0 <= b + reach and x.kind in ("col", "table")
                     and not getattr(x, "ctx", False)
                     and not getattr(x, "used_as_measure", False) and not getattr(x, "null", False)]
            if not cands:
                continue
            x = cands[0]
            if x.kind == "table" and len(cands) > 1 and cands[1].kind == "col" and cands[1].i0 == x.i1 and \
                    getattr(cands[1], "e", None) is not None and cands[1].e.table in {t.table for t in x.cands}:
                x.ctx = True                           # "customer segment": the entity noun qualifies its column
                x = cands[1]
            if x.kind == "col":
                e = getattr(x, "e", None)
                if e is None:
                    self.Q.ambiguities.append(f"'{x.text}' could be " + " or ".join(x.amb)); continue
                k = self.m.col(e.table, e.column).kind
                if k == "date" or (k == "measure" and id(x) not in self._group_targets()):
                    continue
                if k == "id" and e.path is None:
                    tgt = [te for te in self.lex.tables if te.path is not None and te.path.role == e.column and not te.path.fans_out]
                    if tgt and tgt[0].display:
                        out.append(Col(tgt[0].table, tgt[0].display, tgt[0].path)); x.grouped = True
                        self._use(a, b, "group"); self._ev(x.i0, x.i1, f"group by {tgt[0].table}.{tgt[0].display}", "entity label"); continue
                    if not tgt:
                        self.Q.unresolved.append(f"{e.column} has no lookup table that names its values"); continue
                if e.path is not None and e.path.fans_out:
                    self.Q.unsupported.append(f"grouping by {e.table}.{e.column} (one-to-many) would count rows more than once")
                    continue
                out.append(self._col(e)); x.grouped = True
                self._use(a, b, "group"); self._ev(x.i0, x.i1, f"group by {e.table}.{e.column}", "grouping")
            else:
                tes = x.cands
                if len({(t.table, t.path.role if t.path else "") for t in tes}) > 1:
                    w, amb = self._choose_path([L.ColEntry(t.table, t.display or "", t.path, [], [], "text") for t in tes], x.i0, x.i1)
                    if w is None:
                        self.Q.ambiguities.append(f"'{x.text}' is reached in more than one way: " + " or ".join(amb)); continue
                    te = next(t for t in tes if t.path is w.path)
                    rw = set(L._role_words(te.path, te.table))
                    near = range(max(0, x.i0 - 3), min(len(self.t), x.i1 + 3))
                    if any(self.t[j].can in rw and participle(self.t[j].low) for j in near) and len(te.path.steps) == 1:
                        fk = te.path.steps[0][0]
                        if fk.nullable:
                            self.extra.append(IsNull(Col(self.m.anchor, fk.child_col, None), True))
                            self._ev(x.i0, x.i1, f"{self.m.anchor}.{fk.child_col} IS NOT NULL", "the verb says the link exists")
                else:
                    te = tes[0]
                if te.path is None:
                    cue_w = self.t[a].low if a >= 0 else ""
                    between = self.ql[self.t[b].s:self.t[x.i0].s] if b < x.i0 else ""
                    if reach and cue_w in ("per", "each", "every", "for", "by") and not re.search(
                            r"\b(?:number|count|total|sum|amount|average|share|percentage)\b", between) and not any(
                            isinstance(mm.expr, Agg) and mm.expr.func == "avg" for mm in self.Q.measures) and not self._avg_cue():
                        self.Q.unresolved.append(f"'{self._text(a, x.i1)}' would give one value per {self.m.anchor} row; "
                                                 f"did you mean the average per {x.text}, or the overall total?")
                    continue
                if not te.path.fans_out and len(te.path.steps) == 1 and te.path.steps[0][0].nullable and len(tes) == 1 \
                        and a > 0 and participle(self.t[a - 1].low):
                    fk = te.path.steps[0][0]       # "handled by each adjuster": only rows that have one
                    self.extra.append(IsNull(Col(self.m.anchor, fk.child_col, None), True))
                    self._ev(x.i0, x.i1, f"{self.m.anchor}.{fk.child_col} IS NOT NULL", "the verb says the link exists")
                if te.path.fans_out:
                    self.Q.unsupported.append(f"grouping by {te.table} (one-to-many) would count rows more than once")
                    continue
                if not te.display:
                    self.Q.unresolved.append(f"{te.table} has no name column to label groups")
                    continue
                out.append(Col(te.table, te.display, te.path)); x.grouped = True
                self._use(a, b, "group"); self._ev(x.i0, x.i1, f"group by {te.table}.{te.display}", "entity label")
        return list(dict.fromkeys(out))

    # ------------------------------------------------------------------ accounting
    def _account(self) -> None:
        # the base table's own noun and generic words are not unresolved content
        for x in self.G.mentions:
            if x.kind == "table" and x.cands[0].path is None:
                self._use(x.i0, x.i1, "base table")
        # a verb directly before "by <value or entity>" links them ("taught by Ana Ruiz", "driven by drivers")
        for x in self.G.mentions:
            if x.kind in ("value", "table") and x.i0 >= 2 and self.t[x.i0 - 1].low == "by" and (x.i0 - 2) not in self.used:
                self.used[x.i0 - 2] = "linking verb"
                self.used.setdefault(x.i0 - 1, "linking verb")
        left = []
        for i, t in enumerate(self.t):
            if i in self.used:
                continue
            if t.low in FUNCTION or t.can in FUNCTION or t.can in LIGHT or t.low in FILLER or t.low.isdigit():
                continue
            if i == 0 and t.low in ("report", "show", "list", "give", "tell", "display", "find", "get", "compute", "calculate"):
                continue
            if any(x.i0 <= i < x.i1 for x in self.G.mentions):
                continue
            left.append(t.text)
        unused = [x for x in self.G.mentions if x.kind in ("col", "table") and not self._mention_used(x)]
        for x in unused:
            left.append(x.text)
        if left:
            self.Q.unresolved.append("words not grounded: " + ", ".join(dict.fromkeys(left)))
        dangling = [t.text for i, t in enumerate(self.t) if i not in self.used and t.low in ("not", "no", "never", "without", "non", "nor")]
        if dangling:
            self.Q.unresolved.append(f"'{dangling[0]}' is not attached to any condition")

    def _mention_used(self, x) -> bool:
        if any(getattr(x, f, False) for f in ("used_as_measure", "null", "cmp", "cond", "grouped", "ctx")):
            return True
        if all(i in self.ctx for i in range(x.i0, x.i1)):
            return True
        if x.kind == "table" and x.cands[0].path is None:
            return True
        cols = {(c.table, c.column) for c in self.Q.cols()}
        for e in x.cands:
            if x.kind == "col" and (e.table, e.column) in cols:
                return True
            if x.kind == "table" and any(c.table == e.table for c in self.Q.cols()):
                return True
        for f in self.Q.filters:
            if isinstance(f, Exists) and any(e.table in {st[0].child for st in f.path.steps} | {st[0].parent for st in f.path.steps}
                                             for e in x.cands):
                return True
        return any(ev.span and x.text.lower() in ev.span.lower() and "no condition" in ev.grounded_to for ev in self.Q.evidence)
