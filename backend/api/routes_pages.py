"""Backend endpoints that feed the enterprise dashboard pages.

Every endpoint returns real data from the active dataset — never
fabricated values. Pages that depend on information the dataset can't
provide (forecasts without enough history, anomalies when no date
column exists, etc.) return an `unavailable` flag with a human-readable
reason so the UI can render an "unavailable state" rather than fake
numbers.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query


router = APIRouter(prefix="/api/pages", tags=["pages"])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _dataset_and_catalog():
    from insightflow.knowledge.dataset_registry import get_active_dataset
    from insightflow.knowledge.kpi_catalog import build_catalog
    ds = get_active_dataset()
    return ds, build_catalog(ds)


def _unavailable(reason: str) -> Dict[str, Any]:
    return {"unavailable": True, "reason": reason}


# ---------------------------------------------------------------------------
# /api/pages/explorer — Analytics Explorer page metadata
# ---------------------------------------------------------------------------

@router.get("/explorer")
def explorer_meta() -> Dict[str, Any]:
    """Return the columns, KPIs, and suggested questions for the current
    dataset so the Explorer page can offer typeahead + templates."""
    from insightflow.knowledge.semantic_model import build_semantic_model
    ds, cat = _dataset_and_catalog()
    model = build_semantic_model(ds)
    suggestions: list[str] = []
    rev_kpi = cat.get("total_revenue")
    if rev_kpi and ds.dimensions:
        suggestions.append(f"{rev_kpi.name} by {ds.dimensions[0]}")
    if cat.get("profit") and ds.dates:
        suggestions.append("Profit over time")
    if cat.get("total_revenue") and ds.dates:
        suggestions.append("Compare revenue in June vs July")
    return {
        "dataset": {"id": ds.id, "name": ds.name, "table": ds.table,
                     "kind": ds.kind},
        "columns": [{"name": c.name, "role": c.role,
                      "sql_type": c.sql_type}
                     for c in ds.columns.values()],
        "measures": ds.measures,
        "dimensions": ds.dimensions,
        "dates": ds.dates,
        "kpis": [{"id": k.kpi_id, "name": k.display_name,
                   "aggregation": k.aggregation, "formula": k.formula,
                   "unit": k.unit, "aliases": k.aliases[:6]}
                  for k in cat.kpis.values()],
        "grain": model.grain,
        "suggested_questions": suggestions,
    }


# ---------------------------------------------------------------------------
# /api/pages/anomaly — simple z-score anomaly detection
# ---------------------------------------------------------------------------

@router.get("/anomaly")
def anomaly_detection(kpi_id: str = Query("total_revenue"),
                      threshold: float = Query(2.0),
                      time_unit: str = Query("month")) -> Dict[str, Any]:
    from insightflow.plan import (
        AnalyticalPlan, DimRef, Grain, IntentKind, MeasureRef, SQLCompiler,
    )
    from insightflow.execution.executor import run_sql
    import statistics
    ds, cat = _dataset_and_catalog()
    kpi = cat.get(kpi_id)
    if kpi is None:
        return _unavailable(f"KPI {kpi_id!r} not defined on {ds.name!r}")
    if not ds.dates:
        return _unavailable("dataset has no date column")
    plan = AnalyticalPlan(
        intent_kind=IntentKind.TREND, table=ds.table,
        measures=[MeasureRef(kpi_id=kpi.kpi_id, formula=kpi.formula,
                              aggregation=kpi.aggregation, unit=kpi.unit)],
        dims=[DimRef(column=ds.dates[0], is_time=True,
                      time_unit=time_unit)],
        grain=Grain(kind="time", time_unit=time_unit,
                     time_column=ds.dates[0]),
        order_by="time_asc",
    )
    sql = SQLCompiler(ds, cat).compile(plan)
    r = run_sql(sql)
    if not r.ok:
        return {"unavailable": True, "reason": r.error}
    series = [{"period": str(row[0]), "value": row[1]} for row in r.rows]
    values = [float(p["value"]) for p in series
               if p.get("value") is not None]
    if len(values) < 4:
        return {"kpi": kpi_id, "series": series, "anomalies": [],
                 "note": "insufficient_data_for_zscore",
                 "mean": None, "stdev": None, "sql": sql}
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
    return {"kpi": kpi.kpi_id, "name": kpi.display_name,
             "method": "zscore", "threshold": threshold,
             "mean": round(mean, 3), "stdev": round(stdev, 3),
             "series": series, "anomalies": anomalies, "sql": sql}


# ---------------------------------------------------------------------------
# /api/pages/forecast — naive baseline forecast with MAE
# ---------------------------------------------------------------------------

@router.get("/forecast")
def forecast(kpi_id: str = Query("total_revenue"),
              horizon: int = Query(3, ge=1, le=12),
              baseline: str = Query("last_value")) -> Dict[str, Any]:
    import statistics
    from insightflow.plan import (
        AnalyticalPlan, DimRef, Grain, IntentKind, MeasureRef, SQLCompiler,
    )
    from insightflow.execution.executor import run_sql
    ds, cat = _dataset_and_catalog()
    kpi = cat.get(kpi_id)
    if kpi is None:
        return _unavailable(f"KPI {kpi_id!r} not defined")
    if not ds.dates:
        return _unavailable("dataset has no date column")
    plan = AnalyticalPlan(
        intent_kind=IntentKind.TREND, table=ds.table,
        measures=[MeasureRef(kpi_id=kpi.kpi_id, formula=kpi.formula,
                              aggregation=kpi.aggregation, unit=kpi.unit)],
        dims=[DimRef(column=ds.dates[0], is_time=True, time_unit="month")],
        grain=Grain(kind="time", time_unit="month", time_column=ds.dates[0]),
        order_by="time_asc",
    )
    sql = SQLCompiler(ds, cat).compile(plan)
    r = run_sql(sql)
    if not r.ok:
        return _unavailable(r.error)
    series = [{"period": str(row[0]), "value": row[1]} for row in r.rows]
    values = [float(p["value"]) for p in series
               if p.get("value") is not None]
    n = len(values)
    if n < 4:
        return {"kpi": kpi_id, "name": kpi.display_name,
                 "unavailable": True,
                 "reason": "need at least 4 monthly points to forecast",
                 "series": series}
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
    return {"kpi": kpi.kpi_id, "name": kpi.display_name,
             "baseline": baseline, "horizon": horizon,
             "history": series,
             "mae": mae, "test_len": len(test),
             "forecast": [{"period": f"+{i+1}", "value": v}
                           for i, v in enumerate(future)],
             "note": "naive baseline — sanity check only"}


# ---------------------------------------------------------------------------
# /api/pages/recommendations — surfaced from the data, never fabricated
# ---------------------------------------------------------------------------

@router.get("/recommendations")
def recommendations() -> Dict[str, Any]:
    from insightflow.execution.executor import run_sql
    ds, cat = _dataset_and_catalog()
    items: list[dict] = []

    # Loss-making groups: profit < 0 by first dim
    profit = cat.get("profit")
    if profit and ds.dimensions:
        dim = ds.dimensions[0]
        sql = (f'SELECT "{dim}" AS g, {profit.formula} AS p '
                f'FROM "{ds.table}" GROUP BY "{dim}" '
                f'HAVING {profit.formula} < 0 ORDER BY p ASC LIMIT 3')
        r = run_sql(sql)
        if r.ok and r.rows:
            for row in r.rows:
                items.append({
                    "observation": f"{dim} '{row[0]}' is loss-making",
                    "metric": "profit",
                    "value": float(row[1]) if row[1] is not None else None,
                    "evidence_sql": sql,
                    "suggested_action": (
                        f"Review pricing / cost structure for {dim} "
                        f"'{row[0]}' — total profit is negative."),
                    "limitations": "correlation only, no causal claim",
                })

    # Fastest-growing dim segment (if date + dim present)
    rev = cat.get("total_revenue")
    if rev and ds.dates and ds.dimensions and len(items) < 3:
        dim = ds.dimensions[0]
        sql = (
            f'WITH monthly AS ('
            f'SELECT substr("{ds.dates[0]}",1,7) AS m, '
            f'"{dim}" AS g, {rev.formula} AS v '
            f'FROM "{ds.table}" GROUP BY m, "{dim}") '
            f'SELECT g, MIN(v) AS lo, MAX(v) AS hi FROM monthly '
            f'GROUP BY g ORDER BY (MAX(v) - MIN(v)) DESC LIMIT 1'
        )
        r = run_sql(sql)
        if r.ok and r.rows:
            row = r.rows[0]
            items.append({
                "observation": f"{dim} '{row[0]}' shows widest monthly revenue swing",
                "metric": "total_revenue_range",
                "value": {"low": row[1], "high": row[2]},
                "evidence_sql": sql,
                "suggested_action": (
                    "Investigate what drives the variance — promotion "
                    "schedule, seasonality, or supply constraints."),
                "limitations": "variance != trend; need more context",
            })

    if not items:
        return {"recommendations": [], "note": "no actionable patterns found"}
    return {"recommendations": items, "generated_at": datetime.utcnow().isoformat()}


# ---------------------------------------------------------------------------
# /api/pages/reports — list + build
# ---------------------------------------------------------------------------

@router.get("/reports/summary")
def report_summary(format: str = Query("markdown")) -> Dict[str, Any]:
    """Executive summary — delegates to the reporting MCP server when
    available, falls back to inline computation when it isn't."""
    try:
        from insightflow.mcp_integration import get_manager
        mgr = get_manager()
        mgr.connect("reporting", timeout=15)
        r = mgr.call("reporting", "generate_summary_report",
                      {"format": format})
        if r.ok:
            return {"source": "mcp:reporting",
                     "content": r.content, "duration_ms": r.duration_ms}
    except Exception:
        pass
    # Fallback: do it inline
    from insightflow.execution.executor import run_sql
    from sqlalchemy import text
    ds, cat = _dataset_and_catalog()
    out_kpis: list[dict] = []
    for kid in ("total_revenue", "profit", "gross_margin", "order_count"):
        kpi = cat.get(kid)
        if kpi is None: continue
        try:
            from insightflow.execution.executor import get_engine
            with get_engine().connect() as conn:
                v = conn.execute(text(
                    f'SELECT {kpi.formula} FROM "{ds.table}"')).scalar()
            out_kpis.append({"kpi_id": kpi.kpi_id, "name": kpi.display_name,
                              "value": float(v) if v is not None else None,
                              "unit": kpi.unit})
        except Exception as e:
            out_kpis.append({"kpi_id": kpi.kpi_id, "error": str(e)})
    return {"source": "fallback",
             "content": {"title": f"Executive Summary — {ds.name}",
                          "generated_at": datetime.utcnow().isoformat(),
                          "dataset": ds.table, "kpis": out_kpis}}


