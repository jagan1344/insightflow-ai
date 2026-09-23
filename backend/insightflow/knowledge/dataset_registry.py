"""Dataset registry — a lightweight active-dataset layer.

The historical demo star-schema (`orders`, `products`, `regions`,
`customers`) is preserved verbatim; the registry simply records it as a
built-in dataset called `demo`. Uploaded datasets are stored in
dedicated `dataset_<id>` tables that mirror their source columns 1-to-1.

This module answers three questions the rest of the pipeline needs:

    1. Which dataset is currently active?
    2. What is that dataset's physical table + column names?
    3. What semantic role does each column play (measure / dimension /
       date), inferred from the data itself?

Everything else — NL→SQL, KPI validation, analyzer, chart chooser —
becomes dataset-agnostic by reading `get_active_dataset()` instead of
assuming the demo schema.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from ..execution.executor import get_engine


DEMO_ID = "demo"
_META_TABLE = "_datasets"


# ---------------------------------------------------------------------------
# Column-role inference
# ---------------------------------------------------------------------------

_MEASURE_HINTS = (
    "revenue", "sales", "amount", "value", "price",
    "profit", "cost", "spend", "expense", "loss",
    "discount", "margin", "count", "quantity", "qty",
    "units", "volume", "orders", "transactions",
    "total", "sum", "avg",
)
_DIMENSION_HINTS = (
    "region", "state", "city", "country", "location",
    "category", "sub_category", "subcategory", "class", "type",
    "product", "sku", "item",
    "customer", "client", "segment", "group", "tier",
    "channel", "platform", "department", "team",
)
_DATE_HINTS = (
    "date", "day", "month", "year", "quarter", "week",
    "timestamp", "created", "updated", "order_date", "ship_date",
)


@dataclass
class ColumnInfo:
    name: str
    sql_type: str
    role: str                # "measure" | "dimension" | "date" | "id" | "unknown"
    distinct_count: Optional[int] = None
    sample_values: list = field(default_factory=list)

    @property
    def is_numeric(self) -> bool:
        t = (self.sql_type or "").upper()
        return any(k in t for k in ("INT", "REAL", "NUM", "DEC", "FLOAT", "DOUBLE"))

    @property
    def is_text(self) -> bool:
        t = (self.sql_type or "").upper()
        return any(k in t for k in ("CHAR", "TEXT", "STRING", "CLOB"))


@dataclass
class ActiveDataset:
    id: str                            # short id; "demo" or a slug for uploaded ones
    name: str                          # human-readable
    table: str                         # main table to query
    kind: str                          # "demo" | "uploaded"
    columns: dict[str, ColumnInfo] = field(default_factory=dict)
    # For the demo dataset only, join hints allow the analyzer to reach
    # region_name/customer_name/product_name via joins.
    join_hints: dict[str, str] = field(default_factory=dict)

    # -- role queries ----------------------------------------------------
    @property
    def measures(self) -> list[str]:
        return [n for n, c in self.columns.items() if c.role == "measure"]

    @property
    def dimensions(self) -> list[str]:
        return [n for n, c in self.columns.items() if c.role == "dimension"]

    @property
    def dates(self) -> list[str]:
        return [n for n, c in self.columns.items() if c.role == "date"]

    def as_ddl_text(self) -> str:
        cols = ", ".join(f"{c.name} {c.sql_type}" for c in self.columns.values())
        return f"TABLE {self.table}({cols})"


# ---------------------------------------------------------------------------
# Metadata table  (a one-row-per-dataset registry)
# ---------------------------------------------------------------------------

def _ensure_meta(conn) -> None:
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {_META_TABLE} (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            table_name TEXT NOT NULL,
            kind TEXT NOT NULL,
            uploaded_at TEXT,
            is_active INTEGER NOT NULL DEFAULT 0
        )
    """))


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()
    return (s or "dataset")[:40]


# ---------------------------------------------------------------------------
# Column-role inference — schema-aware, data-aware
# ---------------------------------------------------------------------------

