"""Database schema introspection."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
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


@lru_cache(maxsize=1)
def get_schema() -> Schema:
    engine = get_engine()
    insp = inspect(engine)
    schema = Schema()
    for t in insp.get_table_names():
        cols = [c["name"] for c in insp.get_columns(t)]
        schema.tables[t] = cols
    return schema


def refresh_schema() -> Schema:
    get_schema.cache_clear()
    return get_schema()
