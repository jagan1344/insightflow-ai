"""Analytics MCP server (high-level FastMCP-style API).

Delegates every tool to the existing deterministic analytics stack
(plan pipeline, KPI catalog, compiler, result validator). Nothing here
re-implements analytics logic — the LLM only chooses WHICH tool to
call; the numbers come from Python/SQLAlchemy.
"""
from __future__ import annotations

import logging
import math
import statistics
from typing import Any, Optional

from mcp.server import MCPServer


logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("mcp.analytics")

app = MCPServer("insightflow-analytics")


# ---------------------------------------------------------------------------
# Lazy helpers
# ---------------------------------------------------------------------------

def _dataset_and_catalog():
    from insightflow.knowledge.dataset_registry import get_active_dataset
    from insightflow.knowledge.kpi_catalog import build_catalog
    ds = get_active_dataset()
    return ds, build_catalog(ds)


def _run_sql(sql: str):
    from insightflow.execution.executor import run_sql
    return run_sql(sql)


def _resolve_kpi(cat, kpi_id: str):
    kpi = cat.get(kpi_id)
    if kpi is None:
        raise ValueError(
            f"KPI {kpi_id!r} not found. Available: "
            f"{sorted(cat.all_ids())[:30]}")
    return kpi


# ---------------------------------------------------------------------------

@app.tool()
def calculate_kpi(kpi_id: str,
                   time_range_lo: Optional[str] = None,
                   time_range_hi: Optional[str] = None) -> dict:
    """Compute a KPI value from the active dataset.

    kpi_id: catalog KPI id (e.g. 'total_revenue', 'profit').
    time_range_lo / time_range_hi: optional YYYY-MM period bounds.
    """
    from insightflow.plan import (
        AnalyticalPlan, FilterExpr, IntentKind, MeasureRef, SQLCompiler,
    )
    ds, cat = _dataset_and_catalog()
    kpi = _resolve_kpi(cat, kpi_id)
    filters = []
    if ds.dates and time_range_lo:
        filters.append(FilterExpr(
            kind="time_range", column=ds.dates[0],
            lo=str(time_range_lo),
            hi=str(time_range_hi or time_range_lo)))
    plan = AnalyticalPlan(
        intent_kind=IntentKind.DIRECT_KPI, table=ds.table,
        measures=[MeasureRef(kpi_id=kpi.kpi_id, formula=kpi.formula,
                              aggregation=kpi.aggregation, unit=kpi.unit)],
        filters=filters,
    )
    sql = SQLCompiler(ds, cat).compile(plan)
    result = _run_sql(sql)
    value = None
    if result.ok and result.rows:
        try: value = float(result.rows[0][-1])
        except (TypeError, ValueError): pass
    return {"kpi": kpi.kpi_id, "name": kpi.display_name,
             "formula": kpi.formula, "unit": kpi.unit, "value": value,
             "sql": sql, "dataset": ds.table, "ok": result.ok,
             "error": result.error if not result.ok else None}


@app.tool()
def compare_periods(kpi_id: str, base_period: str, target_period: str) -> dict:
    """Compute a KPI for two YYYY-MM periods. Returns base/target/delta/pct_change."""
    from insightflow.plan import (
        AnalyticalPlan, ComparisonSpec, IntentKind, MeasureRef, SQLCompiler,
    )
    ds, cat = _dataset_and_catalog()
    kpi = _resolve_kpi(cat, kpi_id)
    if not ds.dates:
        return {"error": "dataset has no date column"}
    plan = AnalyticalPlan(
        intent_kind=IntentKind.COMPARISON, table=ds.table,
        measures=[MeasureRef(kpi_id=kpi.kpi_id, formula=kpi.formula,
                              aggregation=kpi.aggregation, unit=kpi.unit)],
        comparison=ComparisonSpec(time_column=ds.dates[0],
                                    base_period=base_period,
                                    target_period=target_period),
    )
    sql = SQLCompiler(ds, cat).compile(plan)
    result = _run_sql(sql)
    base_v = target_v = None
    for r in result.rows or []:
        try: p, v = str(r[0]), float(r[1])
        except (TypeError, ValueError, IndexError): continue
        if p == base_period: base_v = v
        elif p == target_period: target_v = v
    delta = (target_v - base_v) if (base_v is not None and target_v is not None) else None
    pct = (delta / base_v * 100.0) if (delta is not None and base_v) else None
    return {"kpi": kpi.kpi_id, "base_period": base_period,
             "target_period": target_period, "base": base_v,
             "target": target_v, "delta": delta, "pct_change": pct,
             "sql": sql, "ok": result.ok}


@app.tool()
def analyze_trend(kpi_id: str, time_unit: str = "month") -> dict:
    """Return a KPI's values bucketed by time_unit (day/week/month/quarter/year)."""
    from insightflow.plan import (
        AnalyticalPlan, DimRef, Grain, IntentKind, MeasureRef, SQLCompiler,
    )
    ds, cat = _dataset_and_catalog()
    kpi = _resolve_kpi(cat, kpi_id)
    if not ds.dates:
        return {"error": "dataset has no date column"}
    plan = AnalyticalPlan(
        intent_kind=IntentKind.TREND, table=ds.table,
        measures=[MeasureRef(kpi_id=kpi.kpi_id, formula=kpi.formula,
                              aggregation=kpi.aggregation, unit=kpi.unit)],
        dims=[DimRef(column=ds.dates[0], is_time=True, time_unit=time_unit)],
        grain=Grain(kind="time", time_unit=time_unit, time_column=ds.dates[0]),
        order_by="time_asc",
    )
    sql = SQLCompiler(ds, cat).compile(plan)
    result = _run_sql(sql)
    return {"kpi": kpi.kpi_id, "time_unit": time_unit,
             "series": [{"period": str(r[0]), "value": r[1]}
                         for r in (result.rows or [])],
             "sql": sql, "ok": result.ok}


