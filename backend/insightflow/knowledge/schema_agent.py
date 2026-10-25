"""Database schema introspection."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set

from sqlalchemy import inspect

from ..execution.executor import get_engine


@dataclass
class Schema:
    tables: Dict[str, List[str]] = field(default_factory=dict)

    def as_ddl_text(self) -> str:
        parts = []
        for t, cols in self.tables.items():
            parts.append(f"TABLE {t}({', '.join(cols)})")
        return "\n".join(parts)

    def all_columns(self) -> Set[str]:
        cols: Set[str] = set()
        for t, colnames in self.tables.items():
            for c in colnames:
                cols.add(c)
                cols.add(f"{t}.{c}")
        return cols


_cache: dict = {"key": None, "schema": None}


def _ddl_version() -> object:
    """PRAGMA schema_version changes on any DDL (create/drop/alter). Cheap,
    so the schema cache can never serve a stale table/column list."""
    engine = get_engine()
    if engine.dialect.name != "sqlite":
        return None
    try:
        with engine.connect() as conn:
            ver = conn.exec_driver_sql("PRAGMA schema_version").scalar()
            h = hash(tuple(conn.exec_driver_sql(
                "SELECT name, sql FROM sqlite_master").fetchall()))
            return (str(engine.url), ver, h)
    except Exception:
        return None


def get_schema() -> Schema:
    key = _ddl_version()
    if key is not None and _cache["key"] == key and _cache["schema"] is not None:
        return _cache["schema"]
    engine = get_engine()
    insp = inspect(engine)
    schema = Schema()
    for t in insp.get_table_names():
        cols = [c["name"] for c in insp.get_columns(t)]
        schema.tables[t] = cols
    _cache["key"], _cache["schema"] = key, (schema if key is not None else None)
    return schema


def refresh_schema() -> Schema:
    _cache["key"] = None; _cache["schema"] = None
    return get_schema()


def schema_changed_since(last_key) -> tuple:
    """-> (changed, key). Lets callers detect external DDL changes."""
    k = _ddl_version()
    return (last_key is not None and k != last_key), k
