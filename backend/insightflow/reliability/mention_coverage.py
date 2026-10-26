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
    # the base table's own noun phrase ("order lines") is not a reference to
    # another table ("orders")
    for n in sorted({rel.anchor.replace("_", " "),
                     rel.anchor.replace("_", " ").rstrip("s")}, key=len, reverse=True):
        ql = ql.replace(n, " ")
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
            if any(e.parent_table == t and e.child_col.lower() in sql_l
                   for e in rel.schema.edges):
                break          # an intermediate hop: its key is used directly
            if fk and not re.search(
                    rf"\b(?:how\s+many|number\s+of|count\s+of|count)\s+"
                    rf"(?:distinct\s+|unique\s+|different\s+)?{re.escape(noun)}\b", ql):
                break      # a many-to-one parent merely mentioned (the base rows already reference it)
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


def unrepresented_years(question: str, sql: str) -> List[str]:
    """A four-digit year named in the question that the SQL never uses
    means the time constraint was silently dropped."""
    ys = set(year_tokens(question))
    return sorted(y for y in ys if y not in sql and str(int(y) + 1) not in sql
                  and str(int(y) - 1) not in sql)


_CMP_BEFORE = re.compile(
    r"(?:over|above|under|below|than|exceeding|exceeds?|least|most|exactly|"
    r"equals?|[<>=]=?|about|around|approximately|worth|costing|priced)\s*$")


def year_tokens(text: str) -> List[str]:
    """Four-digit years, excluding quantities in a comparison ("over 2000")."""
    out = []
    t = text.lower()
    for m in re.finditer(r"(?<![\d.,])((?:19|20)\d{2})(?![\d])", t):
        if _CMP_BEFORE.search(t[max(0, m.start() - 16):m.start()]):
            continue
        out.append(m.group(1))
    return out


_NUM_EXEMPT = re.compile(
    r"\b(?:top|bottom|first|last|past|previous|next|latest|recent|best|worst)"
    r"\s+\d+|\bq[1-4]\b|\d+(?:st|nd|rd|th)\b|\d+\s*%|"
    r"\b\d{4}-\d{2}(?:-\d{2})?\b",
    re.I)


def unrepresented_numbers(question: str, sql: str,
                          value_texts: Optional[List[str]] = None) -> List[str]:
    """Numeric literals in the question (thresholds, counts, quantities)
    that never reach the SQL. Years, top-N / last-N, quarters, ordinals and
    percentages have their own handling and are exempt; digits inside known
    dimension values are masked."""
    q = question.lower()
    for v in (value_texts or []):
        q = q.replace(v.lower(), " ")
    q = re.sub(r"(?<![\d-])(?:19|20)\d{2}-\d{2}-\d{2}(?![\d-])", " ", q)
    for y in year_tokens(q):
        q = q.replace(y, " ", 1)
    q = _NUM_EXEMPT.sub(" ", q)
    sql_n = re.sub(r"\s+", "", sql)
    out = []
    for m in re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w])", q):
        tok = m.group(1)
        pats = {tok, tok.rstrip("0").rstrip(".") if "." in tok else tok}
        if not any(re.search(rf"(?<![\d.]){re.escape(p)}(?:\.0+)?(?![\d])", sql_n)
                   for p in pats):
            out.append(tok)
    return out


_GENERIC_TOK = {"date", "name", "number", "code", "type", "amount", "total",
                "value", "count", "time", "year", "month", "status", "id", "key"}