@app.tool()
def analyze_metric_breakdown(kpi_id: str, dimension: str,
                              top_n: Optional[int] = None) -> dict:
    """Break a KPI down by a dimension column. Returns ranked rows."""
    from insightflow.plan import (
        AnalyticalPlan, DimRef, IntentKind, MeasureRef, SQLCompiler,
    )
    ds, cat = _dataset_and_catalog()
    kpi = _resolve_kpi(cat, kpi_id)
    if dimension not in ds.columns:
        return {"error": f"dimension {dimension!r} not in dataset",
                 "available": ds.dimensions}
    plan = AnalyticalPlan(
        intent_kind=(IntentKind.TOP_N if top_n else IntentKind.BREAKDOWN),
        table=ds.table,
        measures=[MeasureRef(kpi_id=kpi.kpi_id, formula=kpi.formula,
                              aggregation=kpi.aggregation, unit=kpi.unit)],
        dims=[DimRef(column=dimension)],
        top_n=(int(top_n) if top_n else None),
        order_by="measure_desc",
    )
    sql = SQLCompiler(ds, cat).compile(plan)
    result = _run_sql(sql)
    return {"kpi": kpi.kpi_id, "dimension": dimension, "top_n": top_n,
             "rows": [{"label": r[0], "value": r[-1]}
                       for r in (result.rows or [])],
             "sql": sql, "ok": result.ok}


@app.tool()
def detect_anomalies(kpi_id: str, threshold: float = 2.5,
                       time_unit: str = "month") -> dict:
    """Z-score anomaly detector on a KPI's time series.

    Flags points whose |z| ≥ threshold.
    """
    trend = analyze_trend.func(kpi_id=kpi_id, time_unit=time_unit) \
        if hasattr(analyze_trend, "func") else \
        analyze_trend(kpi_id=kpi_id, time_unit=time_unit)
    if not trend.get("ok"):
        return trend
    series = trend["series"]
    values = [float(p["value"]) for p in series if p.get("value") is not None]
    if len(values) < 4:
        return {"kpi": kpi_id, "method": "zscore",
                 "threshold": threshold, "series": series,
                 "anomalies": [], "note": "insufficient_data"}
    mean = statistics.fmean(values)
    stdev = statistics.pstdev(values) or 1.0
    anomalies = []
    for p in series:
        v = p.get("value")
        if v is None: continue
        z = (float(v) - mean) / stdev
        if abs(z) >= threshold:
            anomalies.append({"period": p["period"], "value": v,
                               "z_score": round(z, 3),
                               "expected": round(mean, 3),
                               "deviation": round(float(v) - mean, 3),
                               "severity": "high" if abs(z) >= 3 else "medium"})
    return {"kpi": kpi_id, "method": "zscore",
             "threshold": threshold, "mean": mean, "stdev": stdev,
             "series": series, "anomalies": anomalies}


@app.tool()
def evaluate_forecast(kpi_id: str, horizon: int = 3,
                       baseline: str = "last_value") -> dict:
    """Simple naive-baseline forecast + MAE on an 80/20 holdout.

    baseline: 'last_value' | 'mean' | 'trailing_mean'.
    """
    trend = analyze_trend(kpi_id=kpi_id, time_unit="month")
    series = trend.get("series") or []
    values = [float(p["value"]) for p in series if p.get("value") is not None]
    n = len(values)
    if n < 4:
        return {"kpi": kpi_id, "baseline": baseline, "horizon": horizon,
                 "forecast": [], "mae": None, "note": "insufficient_data"}
    split = max(2, int(n * 0.8))
    train, test = values[:split], values[split:]

    def predict(hist, k):
        if baseline == "mean":
            return [statistics.fmean(hist)] * k
        if baseline == "trailing_mean":
            w = min(3, len(hist))
            return [statistics.fmean(hist[-w:])] * k
        return [hist[-1]] * k

    preds = predict(train, len(test))
    mae = statistics.fmean([abs(a - b) for a, b in zip(test, preds)]) if preds else None
    future = predict(values, horizon)
    return {"kpi": kpi_id, "baseline": baseline, "horizon": horizon,
             "history_len": n, "train_len": split, "test_len": len(test),
             "mae": mae, "forecast": future,
             "note": "naive baseline — use for sanity-check only"}


@app.tool()
def get_business_metric_definition(kpi_id: str) -> dict:
    """Return the KPI catalog entry: formula, aggregation, aliases, unit."""
    _, cat = _dataset_and_catalog()
    kpi = cat.get(kpi_id)
    if kpi is None:
        return {"error": f"KPI {kpi_id!r} not defined",
                 "available": sorted(cat.all_ids())[:40]}
    return {"kpi_id": kpi.kpi_id, "name": kpi.display_name,
             "aggregation": kpi.aggregation, "formula": kpi.formula,
             "unit": kpi.unit, "required_columns": kpi.required_columns,
             "aliases": kpi.aliases, "ratio_0_1": kpi.ratio_0_1,
             "non_negative": kpi.non_negative}


if __name__ == "__main__":
    app.run(transport="stdio")
