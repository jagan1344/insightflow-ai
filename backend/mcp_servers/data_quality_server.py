"""Data quality + governance MCP server (FastMCP-style)."""
from __future__ import annotations

import logging
from typing import Optional

from mcp.server import MCPServer
from sqlalchemy import inspect, text


logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("mcp.dq")

app = MCPServer("insightflow-data-quality")


def _engine():
    from insightflow.execution.executor import get_engine
    return get_engine()


@app.tool()
def profile_table(table: str) -> dict:
    """Row count, column count, per-column null % and distinct counts."""
    engine = _engine()
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return {"error": f"unknown table: {table!r}"}
    cols = [c["name"] for c in insp.get_columns(table)]
    with engine.connect() as conn:
        n = int(conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0)
        per_col = {}
        for col in cols:
            try:
                row = conn.execute(text(
                    f'SELECT COUNT(DISTINCT "{col}"), '
                    f'SUM(CASE WHEN "{col}" IS NULL THEN 1 ELSE 0 END) '
                    f'FROM "{table}"')).fetchone()
                per_col[col] = {"distinct_count": int(row[0] or 0),
                                 "null_count": int(row[1] or 0),
                                 "null_pct": (float(row[1] or 0) / n) if n else 0.0}
            except Exception as e:
                per_col[col] = {"error": str(e)}
    return {"table": table, "row_count": n, "column_count": len(cols),
             "columns": per_col}


@app.tool()
def check_missing_values(table: str, threshold: float = 0.10) -> dict:
    """Columns whose null percentage exceeds the threshold."""
    prof = profile_table(table=table)
    if "error" in prof:
        return prof
    flagged = []
    for col, stats in (prof.get("columns") or {}).items():
        if stats.get("null_pct", 0.0) >= threshold:
            flagged.append({"column": col, "null_pct": stats["null_pct"],
                             "null_count": stats["null_count"]})
    return {"table": table, "threshold": threshold,
             "flagged_columns": sorted(flagged, key=lambda r: -r["null_pct"]),
             "row_count": prof.get("row_count")}


@app.tool()
def check_duplicate_records(table: str, key_column: str) -> dict:
    """How many rows share a value in the given key column."""
    engine = _engine()
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return {"error": f"unknown table: {table!r}"}
    cols = {c["name"] for c in insp.get_columns(table)}
    if key_column not in cols:
        return {"error": f"unknown column: {key_column!r}"}
    with engine.connect() as conn:
        row = conn.execute(text(
            f'SELECT COUNT(*), COUNT(DISTINCT "{key_column}") FROM "{table}"'
        )).fetchone()
        total = int(row[0] or 0); distinct = int(row[1] or 0)
        dups = conn.execute(text(
            f'SELECT "{key_column}", COUNT(*) AS n FROM "{table}" '
            f'GROUP BY "{key_column}" HAVING COUNT(*) > 1 '
            f'ORDER BY n DESC LIMIT 20')).fetchall()
    return {"table": table, "key_column": key_column,
             "total_rows": total, "distinct_keys": distinct,
             "duplicate_count": total - distinct,
             "top_duplicates": [{"value": r[0], "count": int(r[1])} for r in dups]}


@app.tool()
def validate_metric_definition(kpi_id: str) -> dict:
    """Does the KPI's required columns resolve on the active dataset?"""
    from insightflow.knowledge.dataset_registry import get_active_dataset
    from insightflow.knowledge.kpi_catalog import build_catalog
    ds = get_active_dataset()
    cat = build_catalog(ds)
    kpi = cat.get(kpi_id)
    if kpi is None:
        return {"ok": False, "kpi_id": kpi_id, "reason": "not_defined",
                 "available_ids": sorted(cat.all_ids())[:40]}
    missing = [c for c in kpi.required_columns if c not in ds.columns]
    return {"ok": not missing, "kpi_id": kpi.kpi_id,
             "formula": kpi.formula, "required_columns": kpi.required_columns,
             "missing_columns": missing, "dataset": ds.table}


@app.tool()
def check_query_policy(sql: str) -> dict:
    """Does a SQL string pass the client-side policy
    (read-only verb, allowed tables, single statement)?"""
    from insightflow.mcp_integration import load_config
    from insightflow.mcp_integration.policy import PolicyError, PolicyGuard
    cfg = load_config()
    guard = PolicyGuard(cfg)
    srv = cfg.server("db") or (cfg.servers[0] if cfg.servers else None)
    try:
        guard.check_arguments(server=srv, tool_name="execute_readonly_query",
                               arguments={"sql": sql})
    except PolicyError as e:
        return {"ok": False, "reason": str(e)}
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}
    return {"ok": True}


@app.tool()
def get_data_quality_summary() -> dict:
    """Aggregate quality summary for the active dataset."""
    from insightflow.knowledge.dataset_registry import get_active_dataset
    from insightflow.knowledge.kpi_catalog import build_catalog
    from insightflow.knowledge.semantic_model import build_semantic_model
    ds = get_active_dataset()
    model = build_semantic_model(ds)
    cat = build_catalog(ds)
    prof = profile_table(table=ds.table)
    row_count = prof.get("row_count", 0) if isinstance(prof, dict) else 0
    issues: list[str] = []
    overall = 1.0
    if row_count == 0:
        issues.append("dataset is empty"); overall = 0.0
    for col, stats in (prof.get("columns") or {}).items():
        if stats.get("null_pct", 0.0) >= 0.20:
            issues.append(f"column {col!r} is {stats['null_pct']:.0%} null")
            overall -= 0.1
    overall = max(0.0, min(1.0, overall))
    return {"dataset": ds.table, "row_count": row_count,
             "column_count": len(ds.columns), "measures": ds.measures,
             "dimensions": ds.dimensions, "dates": ds.dates,
             "kpi_count": len(cat.kpis), "grain": model.grain,
             "grain_confidence": model.grain_confidence,
             "overall_score": round(overall, 3), "issues": issues}


if __name__ == "__main__":
    app.run(transport="stdio")