def _infer_role(col_name: str, sql_type: str, sample_texts: list) -> str:
    lower = col_name.lower().replace(" ", "_").replace("-", "_")
    tup = tuple(lower.split("_"))
    # id-ish
    if lower == "id" or lower.endswith("_id") or lower == "pk":
        return "id"
    # date-ish
    if any(h in lower for h in _DATE_HINTS):
        return "date"
    # numeric column named like a measure
    numeric = any(k in (sql_type or "").upper()
                  for k in ("INT", "REAL", "NUM", "DEC", "FLOAT", "DOUBLE"))
    if numeric and any(h in lower for h in _MEASURE_HINTS):
        return "measure"
    # text column named like a dimension
    text_like = any(k in (sql_type or "").upper()
                    for k in ("CHAR", "TEXT", "STRING", "CLOB"))
    if text_like and any(h in lower for h in _DIMENSION_HINTS):
        return "dimension"
    # otherwise: numeric → measure, text → dimension
    if numeric:
        return "measure"
    if text_like:
        return "dimension"
    # try to sniff numeric-looking strings
    numish = sum(1 for s in sample_texts[:20]
                 if s and re.fullmatch(r"-?\d+(?:\.\d+)?", str(s).strip()))
    if sample_texts and numish / max(len(sample_texts), 1) > 0.6:
        return "measure"
    return "unknown"


def _sample_column(engine: Engine, table: str, column: str, limit: int = 20) -> list:
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                f'SELECT "{column}" FROM "{table}" '
                f'WHERE "{column}" IS NOT NULL LIMIT :n'
            ), {"n": limit}).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []


def introspect_table(engine: Engine, table: str) -> dict[str, ColumnInfo]:
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return {}
    cols: dict[str, ColumnInfo] = {}
    for c in insp.get_columns(table):
        name = c["name"]
        sql_type = str(c.get("type", "")).upper()
        samples = _sample_column(engine, table, name)
        role = _infer_role(name, sql_type, samples)
        cols[name] = ColumnInfo(
            name=name, sql_type=sql_type, role=role, sample_values=samples,
        )
    return cols


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def bootstrap() -> None:
    """Ensure the registry exists and the demo dataset is registered."""
    engine = get_engine()
    with engine.begin() as conn:
        _ensure_meta(conn)
        existing = conn.execute(text(
            f"SELECT COUNT(*) FROM {_META_TABLE}")).scalar()
        if existing == 0:
            # First bootstrap: register the demo dataset if `orders` exists.
            insp = inspect(engine)
            if "orders" in insp.get_table_names():
                conn.execute(text(
                    f"INSERT INTO {_META_TABLE}(id, name, table_name, kind, "
                    f"uploaded_at, is_active) VALUES ('demo', 'Demo sales', "
                    f"'orders', 'demo', datetime('now'), 1)"))


def list_datasets() -> list[dict]:
    bootstrap()
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT id, name, table_name, kind, uploaded_at, is_active "
            f"FROM {_META_TABLE} ORDER BY is_active DESC, uploaded_at DESC"
        )).fetchall()
    return [
        {"id": r[0], "name": r[1], "table": r[2], "kind": r[3],
         "uploaded_at": r[4], "is_active": bool(r[5])}
        for r in rows
    ]


def _get_active_row(engine: Engine) -> Optional[tuple]:
    with engine.connect() as conn:
        row = conn.execute(text(
            f"SELECT id, name, table_name, kind FROM {_META_TABLE} "
            f"WHERE is_active = 1 LIMIT 1"
        )).fetchone()
    return row


