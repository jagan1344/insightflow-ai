"""Schema lexicon: which question words can refer to which schema element, derived from names, abbreviation
expansion, join roles and stored values. Built once per schema model; inspectable."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .schema_model import Column, Path, SchemaModel
from .words import FUNCTION, canon, col_words, table_words

GENERIC = {"amount", "value", "total", "count", "number", "code", "id", "date", "timestamp", "time", "flag",
           "is", "has", "nam", "nm", "per", "of", "ind", "indicator", "key"}
GENERIC |= {canon(w) for w in GENERIC}          # names are compared in canonical form (date -> dat)


@dataclass
class ColEntry:
    table: str
    column: str
    path: Optional[Path]          # None for the anchor
    words: List[str]              # all canonical words of the name
    core: List[str]               # words that must appear in the question
    kind: str
    role_words: List[str] = field(default_factory=list)   # for lookups reached through a role FK

    @property
    def key(self) -> str:
        return f"{self.table}.{self.column}" + (f"@{self.path.role}" if self.path is not None and self.path.role else "")


@dataclass
class TableEntry:
    table: str
    path: Optional[Path]
    words: List[str]
    display: Optional[str]        # name-like column used to label groups of this entity
    role_words: List[str] = field(default_factory=list)


@dataclass
class ValueEntry:
    text: str
    table: str
    column: str
    path: Optional[Path]


@dataclass
class Lexicon:
    model: SchemaModel
    cols: List[ColEntry]
    tables: List[TableEntry]
    values: Dict[str, List[ValueEntry]]    # lowercased value -> entries


def _display(cols: Dict[str, Column]) -> Optional[str]:
    texts = [c for c in cols.values() if c.kind in ("text", "category")]
    for c in texts:
        if any(w.startswith(("nam", "titl", "label")) for w in c.words) or c.name.lower().endswith(("_nm", "_name")):
            return c.name
    for c in texts:
        if c.kind == "text":
            return c.name
    return texts[0].name if texts else None


def _role_words(path: Optional[Path], parent: str) -> List[str]:
    """Words of the anchor FK column that differ from the parent table's own words ('pickup' in pickup_zone_cd)."""
    if path is None or not path.role:
        return []
    ws = [w for w in col_words(path.role) if w not in GENERIC and w not in FUNCTION]
    tw = set(table_words(parent))
    return [w for w in ws if w not in tw and w + "s" not in tw]


def _schema_abbrev(m: SchemaModel):
    """Short name tokens that abbreviate exactly one longer word used elsewhere in the same schema
    ('mbr' -> member, 'cls' -> class): schema-derived, never a global dictionary."""
    import re as _re
    from .words import ABBREV as _AB, stem as _st
    vocab = set()
    for t, cols in m.tables.items():
        for w in _re.split(r"[^a-z0-9]+", t.lower()):
            if len(w) >= 4:
                vocab.add(w.rstrip("s") if w.endswith("s") and not w.endswith("ss") else w)
        for c in cols:
            for w in _re.split(r"[^a-z0-9]+", c.lower()):
                if len(w) >= 5:
                    vocab.add(w)
    out = {}
    for t, cols in m.tables.items():
        for c in cols:
            for tok in _re.split(r"[^a-z0-9]+", c.lower()):
                if tok in _AB or tok in vocab or tok in FUNCTION or tok in GENERIC:
                    continue
                if 2 <= len(tok) <= 4 and not set(tok[1:]) & set("aeiouy"):
                    hits = [w for w in vocab if w[0] == tok[0] and _subseq(tok, w) and len(w) > len(tok)]
                elif 3 <= len(tok) <= 5:          # truncation of a longer schema word: stu -> student, accom -> accommodation
                    hits = [w for w in vocab if w.startswith(tok) and len(w) > len(tok) + 1]
                else:
                    hits = []
                if len(hits) == 1:
                    out[tok] = _st(hits[0])
    return out


def _subseq(a: str, b: str) -> bool:
    it = iter(b)
    return all(ch in it for ch in a)


def build(m: SchemaModel) -> Lexicon:
    cols: List[ColEntry] = []
    tables: List[TableEntry] = []
    values: Dict[str, List[ValueEntry]] = {}
    targets: List[Tuple[str, Optional[Path]]] = [(m.anchor, None)]
    for t, ps in m.paths.items():
        for p in ps:
            targets.append((t, p))
    ab = _schema_abbrev(m)
    for c in m.columns():
        c.words = [ab.get(w, w) for w in c.words]
    multi = {t for t, ps in m.paths.items() if len({p.role for p in ps}) > 1}
    for t, p in targets:
        tcols = m.tables[t]
        rw = _role_words(p, t) if t in multi else []
        rw = [ab.get(w, w) for w in rw]
        tw = table_words(t)
        disp = _display(tcols)
        tables.append(TableEntry(t, p, tw, disp, rw))
        fkp = {e.child_col: e.parent for e in m.edges if e.child == t}
        for c in tcols.values():
            core = [w for w in c.words if (w not in GENERIC and w not in FUNCTION) or (w in ("no", "non") and c.words[0] == w)] or [w for w in c.words if w not in ("is", "has")] or c.words
            if c.values and c.kind in ("category", "text"):
                for v in c.values:
                    lo = str(v).strip().lower()
                    if len(lo) >= 2 and not re.fullmatch(r"[\d\W_]+", lo):
                        values.setdefault(lo, []).append(ValueEntry(str(v), t, c.name, p))
            if core and set(core) <= {"no", "non"}:
                core = [w for w in c.words if w not in GENERIC]          # no_show needs both words
            if set(core) <= set(tw) and len(c.words) > len(core):
                core = [w for w in c.words if w not in FUNCTION and w not in ("is", "has")]   # order_dt needs "order date"
                if set(core) <= set(tw):
                    core = list(c.words)          # booked_on: the table noun alone ("bookings") never names it
            if c.kind == "id":
                if p is None and c.name not in fkp and not c.pk:
                    cols.append(ColEntry(t, c.name, p, c.words, core, c.kind, rw))   # proctor_id: no lookup
                    continue
                if not (p is None and c.name in fkp):
                    continue
                if set(core) <= set(table_words(fkp[c.name])):
                    continue           # the FK just names its entity: the entity noun stands for it
            if c.name == disp and set(core) <= set(tw):
                continue               # the entity's own name column: the entity noun stands for it
            cols.append(ColEntry(t, c.name, p, c.words, core, c.kind, rw))
    return Lexicon(m, cols, tables, values)
