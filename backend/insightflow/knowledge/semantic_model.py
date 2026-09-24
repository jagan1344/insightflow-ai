"""Dataset Semantic Model.

An enrichment layer on top of `dataset_registry.ActiveDataset`. Where the
registry answers "what physical columns does the active dataset have and
what's each column's coarse role?", the semantic model answers:

    * What is the dataset's grain (row-level? one row per order? per
      customer? per day? something else)?
    * Which columns are candidate primary keys / foreign keys?
    * For each column: distinct count, null percentage, min/max value,
      sample values, inferred aliases, and a confidence for its
      semantic role.
    * Which columns are the "natural" measure / dimension / date / id
      candidates a planner should reach for first?

This model is derived per-dataset from actual data statistics; the
planner and the KPI catalog use it instead of talking to the raw
introspection layer directly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from ..execution.executor import get_engine
from .dataset_registry import ActiveDataset


# ---------------------------------------------------------------------------
# Alias tables — pure LANGUAGE knowledge (which words map to which
# semantic role). NOT dataset knowledge; a role only applies if the data
# supports it.
# ---------------------------------------------------------------------------

_MEASURE_ALIASES: Dict[str, Tuple[str, ...]] = {
    "revenue":  ("revenue", "sales", "amount", "gross", "turnover",
                  "net_sales", "sales_amount", "value"),
    "profit":   ("profit", "gain", "net_profit", "earnings", "margin_amount"),
    "cost":     ("cost", "cogs", "expense", "expenses", "spend"),
    "discount": ("discount", "markdown", "rebate"),
    "quantity": ("quantity", "qty", "units", "items", "count"),
    "price":    ("price", "unit_price", "rate"),
}

_DIM_ALIASES: Dict[str, Tuple[str, ...]] = {
    "region":       ("region", "area", "territory", "zone"),
    "state":        ("state", "province"),
    "city":         ("city", "town"),
    "country":      ("country", "nation"),
    "category":     ("category", "class", "type", "family"),
    "sub_category": ("sub_category", "subcategory", "sub-category"),
    "product":      ("product", "item", "sku"),
    "customer":     ("customer", "client", "buyer", "account"),
    "segment":      ("segment", "tier"),
    "channel":      ("channel", "platform"),
    "department":   ("department", "dept", "division", "team", "branch",
                      "store"),
}

_DATE_HINTS = (
    "date", "day", "month", "year", "quarter", "week",
    "timestamp", "created", "updated", "order_date", "ship_date",
    "invoice_date", "transaction_date", "period",
)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class ColumnProfile:
    """Everything the planner + catalog know about a physical column."""
    name: str
    normalized_name: str
    sql_type: str
    role: str                       # measure|dimension|date|id|boolean|text|unknown
    role_confidence: float          # 0..1
    aliases: List[str] = field(default_factory=list)

    # data statistics
    n_rows: int = 0
    distinct_count: Optional[int] = None
    null_count: Optional[int] = None
    null_pct: float = 0.0
    min_value: Optional[object] = None
    max_value: Optional[object] = None
    sample_values: List[object] = field(default_factory=list)

    # key-role candidates
    is_pk_candidate: bool = False
    is_fk_candidate: bool = False


@dataclass
class DatasetSemanticModel:
    """A per-dataset semantic view derived from data statistics."""
    dataset_id: str
    table: str
    kind: str                       # "demo" | "uploaded"
    n_rows: int = 0
    columns: Dict[str, ColumnProfile] = field(default_factory=dict)
    # grain: one of {"row", "order", "customer", "product", "day",
    #                 "month", "unknown"} — best-guess unit of a row.
    grain: str = "row"
    grain_confidence: float = 0.5
    # convenience lists (role-filtered)
    measures: List[str] = field(default_factory=list)
    dimensions: List[str] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)
    id_columns: List[str] = field(default_factory=list)
    primary_key_candidate: Optional[str] = None

    # ------------------------------------------------------------------
    def col(self, name: str) -> Optional[ColumnProfile]:
        return self.columns.get(name)

    def find_columns_by_alias(self, alias: str,
                                role: Optional[str] = None) -> List[str]:
        """Physical column names whose profile lists `alias` (case-
        insensitive), optionally filtered by role."""
        a = alias.lower().strip().replace(" ", "_").replace("-", "_")
        out: List[str] = []
        for cname, prof in self.columns.items():
            if role is not None and prof.role != role:
                continue
            if a in [p.lower() for p in prof.aliases] or a == prof.normalized_name:
                out.append(cname)
        return out

    def as_dict(self) -> dict:
        return {
            "dataset_id": self.dataset_id,
            "table": self.table,
            "kind": self.kind,
            "n_rows": self.n_rows,
            "grain": self.grain,
            "grain_confidence": self.grain_confidence,
            "primary_key_candidate": self.primary_key_candidate,
            "columns": [
                {
                    "name": p.name,
                    "role": p.role,
                    "role_confidence": p.role_confidence,
                    "sql_type": p.sql_type,
                    "n_rows": p.n_rows,
                    "distinct_count": p.distinct_count,
                    "null_pct": p.null_pct,
                    "min": p.min_value, "max": p.max_value,
                    "is_pk_candidate": p.is_pk_candidate,
                    "is_fk_candidate": p.is_fk_candidate,
                    "aliases": p.aliases,
                }
                for p in self.columns.values()
            ],
        }


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def _normalize_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _find_aliases(normalized: str) -> List[str]:
    """Return language aliases that a column with this normalized name
    could match — used by the planner to know that a column named
    "sales_amount" also serves the alias "revenue"."""
    out: List[str] = [normalized]
    tokens = normalized.split("_")
    for canonical, aliases in _MEASURE_ALIASES.items():
        for a in aliases:
            if a in tokens or a in normalized:
                out.append(canonical)
                out.extend(aliases)
                break
    for canonical, aliases in _DIM_ALIASES.items():
        for a in aliases:
            if a in tokens or a in normalized:
                out.append(canonical)
                out.extend(aliases)
                break
    # de-duplicate preserving order
    seen: set = set(); dedup: List[str] = []
    for a in out:
        if a not in seen:
            seen.add(a); dedup.append(a)
    return dedup


def _looks_numeric(sql_type: str) -> bool:
    t = (sql_type or "").upper()
    return any(k in t for k in ("INT", "REAL", "NUM", "DEC", "FLOAT", "DOUBLE"))


def _looks_text(sql_type: str) -> bool:
    t = (sql_type or "").upper()
    return any(k in t for k in ("CHAR", "TEXT", "STRING", "CLOB"))


def _looks_bool(sql_type: str) -> bool:
    t = (sql_type or "").upper()
    return "BOOL" in t


def _iso_date_ratio(samples: List) -> float:
    if not samples:
        return 0.0
    ok = sum(1 for s in samples[:20]
             if s and re.match(r"^\d{4}-\d{2}(?:-\d{2})?", str(s).strip()))
    return ok / max(1, min(20, len(samples)))


def _infer_role(prof: ColumnProfile) -> Tuple[str, float]:
    """Return (role, confidence). Uses name hints, type and sample content."""
    lname = prof.normalized_name
    tokens = lname.split("_")
    # id?
    if lname == "id" or lname.endswith("_id") or lname == "pk":
        return "id", 0.95
    if prof.distinct_count is not None and prof.n_rows > 0 \
            and prof.distinct_count == prof.n_rows and prof.n_rows > 1:
        return "id", 0.85
    # date?
    if any(h in lname for h in _DATE_HINTS):
        return "date", 0.9
    if _iso_date_ratio(prof.sample_values) > 0.6:
        return "date", 0.75
    # numeric?
    if _looks_numeric(prof.sql_type):
        # measures land here — unless the column looks id-shaped
        return "measure", 0.85
    if _looks_bool(prof.sql_type):
        return "boolean", 0.9
    if _looks_text(prof.sql_type):
        # dimensions with hints get higher confidence
        for dim_name, aliases in _DIM_ALIASES.items():
            if any(a in lname for a in aliases):
                return "dimension", 0.9
        # low-cardinality text → dimension
        if prof.distinct_count is not None and prof.n_rows > 0:
            if prof.distinct_count / prof.n_rows < 0.5:
                return "dimension", 0.75
        return "text", 0.55
    return "unknown", 0.30


def _stats_for_column(engine: Engine, table: str, col: str,
                       n_rows: int) -> dict:
    """Return {distinct_count, null_count, min, max, sample_values}."""
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                f'SELECT COUNT(DISTINCT "{col}"), '
                f'SUM(CASE WHEN "{col}" IS NULL THEN 1 ELSE 0 END), '
                f'MIN("{col}"), MAX("{col}") FROM "{table}"'
            )).fetchone()
            samples = [r[0] for r in conn.execute(text(
                f'SELECT "{col}" FROM "{table}" '
                f'WHERE "{col}" IS NOT NULL LIMIT 20'
            )).fetchall()]
        return {
            "distinct_count": int(row[0] or 0),
            "null_count": int(row[1] or 0),
            "min": row[2],
            "max": row[3],
            "sample_values": samples,
        }
    except Exception:
        return {"distinct_count": None, "null_count": None,
                "min": None, "max": None, "sample_values": []}


def _row_count(engine: Engine, table: str) -> int:
    try:
        with engine.connect() as conn:
            return int(conn.execute(text(
                f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0)
    except Exception:
        return 0


def _estimate_grain(model: DatasetSemanticModel) -> Tuple[str, float]:
    """Best-guess grain from id-candidate patterns and column naming."""
    n = model.n_rows
    if n == 0:
        return "unknown", 0.0

    # A pk-candidate whose name contains "order"/"transaction"/"invoice"
    # is a strong signal.
    for cname, p in model.columns.items():
        if not p.is_pk_candidate:
            continue
        lname = p.normalized_name
        if any(t in lname for t in ("order", "transaction", "invoice",
                                     "receipt")):
            return "order", 0.9
        if "customer" in lname or "client" in lname:
            return "customer", 0.85
        if "product" in lname or "sku" in lname:
            return "product", 0.85

    # Multiple rows per customer / product but one row per (customer,
    # date) or per (customer, product, date) — hard to tell without
    # multi-column key inference. Fall back to name-hint on date column.
    if model.dates:
        # If distinct dates < n_rows, grain is finer than "day".
        d = model.dates[0]
        p = model.columns.get(d)
        if p and p.distinct_count and p.distinct_count < n:
            return "row", 0.6
        return "day", 0.6

    return "row", 0.5


def build_semantic_model(ds: ActiveDataset) -> DatasetSemanticModel:
    """Build the DSM for the given active dataset (works for demo and
    uploaded)."""
    engine = get_engine()
    model = DatasetSemanticModel(
        dataset_id=ds.id, table=ds.table, kind=ds.kind,
    )
    model.n_rows = _row_count(engine, ds.table)

    for cname, info in ds.columns.items():
        prof = ColumnProfile(
            name=cname,
            normalized_name=_normalize_name(cname),
            sql_type=info.sql_type or "",
            role=info.role or "unknown",
            role_confidence=0.5,
            aliases=_find_aliases(_normalize_name(cname)),
            n_rows=model.n_rows,
            sample_values=list(info.sample_values or []),
        )
        # Only physical columns get stats — demo joined pseudo-columns
        # (region_name / product_name / etc.) live in other tables so
        # their stats are inspected via those tables' rows.
        if ds.kind == "demo" and cname not in ("revenue", "cost",
                                                 "discount", "quantity",
                                                 "order_date", "order_id",
                                                 "customer_id", "product_id",
                                                 "region_id"):
            # skip stats for pseudo-columns to keep the DSM cheap; the
            # inferred role coming from the registry is authoritative
            pass
        else:
            s = _stats_for_column(engine, ds.table, cname, model.n_rows)
            prof.distinct_count = s["distinct_count"]
            prof.null_count = s["null_count"]
            prof.null_pct = (s["null_count"] / model.n_rows
                              if model.n_rows and s["null_count"] is not None
                              else 0.0)
            prof.min_value = s["min"]
            prof.max_value = s["max"]
            if not prof.sample_values:
                prof.sample_values = s["sample_values"]

        # Refine role using data statistics.
        role, conf = _infer_role(prof)
        # Data-driven upgrade: a "measure"-typed column that is fully
        # unique + numeric + has "id/no/pk" in its name is really an id.
        looks_id = (role == "id"
                     or any(t in prof.normalized_name for t in
                            ("_id", "id", "_no", "no_", "num", "number")))
        if looks_id and prof.is_pk_candidate and info.role != "date":
            prof.role, prof.role_confidence = "id", max(conf, 0.8)
        elif info.role in ("measure", "dimension", "date", "id"):
            prof.role = info.role
            prof.role_confidence = max(0.6, conf if role == info.role else 0.5)
        else:
            prof.role, prof.role_confidence = role, conf

        # PK candidate?
        if prof.distinct_count is not None and prof.n_rows > 0 \
                and prof.distinct_count == prof.n_rows and prof.null_pct == 0.0:
            prof.is_pk_candidate = True
        # FK candidate — ends with _id but isn't the PK
        if (prof.normalized_name.endswith("_id")
                and prof.normalized_name != "id"
                and not prof.is_pk_candidate):
            prof.is_fk_candidate = True

        model.columns[cname] = prof

    # role-filtered convenience lists
    for cname, p in model.columns.items():
        if p.role == "measure":
            model.measures.append(cname)
        elif p.role == "dimension":
            model.dimensions.append(cname)
        elif p.role == "date":
            model.dates.append(cname)
        elif p.role == "id":
            model.id_columns.append(cname)
        if p.is_pk_candidate and model.primary_key_candidate is None:
            model.primary_key_candidate = cname

    # grain
    model.grain, model.grain_confidence = _estimate_grain(model)
    return model