def unrepresented_column_words(question: str, sql: str, ds) -> List[str]:
    """A distinctive word of some column's name appears in the question
    ("returned", "late") but that column is never used by the SQL."""
    rel = getattr(ds, "rel", None)
    if ds is None or ds.kind == "demo" or not sql or rel is None:
        return []          # table names are only trustworthy for registered relational data
    qv = question.lower()
    try:
        from ..plan.planner import _value_index, _value_mentions
        for lo, _c in _value_mentions(question, _value_index(ds)):
            qv = qv.replace(lo, " ")
    except Exception:
        pass
    ql = re.sub(r"[^a-z0-9]+", " ", qv)
    sql_l = sql.lower()
    skip = set()
    for t in re.split(r"[^a-z0-9]+", ds.table.lower()):
        skip |= {t, t.rstrip("s"), t.rstrip("s") + "s"}
    if rel is not None:
        from ..knowledge.rel_context import parent_nouns
        for t in rel.schema.tables:
            for n in parent_nouns(t):
                skip |= set(n.split())
    anchor_toks = [t for t in re.split(r"[^a-z0-9]+", ds.table.lower()) if len(t) >= 5]
    # a verb form of the base entity ("enrolled" for enrollments) is not a qualifier
    words = [w for w in ql.split() if len(w) >= 4 and w not in skip
             and not any(w[:5] == t[:5] for t in anchor_toks)]
    out = []
    for c, info in ds.columns.items():
        if info.role == "id":
            continue
        toks = [t for t in re.split(r"[^a-z0-9]+", c.lower())
                if len(t) >= 4 and t not in _GENERIC_TOK and t not in skip]
        if not toks or c.lower() in sql_l:
            continue
        for w in words:
            if any(w == t or w.startswith(t[:max(4, len(t) - 2)]) for t in toks):
                # another referenced column carrying the same token satisfies it
                if any(c2.lower() in sql_l and any(w.startswith(t2[:max(4, len(t2) - 2)])
                       for t2 in re.split(r"[^a-z0-9]+", c2.lower()) if len(t2) >= 4)
                       for c2 in ds.columns):
                    continue
                out.append(f"{w} ({c})")
                break
    return out


def unrepresented_iso_dates(question: str, sql: str) -> List[str]:
    ds_ = re.findall(r"(?<![\d-])((?:19|20)\d{2}-\d{2}-\d{2})(?![\d-])", question)
    return [d for d in ds_ if d not in sql and not _next_day_in(d, sql)]


def _next_day_in(d: str, sql: str) -> bool:
    import datetime
    try:
        nd = (datetime.date.fromisoformat(d) + datetime.timedelta(days=1)).isoformat()
    except ValueError:
        return False
    return nd in sql


_FUNCTION_WORDS = set("""
about above after again against along also always among and another any anyone anything are around because been before
being below between both but cannot could currently did does doing done down during each either else enough even ever
every everything few for from further get give given gives going had has have having here how however into its itself
just keep let like made make makes many more most much must need never next none nor not nothing now off often once only
other others otherwise our ours out over own per please rather really same shall should show shows since some something
sometimes still such tell than that the their theirs them then there these they thing things this those though through
thus till together too toward towards under until upon very want wants was were what whatever when whenever where whether
which while who whom whose why will with within without would yet you your yours list find count give display provide
report calculate compute compare summarize rank sort group order total sum average avg mean median maximum minimum max min
number amount value values figure figures overall all both highest lowest largest smallest biggest greatest best worst top
bottom first second third fourth last previous recent latest earlier later year years month months week weeks day days
quarter quarters half halves date dates time period periods monthly weekly daily yearly annual quarterly percent
come comes came coming go goes went gone going make makes made making get gets got getting take takes took taken
bring brings brought happen happens happened break breakdown ones one included include includes including least most
across altogether whole entire
didn doesn don haven hasn wasn weren isn aren couldn shouldn wouldn won leave leaving left omit omitting ignoring
zero opposed field fields
percentage proportion share ratio rate times daily january february march april june july august september october
november december monday tuesday wednesday thursday friday saturday sunday excluding exclude except including include
included between versus against among each every one two three four five six seven eight nine ten hundred thousand
million records record rows row entries entry items item data dataset table column columns field fields
cost costs revenue revenues sales profit profits margin margins income spend spending expense expenses price prices
change changed changes decline declined declines increase increased increases decrease decreased decreases drop dropped
growth grew rise rose fall fell trend trends contribution contributed driver drivers reason reasons cause caused
affect affected impact vary varies compared comparison difference differences relative against breakdown
across using used via regarding concerning throughout beyond inside outside near behind beside plus whether neither
overall entire whole combined altogether summed calculated computed based according
""".split())


_IRREGULAR_PAST = set("""sold bought paid made taught sent held took got gave kept left lost won ran began wrote
spent brought thought found built saw met put set read led""".split())


