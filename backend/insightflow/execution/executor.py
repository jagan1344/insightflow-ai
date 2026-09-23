"""Read-only, row-capped SQL execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from ..config import settings


@dataclass
class QueryResult:
    columns: List[str] = field(default_factory=list)
    rows: List[tuple] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    def to_dicts(self) -> List[Dict[str, Any]]:
        return [dict(zip(self.columns, r)) for r in self.rows]


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = settings.database_url
    return create_engine(url, future=True)


def reset_engine() -> None:
    get_engine.cache_clear()


def run_sql(sql: str) -> QueryResult:
    """Execute a SQL statement read-only, capping rows. Never raises."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            cur = conn.execute(text(sql))
            cols = list(cur.keys())
            rows = cur.fetchmany(settings.max_rows)
            return QueryResult(columns=cols, rows=[tuple(r) for r in rows])
    except Exception as e:
        return QueryResult(error=str(e))