# ---------------------------------------------------------------------------
# /api/pages/sources — data source status + dataset switcher state
# ---------------------------------------------------------------------------

@router.get("/sources")
def sources() -> Dict[str, Any]:
    """Describe the configured database + available datasets. Never
    exposes the connection URL or secrets."""
    from insightflow.execution.executor import get_engine
    from insightflow.knowledge.dataset_registry import (
        get_active_dataset, list_datasets,
    )
    from sqlalchemy import inspect
    engine = get_engine()
    try:
        dialect = engine.dialect.name
    except Exception:
        dialect = "unknown"
    insp = inspect(engine)
    try:
        tables = insp.get_table_names()
    except Exception:
        tables = []
    active = get_active_dataset()
    return {
        "database": {"dialect": dialect,
                      "table_count": len(tables),
                      "tables": sorted(tables)},
        "datasets": list_datasets(),
        "active_dataset": {
            "id": active.id, "name": active.name, "table": active.table,
            "kind": active.kind, "measures": active.measures,
            "dimensions": active.dimensions, "dates": active.dates,
        },
    }


# ---------------------------------------------------------------------------
# /api/pages/semantic — business metrics / semantic model inspector
# ---------------------------------------------------------------------------

@router.get("/semantic")
def semantic_model() -> Dict[str, Any]:
    from insightflow.knowledge.semantic_model import build_semantic_model
    ds, cat = _dataset_and_catalog()
    model = build_semantic_model(ds)
    return {
        "dataset": {"id": ds.id, "name": ds.name, "table": ds.table,
                     "kind": ds.kind},
        "model": model.as_dict(),
        "kpis": [{
            "id": k.kpi_id, "name": k.display_name,
            "aggregation": k.aggregation, "formula": k.formula,
            "unit": k.unit, "aliases": k.aliases,
            "required_columns": k.required_columns,
            "ratio_0_1": k.ratio_0_1, "non_negative": k.non_negative,
        } for k in cat.kpis.values()],
    }


# ---------------------------------------------------------------------------
# /api/pages/settings — read-only runtime status
# ---------------------------------------------------------------------------

@router.get("/settings")
def settings() -> Dict[str, Any]:
    import os
    import sys
    try:
        from insightflow.mcp_integration import load_config, get_manager
        mcp_cfg = load_config()
        mcp_servers = [{"name": s.name, "enabled": s.enabled,
                         "transport": s.transport,
                         "connected": s.name in get_manager().connected_servers()}
                        for s in mcp_cfg.servers]
    except Exception as e:
        mcp_servers = [{"error": str(e)}]
    try:
        from insightflow.config import settings as s
        thresholds = {"threshold_high": s.threshold_high,
                       "threshold_low": s.threshold_low}
        weights = dict(s.confidence_weights)
    except Exception:
        thresholds = {}; weights = {}
    return {
        "python_version": sys.version.split()[0],
        "database_url_configured": bool(os.environ.get("DATABASE_URL")),
        "llm_provider": os.environ.get("LLM_PROVIDER", "offline"),
        "cors_origins": os.environ.get("CORS_ORIGINS", ""),
        "mcp_servers": mcp_servers,
        "confidence_thresholds": thresholds,
        "confidence_weights": weights,
    }
