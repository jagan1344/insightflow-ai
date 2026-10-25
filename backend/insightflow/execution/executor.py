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
    # Dispose pooled connections before tests recreate the SQLite database.
    engine = get_engine() if get_engine.cache_info().currsize else None
    get_engine.cache_clear()
    if engine is not None:
        engine.dispose()


def _is_sqlite(engine: Engine) -> bool:
    return engine.dialect.name == "sqlite"


def run_sql(sql: str) -> QueryResult:
    """Execute a SQL statement read-only, capping rows and wall time.
    Never raises."""
    raw = None
    try:
        engine = get_engine()
        with engine.connect() as conn:
            if _is_sqlite(engine):
                from .cost_guard import arm_timeout
                raw = conn.connection.driver_connection
                raw.execute("PRAGMA query_only=ON")   # defence in depth
                arm_timeout(raw, settings.query_timeout_s)
            cur = conn.execute(text(sql))
            cols = list(cur.keys())
            rows = cur.fetchmany(settings.max_rows)
            return QueryResult(columns=cols, rows=[tuple(r) for r in rows])
    except Exception as e:
        msg = str(e)
        if "interrupted" in msg.lower():
            msg = (f"query exceeded the {settings.query_timeout_s:g}s time "
                   f"budget and was cancelled")
        return QueryResult(error=msg)
    finally:
        if raw is not None:
            try:
                raw.set_progress_handler(None, 0)
                raw.execute("PRAGMA query_only=OFF")
            except Exception:
                pass


def db_file_path() -> str:
    u = settings.database_url
    return u.split(":///", 1)[1] if ":///" in u else u