def unexplained_words(question: str, ds, catalog=None) -> tuple:
    """Content words that map to nothing: not a function word, schema term
    (table / column / related column / FK parent noun), KPI alias word, or
    known data value. Returns (hard, soft): `soft` are verb-like (-ed / -ing)
    words, which usually just describe the rows ("placed", "borrowed") and
    are reported as a caveat; `hard` (adjectives / nouns such as "overdue",
    "outstanding") change the meaning and must be asked about."""
    if ds is None or ds.kind == "demo" or getattr(ds, "rel", None) is None:
        return [], []      # flat uploads rely on legacy phrase rules the vocabulary check would fight
    from ..plan.planner import _value_index, _value_mentions
    ql = question.lower()
    for lo, _c in _value_mentions(question, _value_index(ds)):
        ql = ql.replace(lo, " ")
    known = set(_FUNCTION_WORDS)
    toks = set()
    for c in ds.columns:
        toks |= set(re.split(r"[^a-z0-9]+", c.lower()))
    toks |= set(re.split(r"[^a-z0-9]+", ds.table.lower()))
    rel = getattr(ds, "rel", None)
    if rel is not None:
        from ..knowledge.rel_context import parent_nouns
        for t in rel.schema.tables:
            toks |= set(re.split(r"[^a-z0-9]+", t.lower()))
            for n in parent_nouns(t):
                toks |= set(n.split())
            for c in rel.schema.tables[t].columns:
                toks |= set(re.split(r"[^a-z0-9]+", c.lower()))
    if catalog is not None:
        for k in catalog.kpis.values():
            for a in k.aliases + [k.display_name]:
                toks |= set(re.split(r"[^a-z0-9]+", a.lower()))
    toks = {t for t in toks if len(t) >= 3}
    hard, soft = [], []
    for w in re.findall(r"[a-z]{4,}", ql):
        if w in known:
            continue
        if any(w == t or w[:5] == t[:5] and min(len(w), len(t)) >= 5
               or (len(t) >= 4 and w.startswith(t)) or (len(w) >= 4 and t.startswith(w))
               or (len(t) == 3 and len(w) >= 5 and w.startswith(t))
               for t in toks):
            continue
        (soft if (re.search(r"ed$", w) or w in _IRREGULAR_PAST) else hard).append(w)
    return list(dict.fromkeys(hard)), list(dict.fromkeys(soft))


_COMPARATIVES = {"larger", "bigger", "higher", "greater", "smaller", "lower", "fewer"}


def words_consumed_by_plan(question: str, plan) -> set:
    """Words that only count as explained because the plan applied the filter
    they describe: a comparative before 'than' needs a >/< comparison filter,
    and an antonym of a polarity flag ('faulty' for sensor_ok) needs that flag
    filtered to 0. Without the matching filter they stay unexplained."""
    from ..plan.planner import _FLAG_ANTONYMS, _FLAG_POLARITY
    ql = question.lower()
    fs = list(getattr(plan, "filters", None) or [])
    out = set()
    if any(f.kind == "cmp" and getattr(f, "op", "") in (">", "<", ">=", "<=") for f in fs):
        out |= {w for w in re.findall(r"\b([a-z]+)\s+than\b", ql) if w in _COMPARATIVES}
    if any(f.kind == "cmp" and getattr(f, "op", "") in (">=", "<=") for f in fs):
        out |= set(re.findall(r"\bat\s+(least|most)\b", ql))
    if any(f.kind == "eq" and f.value == 0 and
           set(re.split(r"[^a-z0-9]+", str(f.column).lower())) & _FLAG_POLARITY for f in fs):
        out |= {m.group(0) for m in re.finditer(rf"\b(?:{_FLAG_ANTONYMS})\b", ql)}
    if any(f.kind == "eq" and f.value in (0, 1) and
           set(re.split(r"[^a-z0-9]+", str(f.column).lower())) & _FLAG_POLARITY for f in fs):
        from ..plan.planner import _FLAG_POSITIVE
        out |= {w for m in re.finditer(rf"\b(?:{_FLAG_POSITIVE}|{_FLAG_ANTONYMS})\b", ql) for w in m.group(0).split()}
    if any(f.kind in ("null", "not_null") for f in fs):
        out |= {"unknown", "missing", "blank", "empty", "null", "recorded", "unrecorded", "unset", "entered",
                "known", "assigned", "unassigned", "allocated", "captured", "provided", "filled"}
    if any(f.kind == "not_in" or (f.kind == "eq" and f.value == 0) for f in fs):
        out |= {"leave", "leaving", "omitting", "ignoring", "disregarding", "excluding"}
    return out
