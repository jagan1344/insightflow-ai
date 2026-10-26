"""Shared word layer: tokenisation, a small rule-based stemmer, abbreviation expansion and function words.
Question text and schema names pass through the same functions, so they meet in one canonical form.
This is language knowledge only; no schema- or question-specific entries."""
from __future__ import annotations

import re
from typing import List

# abbreviation -> canonical word (common business abbreviations; ambiguous ones are left out)
ABBREV = {
    "amt": "amount", "qty": "quantity", "cnt": "count", "num": "number", "nbr": "number", "no": "number",
    "cust": "customer", "custs": "customer", "acct": "account", "accts": "account", "acc": "account",
    "dept": "department", "emp": "employee", "prod": "product", "addr": "address", "pct": "percent",
    "dt": "date", "ts": "timestamp", "desc": "description", "cat": "category", "mgr": "manager",
    "org": "organization", "loc": "location", "svc": "service", "inv": "inventory", "ord": "order",
    "prc": "price", "cd": "code", "stat": "status", "sts": "status", "tot": "total", "avg": "average",
    "bal": "balance", "pmt": "payment", "pymt": "payment", "yr": "year", "mth": "month", "mo": "month",
    "wk": "week", "ref": "reference", "src": "source", "dst": "destination", "dest": "destination",
    "ctry": "country", "veh": "vehicle", "temp": "temperature", "pax": "passenger", "apt": "airport",
    "carr": "carrier", "flt": "flight", "sup": "supplier", "vend": "vendor", "cls": "class", "lang": "language",
    "rpt": "report", "req": "request", "dist": "distance", "dur": "duration", "prem": "premium",
    "nts": "night", "hrs": "hour", "hr": "hour", "mins": "minute", "min": "minute", "secs": "second",
    "tkt": "ticket", "dep": "deposit", "dlv": "delivery", "dlvy": "delivery", "rest": "restaurant",
    "nm": "name", "bldg": "building", "mgmt": "management", "wt": "weight", "kgs": "kg",
    "xfer": "transfer", "xfers": "transfer", "rcpt": "receipt", "rcv": "receive", "recv": "receive",
    "subs": "subscriber", "sub": "subscriber", "usr": "user", "msg": "message", "txn": "transaction",
    "trx": "transaction", "inst": "install", "mtd": "method", "rtg": "rating", "lvl": "level",
    "stmt": "statement", "mrc": "recurring", "chg": "charge", "fee": "fee", "sq": "square",
    "pts": "point", "pt": "point", "km": "kilometer", "kms": "kilometer", "kilometre": "kilometer",
    "kilometres": "kilometer", "metre": "meter", "metres": "meter",
}

IRREGULAR = {
    "paid": "pay", "sold": "sell", "bought": "buy", "made": "make", "taken": "take", "took": "take",
    "gave": "give", "given": "give", "came": "come", "went": "go", "gone": "go", "brought": "bring",
    "spent": "spend", "won": "win", "lost": "lose", "held": "hold", "kept": "keep", "sent": "send",
    "built": "build", "left": "leave", "ran": "run", "began": "begin", "begun": "begin", "wrote": "write",
    "written": "write", "children": "child", "people": "person", "men": "man", "women": "woman",
    "data": "data", "criteria": "criterion",
}

FUNCTION = set("""
a an the of in on at to for from by with without within into onto over under about across after before
during between through via per each every all any some no not none never nor or and but also as than then
is are was were be been being am do does did done doing have has had having can could would should will
shall may might must i we us our ours you your they them their it its this that these those there here
what which who whom whose when where why how much many more most less least fewer few other others
such own same so too very just only even still yet ever please show give list tell me find get let
see display want need know report provide total overall altogether whole entire across both either
one ones s t d ll ve re m don didn doesn haven hasn wasn weren isn aren couldn shouldn wouldn won
time times
""".split())


def tokens(text: str) -> List[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def stem(w: str) -> str:
    """Consistent (not linguistic) stemming: both sides of every comparison use it."""
    w = w.lower()
    if w in IRREGULAR:
        return IRREGULAR[w]
    if len(w) <= 3 or w.isdigit():
        return w
    if w.endswith(("ies", "ied")) and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("sses", "shes", "ches", "xes", "zes")):
        w = w[:-2]
    elif w.endswith(("ss", "us", "is")):
        return w
    elif w.endswith("s"):
        w = w[:-1]
    for suf in ("ing", "ed"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[:-len(suf)]
            if len(w) >= 4 and w[-1] == w[-2] and w[-1] not in "lsz":
                w = w[:-1]                          # shipped -> ship, planned -> plan
            break
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]                                  # price / priced / pricing -> pric
    return w


def canon(w: str) -> str:
    """Abbreviation expansion, then stemming."""
    w = w.lower()
    return stem(ABBREV.get(w, w))


def col_words(name: str) -> List[str]:
    ts = tokens(name)
    # "order_no" -> number, but "no_show" keeps its negation
    return [t if t in ("no", "non") and i < len(ts) - 1 else canon(t) for i, t in enumerate(ts)]


def table_words(name: str) -> List[str]:
    ws = [canon(t) for t in tokens(name)]
    return ws


# unit words: a column may be named without its unit ("score" for score_pct, "duration" for dur_min)
UNITS = {canon(w) for w in ("minute", "min", "mins", "hour", "hrs", "hr", "second", "secs", "day", "days", "km", "mi",
                            "mile", "kg", "lb", "percent", "pct", "usd", "eur", "gbp", "dollar", "kwh", "gb", "mb",
                            "ft", "sqft", "cents", "cent")}


DERIV = ("al", "ment", "ion", "ation", "s")     # renewal / shipment / completion: derived from the verb


def participle(w: str) -> bool:
    """Past-participle / adjectival verb form ('shipped', 'graded', 'paid')."""
    w = w.lower()
    return (w.endswith("ed") and len(w) > 4) or w in {"paid", "sent", "done", "made", "shown", "given", "taken", "built",
                                                      "sold", "won", "lost", "kept", "held", "spent", "met", "seen"}


def content(word: str) -> bool:
    return word not in FUNCTION and not word.isdigit()
