"""Question normalisation against the active schema (deterministic, inspectable).

A rewrite is applied only when its target term exists in the active schema and the
rewrite is unique; nothing is invented that the schema does not establish. Each rewrite
is returned as a `Rewrite` so the orchestrator can record it, and rewrites that are an
interpretation (a business synonym, an acronym, a revenue word) are stated in the answer.

Rules (language knowledge, not schema- or question-specific):
  numbers      "1,000" -> "1000"
  compounds    "drop-off" / "dropped off" -> "dropoff" when `dropoff` is a schema token
  columns      "claimed amount" / "amount claimed" -> "claim amt"; "type of room" -> "room type";
               "payment method" -> "pay method" (multi-word column names, matched on
               canonical tokens, rewritten to the column's own words)
  units        "kilowatt-hours" -> "kwh", "square metres" -> "sq m" when the schema uses them
  synonyms     "reservations" -> "bookings" when only one member of a synonym group is in the schema
  acronyms     "online travel agencies" -> "OTA" when "OTA" is a stored value
  revenue      "revenue" / "brought in" / "value of <rows>" -> "amount" when the base table has
               exactly one generically named money column (amt / amount / value / total)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .abbrev import ABBREV, canon


@dataclass
class Rewrite:
    rule: str
    before: str
    after: str
    interpretive: bool

    def describe(self) -> str:
        return f"'{self.before}' read as '{self.after}' ({self.rule})"


# unit and measure words whose schema form is an abbreviation
_UNITS: Dict[str, List[str]] = {
    "kwh": ["kilowatt hours", "kilowatt-hours", "kilowatt hour", "kilowatt-hour", "kw h"],
    "km": ["kilometres", "kilometers", "kilometre", "kilometer"],
    "hrs": ["hours"], "hr": ["hours", "hour"],
    "min": ["minutes", "minute"],
    "nts": ["room nights", "room-nights", "nights", "night"],
    "sq m": ["square metres", "square meters", "square metre", "square meter", "sqm", "m2"],
    "sq ft": ["square feet", "square foot", "sqft"],
    "kg": ["kilograms", "kilogram", "kilos"],
}

# groups of words that name the same business object; members are rewritten to the one the schema uses
_SYNONYMS: List[Set[str]] = [
    {"booking", "reservation"}, {"customer", "client"}, {"trip", "ride", "journey"},
    {"order", "purchase"}, {"docs", "documents", "documentation", "paperwork"},
    {"employee", "staff", "worker"}, {"supplier", "vendor"}, {"product", "item"},
    {"invoice", "bill"}, {"shipment", "consignment"}, {"student", "pupil", "learner"},
    {"ticket", "case"}, {"category", "class"},
]
_REVENUE = r"(?:total\s+)?(?:revenue|sales\s+revenue|takings|turnover|income|brought\s+in|earned|generated)"
_GENERIC_MONEY = {"amount", "total", "value"}
_MONEY_HINT = {"amount", "amt", "price", "fare", "cost", "fee", "revenue", "sales", "value", "usd", "eur",
               "gbp", "premium", "prem", "charge", "spend", "salary", "wage", "pay", "tip", "total"}
_PARTICLES = ("up", "off", "in", "out", "on", "over", "down")
_FUNCTION = {"the", "for", "and", "of", "on", "in", "at", "to", "by", "with", "from", "our", "we", "all",
             "any", "are", "was", "were", "has", "have", "how", "what", "which", "who", "per", "each"}


def _plural(w: str) -> List[str]:
    if w.endswith("y") and len(w) > 2 and w[-2] not in "aeiou":
        return [w, w[:-1] + "ies"]
    if w.endswith(("s", "x", "ch", "sh")):
        return [w, w + "es"]
    return [w, w + "s"]


def _participles(w: str) -> List[str]:
    out = {w}
    if w.endswith("e"):
        out |= {w + "d"}
    else:
        out |= {w + "ed"}
        if len(w) > 2 and w[-1] not in "aeiouwxy" and w[-2] in "aeiou" and w[-3] not in "aeiou":
            out |= {w + w[-1] + "ed"}
    return sorted(out)


def _verb_forms(w: str) -> List[str]:
    out = set(_participles(w)) | {w + "s", w + "ing"}
    if len(w) > 2 and w[-1] not in "aeiouwxy" and w[-2] in "aeiou" and w[-3] not in "aeiou":
        out |= {w + w[-1] + "ing"}
    return sorted(out)


def _schema_names(ds) -> Tuple[Dict[str, Dict[str, str]], str]:
    """{table: {column: sql_type}} for the base table and every table reachable in its schema."""
    rel = getattr(ds, "rel", None)
    if rel is not None:
        return {t: dict(ti.columns) for t, ti in rel.schema.tables.items()}, ds.table
    return {ds.table: {c: getattr(i, "sql_type", "") for c, i in ds.columns.items()}}, ds.table


def _sub(text: str, phrase: str, repl: str) -> Tuple[str, Optional[str]]:
    m = re.search(rf"(?<![a-z0-9_]){re.escape(phrase)}(?![a-z0-9_])", text, flags=re.I)
    if not m:
        return text, None
    return text[:m.start()] + repl + text[m.end():], m.group(0)


def normalise(question: str, ds) -> Tuple[str, List[Rewrite]]:
    if ds is None or getattr(ds, "kind", "demo") == "demo":
        return question, []
    tables, anchor = _schema_names(ds)
    rewrites: List[Rewrite] = []
    q = question

    # numbers with thousands separators
    for m in list(re.finditer(r"\d{1,3}(?:,\d{3})+\b", q)):
        rewrites.append(Rewrite("number", m.group(0), m.group(0).replace(",", ""), False))
    q = re.sub(r"(?<=\d),(?=\d{3}\b)", "", q)

    # protect stored values (they are matched verbatim elsewhere)
    try:
        from ..plan.planner import _value_index
        vidx = _value_index(ds)
    except Exception:
        vidx = {}
    values = list(vidx.keys())
    masks: Dict[str, str] = {}

    def _mask(s: str) -> str:
        for i, v in enumerate(sorted(values, key=len, reverse=True)):
            if len(v) < 3:
                continue
            m = re.search(rf"(?<![a-z0-9]){re.escape(v)}(?![a-z0-9])", s, flags=re.I)
            if m:
                key = f"⁣{len(masks)}⁣"
                masks[key] = s[m.start():m.end()]
                s = s[:m.start()] + key + s[m.end():]
        return s

    q = _mask(q)

    tokens: Set[str] = set()
    for t, cols in tables.items():
        tokens |= {x for x in re.split(r"[^a-z0-9]+", t.lower()) if x}
        for c in cols:
            tokens |= {x for x in re.split(r"[^a-z0-9]+", c.lower()) if x}

    # compounds written apart: drop-off / dropped off -> dropoff, check-in -> checkin
    for tok in sorted(tokens, key=len, reverse=True):
        for p in _PARTICLES:
            if tok.endswith(p) and len(tok) > len(p) + 2:
                head = tok[:-len(p)]
                for form in [head] + _verb_forms(head):
                    for sep in ("-", " "):
                        q, hit = _sub(q, f"{form}{sep}{p}", tok)
                        if hit:
                            rewrites.append(Rewrite("compound", hit, tok, False))

    # multi-word column names: canonical tokens in order, reversed, or "<b> of <a>"
    seen: Dict[Tuple[str, ...], List[str]] = {}
    for t, cols in tables.items():
        for c in cols:
            raw = [x for x in re.split(r"[^a-z0-9]+", c.lower()) if x]
            ct = [canon(x) for x in raw]
            if len(ct) == 2 and not ({"id", "code", "key"} & set(ct)):
                seen.setdefault(tuple(ct), []).append(" ".join(raw))
    for ct, raws in seen.items():
        if len(set(raws)) != 1:
            continue                          # the same phrase names two columns: never guess
        a, b = ct
        target = raws[0]
        forms = []
        for pa in sorted(set(_participles(a)) | {a}):
            for pb in _plural(b):
                forms += [f"{pa} {pb}", f"{pb} {pa}"]
        for pb in _plural(b):
            forms += [f"{pb} of {a}", f"{pb} of the {a}"]
        forms += [f"{a}-{b}"]
        for f in sorted(set(forms) - {target}, key=len, reverse=True):
            q, hit = _sub(q, f, target)
            if hit:
                rewrites.append(Rewrite("column name", hit, target, False))
                break

    # unit words
    for tok, phrases in _UNITS.items():
        if not all(x in tokens for x in tok.split()):
            continue
        for ph in sorted(phrases, key=len, reverse=True):
            if all(x in tokens for x in ph.split()):
                continue                      # the schema itself uses the long word
            q, hit = _sub(q, ph, tok)
            if hit:
                rewrites.append(Rewrite("unit", hit, tok, False))

    # synonym groups
    table_nouns = {canon(x) for t in tables for x in re.split(r"[^a-z0-9]+", t.lower()) if x}
    for grp in _SYNONYMS:
        present = [w for w in grp if w in table_nouns or w in tokens]
        if len(present) != 1:
            continue
        target = present[0]
        for w in grp - {target}:
            if w in tokens:
                continue
            for wf, tf in zip(_plural(w), _plural(target)):
                q, hit = _sub(q, wf, tf)
                if hit:
                    rewrites.append(Rewrite("business synonym", hit, tf, True))

    # acronyms stored as values: "online travel agencies" -> "OTA"
    for lo, cands in vidx.items():
        origs = {str(o) for _c, o in cands}
        if len(origs) != 1:
            continue
        v = next(iter(origs))
        if not (3 <= len(v) <= 5 and v.isalpha() and v.isupper()):
            continue
        pat = r"\b" + r"\s+".join(rf"{ch}[a-z]+" for ch in v.lower()) + r"\b"
        m = re.search(pat, q, flags=re.I)
        if m and not (set(m.group(0).lower().split()) & _FUNCTION):
            q = q[:m.start()] + v + q[m.end():]
            rewrites.append(Rewrite("acronym", m.group(0), v, True))

    # revenue words -> the base table's single generic money column
    acols = tables.get(anchor, {})
    generic = [c for c in acols
               if set(canon(x) for x in re.split(r"[^a-z0-9]+", c.lower()) if x) <= _GENERIC_MONEY
               and any(k in (acols[c] or "").upper() for k in ("REAL", "NUM", "DEC", "FLOA", "DOUB", "INT"))]
    if len(generic) == 1 and not ({"revenue", "sales", "income"} & tokens):
        gw = " ".join(x for x in re.split(r"[^a-z0-9]+", generic[0].lower()) if x)
        anc = [x for x in re.split(r"[^a-z0-9]+", anchor.lower()) if x][-1]
        sing = anc[:-1] if anc.endswith("s") else anc
        for f in [rf"value\s+of\s+(?:the\s+|our\s+)?{anc}", rf"{sing}\s+value", rf"{sing}\s+revenue", _REVENUE]:
            m = re.search(rf"\b{f}\b", q, flags=re.I)
            if m:
                q = q[:m.start()] + gw + q[m.end():]
                rewrites.append(Rewrite("revenue word", m.group(0), gw, True))
                break
        # "what did we bill" / "how much did we bill"
        vf = "|".join(_verb_forms(sing) + [sing])
        m = re.search(rf"\b(?:what|how\s+much)\s+(?:did|have|has|do)\s+we\s+(?:{vf})\b", q, flags=re.I)
        if m:
            q = q[:m.start()] + f"what is the total {gw}" + q[m.end():]
            rewrites.append(Rewrite("revenue word", m.group(0), f"total {gw}", True))

    for k, v in masks.items():
        q = q.replace(k, v)
    q = re.sub(r"\s{2,}", " ", q).strip()
    return q, rewrites
