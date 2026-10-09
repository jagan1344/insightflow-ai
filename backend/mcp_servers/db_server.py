"""Database MCP server (high-level FastMCP-style API).

Exposes read-only introspection + query execution against the same
SQLAlchemy engine the app uses. Every tool enforces:

    * read-only SQL (SELECT/WITH only)
    * table allowlist (orders / demo lookups / dataset_* / _datasets)
    * row cap (default 1,000)
    * no secrets in error text
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

from mcp.server import MCPServer
from sqlalchemy import inspect, text

from mcp_servers._common import ensure_readonly_sql, table_allowed


logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("mcp.db")

app = MCPServer("insightflow-db")


MAX_ROWS = int(os.environ.get("MCP_DB_MAX_ROWS", "1000"))
ALLOWED_PREFIXES = tuple(
    (os.environ.get("MCP_DB_ALLOWED_PREFIXES")
     or "orders,customers,products,regions,dataset_,_datasets").split(","))


def _engine():
    from insightflow.execution.executor import get_engine
    return get_engine()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@app.tool()
def list_schemas() -> dict[str, list[str]]:
    """Return the list of logical schemas. SQLite returns `['main']`."""
    try:
        return {"schemas": [str(_engine().url.database) or "main"]}
    except Exception:
        return {"schemas": ["main"]}


@app.tool()
def list_tables() -> dict[str, list[str]]:
    """List every table that the server policy permits access to."""
    insp = inspect(_engine())
    tables = [t for t in insp.get_table_names()
               if table_allowed(t, ALLOWED_PREFIXES)]
    return {"tables": sorted(tables)}


@app.tool()
def describe_table(table: str) -> dict:
    """Return a table's columns, SQL types, and row count."""
    if not table_allowed(table, ALLOWED_PREFIXES):
        return {"error": f"table not allowed: {table!r}"}
    engine = _engine()
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return {"error": f"unknown table: {table!r}"}
    cols = [{"name": c["name"], "sql_type": str(c.get("type", "")),
              "nullable": bool(c.get("nullable", True))}
             for c in insp.get_columns(table)]
    with engine.connect() as conn:
        row_count = int(conn.execute(
            text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0)
    return {"table": table, "columns": cols, "row_count": row_count}


@app.tool()
def get_column_metadata(table: str) -> dict:
    """Per-column metadata via the semantic model (role, distinct count,
    null %, min/max, samples)."""
    if not table_allowed(table, ALLOWED_PREFIXES):
        return {"error": f"table not allowed: {table!r}"}
    engine = _engine()
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return {"error": f"unknown table: {table!r}"}
    try:
        from insightflow.knowledge.dataset_registry import (
            ActiveDataset, ColumnInfo,
        )
        from insightflow.knowledge.semantic_model import build_semantic_model
        cols_meta = {
            c["name"]: ColumnInfo(name=c["name"],
                                   sql_type=str(c.get("type", "")),
                                   role="unknown")
            for c in insp.get_columns(table)
        }
        ds = ActiveDataset(id=table, name=table, table=table,
                            kind="uploaded", columns=cols_meta)
        return build_semantic_model(ds).as_dict()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@app.tool()
def get_relationships(table: str) -> dict:
    """Foreign-key relationships discovered on a table."""
    if not table_allowed(table, ALLOWED_PREFIXES):
        return {"error": f"table not allowed: {table!r}"}
    engine = _engine()
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return {"error": f"unknown table: {table!r}"}
    fks = []
    try:
        for fk in insp.get_foreign_keys(table):
            fks.append({
                "constrained_columns": fk.get("constrained_columns") or [],
                "referred_table": fk.get("referred_table"),
                "referred_columns": fk.get("referred_columns") or [],
            })
    except Exception:
        pass
    return {"table": table, "foreign_keys": fks}


@app.tool()
def execute_readonly_query(sql: str, limit: int = MAX_ROWS) -> dict:
    """Execute a validated single SELECT/WITH query.

    `limit` caps rows (never exceeds the server MAX_ROWS). Any other
    SQL verb or multi-statement input is rejected.
    """
    if limit > MAX_ROWS:
        limit = MAX_ROWS
    try:
        ensure_readonly_sql(sql)
    except ValueError as e:
        return {"error": str(e)}
    tables_in_sql = set(re.findall(
        r'\b(?:from|join)\s+"?([A-Za-z_][A-Za-z0-9_]*)"?',
        sql, flags=re.I))
    bad = [t for t in tables_in_sql if not table_allowed(t, ALLOWED_PREFIXES)]
    if bad:
        return {"error": f"tables not allowed: {sorted(bad)}"}
    engine = _engine()
    started = time.monotonic()
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = []
        truncated = False
        for i, r in enumerate(result):
            if i >= limit:
                truncated = True; break
            rows.append(list(r))
    return {"columns": columns, "rows": rows, "row_count": len(rows),
             "truncated": truncated,
             "duration_ms": int((time.monotonic() - started) * 1000)}


@app.tool()
def get_data_freshness(table: str, date_column: str | None = None) -> dict:
    """Return the latest value in a date-shaped column (for "last updated")."""
    if not table_allowed(table, ALLOWED_PREFIXES):
        return {"error": f"table not allowed: {table!r}"}
    engine = _engine()
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return {"error": f"unknown table: {table!r}"}
    date_col = date_column
    if not date_col:
        for c in insp.get_columns(table):
            n = c["name"].lower()
            if any(h in n for h in ("date", "day", "month", "timestamp",
                                      "created", "updated")):
                date_col = c["name"]; break
    if not date_col:
        return {"table": table, "latest": None, "note": "no_date_column"}
    with engine.connect() as conn:
        row = conn.execute(text(
            f'SELECT MAX("{date_col}") FROM "{table}"')).fetchone()
    return {"table": table, "date_column": date_col,
             "latest": str(row[0]) if row and row[0] is not None else None}


if __name__ == "__main__":
    app.run(transport="stdio")
