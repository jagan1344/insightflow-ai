"""Reporting MCP server (FastMCP-style)."""
from __future__ import annotations

import csv
import io
import logging
import time
from typing import Optional

from mcp.server import MCPServer
from sqlalchemy import text

from mcp_servers._common import ensure_readonly_sql


logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("mcp.reporting")

app = MCPServer("insightflow-reporting")

MAX_EXPORT_ROWS = 10_000


def _engine():
    from insightflow.execution.executor import get_engine
    return get_engine()


def _run_sql(sql: str, limit: int):
    ensure_readonly_sql(sql)
    engine = _engine()
    with engine.connect() as conn:
        res = conn.execute(text(sql))
        cols = list(res.keys())
        rows = []
        for i, r in enumerate(res):
            if i >= limit: break
            rows.append(list(r))
    return cols, rows


@app.tool()
def generate_summary_report(format: str = "json") -> dict:
    """Executive summary for the active dataset.

    format: 'json' (default) or 'markdown' — markdown returns {'markdown': '...'}.
    """
    from insightflow.knowledge.dataset_registry import get_active_dataset
    from insightflow.knowledge.kpi_catalog import build_catalog
    ds = get_active_dataset()
    cat = build_catalog(ds)
    kpis: list[dict] = []
    for kid in ("total_revenue", "profit", "gross_margin", "order_count"):
        kpi = cat.get(kid)
        if kpi is None: continue
        try:
            with _engine().connect() as conn:
                v = conn.execute(text(
                    f'SELECT {kpi.formula} FROM "{ds.table}"')).scalar()
                kpis.append({"kpi_id": kpi.kpi_id, "name": kpi.display_name,
                              "value": float(v) if v is not None else None,
                              "unit": kpi.unit})
        except Exception as e:
            kpis.append({"kpi_id": kpi.kpi_id, "error": str(e)})
    body = {"title": f"Executive Summary — {ds.name}",
             "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
             "dataset": ds.table, "kpis": kpis,
             "measures": ds.measures, "dimensions": ds.dimensions,
             "dates": ds.dates}
    if format == "markdown":
        lines = [f"# {body['title']}", "",
                  f"_Generated {body['generated_at']} — dataset `{ds.table}`_",
                  "", "## KPIs", ""]
        for k in kpis:
            if "error" in k:
                lines.append(f"- **{k['kpi_id']}** — error: {k['error']}")
            else:
                lines.append(f"- **{k['name']}** ({k['kpi_id']}): "
                              f"{k.get('value')} {k.get('unit')}")
        body["markdown"] = "\n".join(lines)
    return body


@app.tool()
def export_query_results(sql: str, limit: int = MAX_EXPORT_ROWS) -> dict:
    """Run a validated SELECT and return the result as CSV text."""
    if limit > MAX_EXPORT_ROWS: limit = MAX_EXPORT_ROWS
    try:
        cols, rows = _run_sql(sql, limit)
    except ValueError as e:
        return {"error": str(e)}
    # Force \n line endings so the output is identical on Windows and
    # Linux and portable through MCP's text channel.
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for r in rows: w.writerow(r)
    return {"csv": buf.getvalue(), "row_count": len(rows),
             "columns": cols}


@app.tool()
def generate_metric_report(kpi_id: str, format: str = "json") -> dict:
    """Per-KPI report with definition, current value, monthly trend, top-5 breakdown."""
    from insightflow.knowledge.dataset_registry import get_active_dataset
    from insightflow.knowledge.kpi_catalog import build_catalog
    from insightflow.plan import (
        AnalyticalPlan, DimRef, Grain, IntentKind, MeasureRef, SQLCompiler,
    )
    ds = get_active_dataset()
    cat = build_catalog(ds)
    kpi = cat.get(kpi_id)
    if kpi is None:
        return {"error": f"KPI {kpi_id!r} not defined on this dataset"}
    engine = _engine()
    headline = None
    try:
        with engine.connect() as conn:
            v = conn.execute(text(
                f'SELECT {kpi.formula} FROM "{ds.table}"')).scalar()
            headline = float(v) if v is not None else None
    except Exception:
        pass
    trend: list = []
    if ds.dates:
        plan = AnalyticalPlan(
            intent_kind=IntentKind.TREND, table=ds.table,
            measures=[MeasureRef(kpi_id=kpi.kpi_id, formula=kpi.formula,
                                  aggregation=kpi.aggregation, unit=kpi.unit)],
            dims=[DimRef(column=ds.dates[0], is_time=True, time_unit="month")],
            grain=Grain(kind="time", time_unit="month",
                         time_column=ds.dates[0]),
            order_by="time_asc",
        )
        sql = SQLCompiler(ds, cat).compile(plan)
        try:
            with engine.connect() as conn:
                for r in conn.execute(text(sql)):
                    trend.append({"period": str(r[0]), "value": r[1]})
        except Exception:
            pass
    breakdown: list = []
    if ds.dimensions:
        dim = ds.dimensions[0]
        plan = AnalyticalPlan(
            intent_kind=IntentKind.TOP_N, table=ds.table,
            measures=[MeasureRef(kpi_id=kpi.kpi_id, formula=kpi.formula,
                                  aggregation=kpi.aggregation, unit=kpi.unit)],
            dims=[DimRef(column=dim)], top_n=5, order_by="measure_desc",
        )
        sql = SQLCompiler(ds, cat).compile(plan)
        try:
            with engine.connect() as conn:
                for r in conn.execute(text(sql)):
                    breakdown.append({"label": r[0], "value": r[-1]})
        except Exception:
            pass
    body = {"kpi_id": kpi.kpi_id, "name": kpi.display_name,
             "aggregation": kpi.aggregation, "formula": kpi.formula,
             "unit": kpi.unit, "required_columns": kpi.required_columns,
             "value": headline, "trend": trend, "top_breakdown": breakdown,
             "dataset": ds.table}
    if format == "markdown":
        lines = [f"# {kpi.display_name} ({kpi.kpi_id})", "",
                  f"**Formula:** `{kpi.formula}`  ",
                  f"**Aggregation:** {kpi.aggregation}  ",
                  f"**Unit:** {kpi.unit}  ",
                  f"**Current value:** {headline}", ""]
        if trend:
            lines += ["## Monthly trend", ""]
            for p in trend[-12:]:
                lines.append(f"- {p['period']}: {p['value']}")
            lines.append("")
        if breakdown:
            lines += [f"## Top 5 by {ds.dimensions[0]}", ""]
            for b in breakdown:
                lines.append(f"- {b['label']}: {b['value']}")
        body["markdown"] = "\n".join(lines)
    return body


if __name__ == "__main__":
    app.run(transport="stdio")