def get_active_dataset() -> ActiveDataset:
    """Return the currently-active dataset with fully-introspected columns.

    If nothing is active but the demo schema exists, the demo becomes
    active on the fly. If nothing is available at all, returns a stub
    where `table` is `orders` (matches legacy behaviour so tests that
    don't exercise the registry still work).
    """
    bootstrap()
    engine = get_engine()
    row = _get_active_row(engine)
    if row is None:
        # Nothing active; try demo as fallback.
        insp = inspect(engine)
        if "orders" in insp.get_table_names():
            with engine.begin() as conn:
                conn.execute(text(
                    f"UPDATE {_META_TABLE} SET is_active = "
                    f"CASE WHEN id = 'demo' THEN 1 ELSE 0 END"))
            row = _get_active_row(engine)
        else:
            return ActiveDataset(id="none", name="(empty)", table="orders",
                                 kind="demo", columns={})

    ds_id, name, table_name, kind = row
    if kind == "demo":
        # Demo-specific columns are known; still introspect actual columns.
        cols = introspect_table(engine, table_name)
        # Ensure key demo columns come out with the right roles regardless
        # of the inference heuristics.
        role_overrides = {
            "revenue": "measure", "cost": "measure",
            "discount": "measure", "quantity": "measure",
            "order_date": "date",
            "region_id": "id", "product_id": "id",
            "customer_id": "id", "order_id": "id",
        }
        for cname, r in role_overrides.items():
            if cname in cols:
                cols[cname].role = r
        return ActiveDataset(
            id=ds_id, name=name, table=table_name, kind="demo",
            columns=cols,
            join_hints={
                "region_name": ("JOIN regions ON regions.region_id = "
                                "orders.region_id"),
                "product_name": ("JOIN products ON products.product_id = "
                                 "orders.product_id"),
                "category": ("JOIN products ON products.product_id = "
                             "orders.product_id"),
                "sub_category": ("JOIN products ON products.product_id = "
                                 "orders.product_id"),
                "customer_name": ("JOIN customers ON customers.customer_id "
                                  "= orders.customer_id"),
                "segment": ("JOIN customers ON customers.customer_id = "
                            "orders.customer_id"),
            },
        )
    cols = introspect_table(engine, table_name)
    return ActiveDataset(id=ds_id, name=name, table=table_name,
                         kind="uploaded", columns=cols)


def set_active(dataset_id: str) -> ActiveDataset:
    bootstrap()
    engine = get_engine()
    with engine.begin() as conn:
        n = conn.execute(text(
            f"SELECT COUNT(*) FROM {_META_TABLE} WHERE id = :id"
        ), {"id": dataset_id}).scalar()
        if not n:
            raise ValueError(f"unknown dataset id: {dataset_id!r}")
        conn.execute(text(
            f"UPDATE {_META_TABLE} SET is_active = "
            f"CASE WHEN id = :id THEN 1 ELSE 0 END"), {"id": dataset_id})
    return get_active_dataset()


def register_uploaded(name: str, table_name: str) -> str:
    """Insert a new uploaded dataset row and mark it active. Returns the id."""
    bootstrap()
    engine = get_engine()
    with engine.begin() as conn:
        # ensure unique id
        base = _slug(name)
        candidate = base
        i = 1
        while conn.execute(text(
                f"SELECT 1 FROM {_META_TABLE} WHERE id = :id"),
                {"id": candidate}).scalar():
            i += 1
            candidate = f"{base}_{i}"
        conn.execute(text(
            f"INSERT INTO {_META_TABLE}(id, name, table_name, kind, "
            f"uploaded_at, is_active) VALUES (:id, :name, :t, 'uploaded', "
            f"datetime('now'), 0)"),
            {"id": candidate, "name": name, "t": table_name})
        conn.execute(text(
            f"UPDATE {_META_TABLE} SET is_active = "
            f"CASE WHEN id = :id THEN 1 ELSE 0 END"), {"id": candidate})
    return candidate


def delete_uploaded(dataset_id: str) -> None:
    """Drop the physical table and remove the registry row. Refuses demo."""
    if dataset_id == DEMO_ID:
        raise ValueError("cannot delete the demo dataset")
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(text(
            f"SELECT table_name, kind FROM {_META_TABLE} WHERE id = :id"),
            {"id": dataset_id}).fetchone()
        if not row:
            return
        table_name, kind = row
        if kind == "uploaded":
            conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
        conn.execute(text(f"DELETE FROM {_META_TABLE} WHERE id = :id"),
                     {"id": dataset_id})
        # if we removed the active one, fall back to demo
        remaining = conn.execute(text(
            f"SELECT COUNT(*) FROM {_META_TABLE} WHERE is_active = 1"
        )).scalar()
        if not remaining:
            conn.execute(text(
                f"UPDATE {_META_TABLE} SET is_active = 1 WHERE id = 'demo'"))
