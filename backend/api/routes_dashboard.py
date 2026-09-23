"""Dashboard payload + seed/simulate endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from insightflow.execution.executor import get_engine, reset_engine
from insightflow.knowledge.kpi import KPIS
from insightflow.knowledge.schema_agent import refresh_schema

from .schemas import DashboardPayload, SimpleResponse
from . import realtime


router = APIRouter()


# ---------------------------------------------------------------------------
def _monthly_series(kpi_expr: str) -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT substr(order_date,1,7) AS m, {kpi_expr} AS v "
            f"FROM orders GROUP BY m ORDER BY m"
        )).fetchall()
    return [{"month": r[0], "value": float(r[1] or 0)} for r in rows]


def _by(kpi_expr: str, dim: str) -> list[dict]:
    if dim == "region":
        sql = (f"SELECT regions.region_name AS label, {kpi_expr} AS v "
               f"FROM orders JOIN regions ON regions.region_id = orders.region_id "
               f"GROUP BY regions.region_name ORDER BY v DESC")
        key = "region"
    elif dim == "category":
        sql = (f"SELECT products.category AS label, {kpi_expr} AS v "
               f"FROM orders JOIN products ON products.product_id = orders.product_id "
               f"GROUP BY products.category ORDER BY v DESC")
        key = "category"
    else:
        raise ValueError(dim)
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
    return [{key: r[0], "value": float(r[1] or 0)} for r in rows]


def build_dashboard(version: int = 0) -> dict:
    engine = get_engine()
    total_rev = KPIS["total_revenue"].sql_expr
    order_ct = KPIS["order_count"].sql_expr
    aov = KPIS["avg_order_value"].sql_expr
    gm = KPIS["gross_margin"].sql_expr

    # Latest month vs previous month for delta_pct
    with engine.connect() as conn:
        months = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT substr(order_date,1,7) AS m FROM orders ORDER BY m"
        )).fetchall()]
    kpi_deltas = {}
    if len(months) >= 2:
        last, prev = months[-1], months[-2]
        with engine.connect() as conn:
            def one(expr: str, m: str) -> float:
                v = conn.execute(text(
                    f"SELECT {expr} FROM orders WHERE substr(order_date,1,7)=:m"
                ), {"m": m}).scalar()
                return float(v) if v is not None else 0.0
            for key, expr in [
                ("total_revenue", total_rev),
                ("order_count", order_ct),
                ("avg_order_value", aov),
                ("gross_margin", gm),
            ]:
                curr = one(expr, last)
                prv = one(expr, prev)
                delta = ((curr - prv) / prv * 100.0) if prv else 0.0
                kpi_deltas[key] = round(delta, 2)
    else:
        for key in ("total_revenue", "order_count", "avg_order_value", "gross_margin"):
            kpi_deltas[key] = 0.0

    with engine.connect() as conn:
        overall_totals = {
            "total_revenue": float(conn.execute(text(f"SELECT {total_rev} FROM orders")).scalar() or 0),
            "order_count":   float(conn.execute(text(f"SELECT {order_ct} FROM orders")).scalar() or 0),
            "avg_order_value": float(conn.execute(text(f"SELECT {aov} FROM orders")).scalar() or 0),
            "gross_margin":  float(conn.execute(text(f"SELECT {gm} FROM orders")).scalar() or 0),
        }

    kpis = {
        "total_revenue": {"value": overall_totals["total_revenue"], "unit": "$",
                          "delta_pct": kpi_deltas["total_revenue"]},
        "order_count":   {"value": overall_totals["order_count"], "unit": "orders",
                          "delta_pct": kpi_deltas["order_count"]},
        "avg_order_value": {"value": overall_totals["avg_order_value"], "unit": "$",
                            "delta_pct": kpi_deltas["avg_order_value"]},
        "gross_margin":  {"value": overall_totals["gross_margin"], "unit": "ratio",
                          "delta_pct": kpi_deltas["gross_margin"]},
    }
    return {
        "version": version,
        "kpis": kpis,
        "revenue_by_month":    _monthly_series(total_rev),
        "revenue_by_region":   _by(total_rev, "region"),
        "revenue_by_category": _by(total_rev, "category"),
        "margin_by_category":  _by(gm, "category"),
    }


# ---------------------------------------------------------------------------

@router.get("/api/dashboard", response_model=DashboardPayload)
def get_dashboard():
    try:
        return build_dashboard(version=realtime.state.version)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/kpis")
def get_kpis():
    return {
        k: {"name": v.name, "sql_expr": v.sql_expr, "description": v.description,
            "unit": v.unit, "ratio_0_1": v.ratio_0_1}
        for k, v in KPIS.items()
    }


@router.get("/api/schema")
def get_schema():
    from insightflow.knowledge.schema_agent import get_schema as _get
    return {"tables": _get().tables}


@router.post("/api/seed", response_model=SimpleResponse)
def reseed():
    """Reseed the demo dataset AND make it active. Any uploaded datasets
    are left alone (still queryable via `POST /api/datasets/activate/<id>`)."""
    import runpy
    from pathlib import Path
    seed_path = Path(__file__).resolve().parent.parent / "data" / "seed.py"
    runpy.run_path(str(seed_path), run_name="__main__")
    reset_engine()
    refresh_schema()
    # switch active back to demo
    try:
        from insightflow.knowledge.dataset_registry import set_active, DEMO_ID
        set_active(DEMO_ID)
    except Exception:
        pass
    realtime.state.mark_changed()
    from insightflow.execution.executor import run_sql
    n = run_sql("SELECT COUNT(*) FROM orders").rows[0][0]
    return SimpleResponse(ok=True, detail="reseeded (demo dataset is active)",
                          row_count=int(n))


@router.post("/api/simulate/start", response_model=SimpleResponse)
def simulate_start(rate: float = 2.0, batch: int = 3):
    started = realtime.simulator.start(rate_seconds=rate, batch=batch)
    return SimpleResponse(ok=started, detail="started" if started else "already running")


@router.post("/api/simulate/stop", response_model=SimpleResponse)
def simulate_stop():
    stopped = realtime.simulator.stop()
    return SimpleResponse(ok=stopped, detail="stopped" if stopped else "not running")


@router.get("/api/simulate/status", response_model=SimpleResponse)
def simulate_status():
    running = realtime.simulator.is_running()
    return SimpleResponse(ok=True, detail="running" if running else "stopped")
