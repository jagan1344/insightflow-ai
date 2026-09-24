"""Dashboard payload + seed/simulate endpoints.

The dashboard now respects the active dataset (2026-09-24). If the
active dataset is `demo`, the historical star-schema logic runs.
If it's an uploaded dataset, KPIs / charts are computed against the
uploaded table using the same column-role inference the adaptive
generator uses. A chart is returned empty when its required
dimension isn't present (rather than showing stale demo data).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from insightflow.execution.executor import get_engine, reset_engine
from insightflow.knowledge.dataset_registry import ActiveDataset, get_active_dataset
from insightflow.knowledge.kpi import KPIS
from insightflow.knowledge.schema_agent import refresh_schema
from insightflow.nlsql.adaptive import (
    _DIM_TOKENS, _METRIC_TOKENS, _pick_column,
)

from .schemas import DashboardPayload, SimpleResponse
from . import realtime


router = APIRouter()


# ---------------------------------------------------------------------------
# Demo star-schema path (unchanged behaviour, isolated as a helper)
# ---------------------------------------------------------------------------

def _demo_monthly(kpi_expr: str) -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT substr(order_date,1,7) AS m, {kpi_expr} AS v "
            f"FROM orders GROUP BY m ORDER BY m"
        )).fetchall()
    return [{"month": r[0], "value": float(r[1] or 0)} for r in rows]


def _demo_by(kpi_expr: str, dim: str) -> list[dict]:
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


def _build_demo_dashboard(version: int) -> dict:
    total_rev = KPIS["total_revenue"].sql_expr
    order_ct = KPIS["order_count"].sql_expr
    aov = KPIS["avg_order_value"].sql_expr
    gm = KPIS["gross_margin"].sql_expr
    engine = get_engine()

    with engine.connect() as conn:
        months = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT substr(order_date,1,7) AS m FROM orders ORDER BY m"
        )).fetchall()]
    kpi_deltas = {k: 0.0 for k in
                  ("total_revenue", "order_count", "avg_order_value", "gross_margin")}
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
                kpi_deltas[key] = round(((curr - prv) / prv * 100.0) if prv else 0.0, 2)

    with engine.connect() as conn:
        overall = {
            "total_revenue": float(conn.execute(text(
                f"SELECT {total_rev} FROM orders")).scalar() or 0),
            "order_count":   float(conn.execute(text(
                f"SELECT {order_ct} FROM orders")).scalar() or 0),
            "avg_order_value": float(conn.execute(text(
                f"SELECT {aov} FROM orders")).scalar() or 0),
            "gross_margin":  float(conn.execute(text(
                f"SELECT {gm} FROM orders")).scalar() or 0),
        }

    return {
        "version": version,
        "kpis": {
            "total_revenue":   {"value": overall["total_revenue"],
                                "unit": "$", "delta_pct": kpi_deltas["total_revenue"]},
            "order_count":     {"value": overall["order_count"],
                                "unit": "orders", "delta_pct": kpi_deltas["order_count"]},
            "avg_order_value": {"value": overall["avg_order_value"],
                                "unit": "$", "delta_pct": kpi_deltas["avg_order_value"]},
            "gross_margin":    {"value": overall["gross_margin"],
                                "unit": "ratio", "delta_pct": kpi_deltas["gross_margin"]},
        },
        "revenue_by_month":    _demo_monthly(total_rev),
        "revenue_by_region":   _demo_by(total_rev, "region"),
        "revenue_by_category": _demo_by(total_rev, "category"),
        "margin_by_category":  _demo_by(gm, "category"),
    }


# ---------------------------------------------------------------------------
# Uploaded-dataset path — computes the same 4 KPIs + 4 charts from the
# ACTUAL columns of the active table. Any chart whose required dim/date
# is missing comes back empty (front-end handles that gracefully).
# ---------------------------------------------------------------------------

def _uploaded_scalar(sql: str) -> float:
    engine = get_engine()
    with engine.connect() as conn:
        v = conn.execute(text(sql)).scalar()
    return float(v) if v is not None else 0.0


def _pick_dim_for(ds: ActiveDataset, dim_kind: str) -> Optional[str]:
    """dim_kind ∈ {'region','category','sub_category', 'segment', 'product', ...}
    Returns physical column name or None."""
    tokens = _DIM_TOKENS.get(dim_kind)
    if not tokens:
        return None
    return _pick_column(ds, tokens, "dimension")


def _first_dimension_column(ds: ActiveDataset) -> Optional[str]:
    """Fallback dimension: the first dimension column in table order."""
    for name, c in ds.columns.items():
        if c.role == "dimension":
            return name
    return None


def _build_uploaded_dashboard(ds: ActiveDataset, version: int) -> dict:
    """Adaptive dashboard for uploaded datasets. Never queries orders."""
    table = ds.table

    # --- pick columns dynamically ---------------------------------
    rev_col = _pick_column(ds, _METRIC_TOKENS["revenue"], "measure")
    if rev_col is None:
        # fall back to first non-cost/-profit/-discount/-quantity measure
        for name, c in ds.columns.items():
            lname = name.lower()
            if c.role == "measure" and not any(
                    t in lname for t in ("cost", "profit", "discount", "qty")):
                rev_col = name
                break
    profit_col = _pick_column(ds, _METRIC_TOKENS["profit"], "measure")
    cost_col = _pick_column(ds, _METRIC_TOKENS["cost"], "measure")
    date_col = next((n for n, c in ds.columns.items() if c.role == "date"), None)

    # Any dim we can use for the region/category charts. We map:
    #   region-ish → chart 1
    #   category-ish → chart 2 (fall back to the FIRST dim if no category col)
    region_col = _pick_dim_for(ds, "region") or _pick_dim_for(ds, "state") \
                 or _pick_dim_for(ds, "country") or _pick_dim_for(ds, "department") \
                 or _pick_dim_for(ds, "segment")
    category_col = _pick_dim_for(ds, "category") or _pick_dim_for(ds, "sub_category")
    if category_col is None:
        # Any dim column that isn't the same as region_col
        for n, c in ds.columns.items():
            if c.role == "dimension" and n != region_col:
                category_col = n
                break
    if region_col is None and category_col is not None:
        # both charts fall back to a single dim if that's all we have
        region_col = category_col

    # --- compute the 4 KPIs ---------------------------------------
    def sum_expr(col: Optional[str]) -> Optional[str]:
        return f'SUM("{col}")' if col else None

    rev_expr = sum_expr(rev_col)
    profit_expr = None
    if profit_col:
        profit_expr = f'SUM("{profit_col}")'
    elif rev_col and cost_col:
        profit_expr = f'SUM("{rev_col}" - "{cost_col}")'
    margin_expr = None
    if profit_expr and rev_expr:
        margin_expr = f"({profit_expr})*1.0/NULLIF({rev_expr},0)"

    total_revenue = _uploaded_scalar(
        f'SELECT {rev_expr} FROM "{table}"') if rev_expr else 0.0
    order_count = _uploaded_scalar(f'SELECT COUNT(*) FROM "{table}"')
    avg_order_value = (total_revenue / order_count) if order_count else 0.0
    gross_margin = _uploaded_scalar(
        f'SELECT {margin_expr} FROM "{table}"') if margin_expr else 0.0

    # --- delta_pct: latest vs previous month (only if date_col) ---
    kpi_deltas = {"total_revenue": 0.0, "order_count": 0.0,
                  "avg_order_value": 0.0, "gross_margin": 0.0}
    if date_col:
        engine = get_engine()
        with engine.connect() as conn:
            months = [r[0] for r in conn.execute(text(
                f'SELECT DISTINCT substr("{date_col}",1,7) AS m '
                f'FROM "{table}" WHERE "{date_col}" IS NOT NULL ORDER BY m'
            )).fetchall() if r[0]]
        if len(months) >= 2:
            last, prev = months[-1], months[-2]
            def bym(expr: str, m: str) -> float:
                if not expr:
                    return 0.0
                sql = (f'SELECT {expr} FROM "{table}" '
                       f'WHERE substr("{date_col}",1,7) = :m')
                engine = get_engine()
                with engine.connect() as conn:
                    v = conn.execute(text(sql), {"m": m}).scalar()
                return float(v) if v is not None else 0.0
            for key, expr in [
                ("total_revenue", rev_expr),
                ("gross_margin", margin_expr),
            ]:
                curr = bym(expr, last)
                prv = bym(expr, prev)
                kpi_deltas[key] = round(((curr - prv) / prv * 100.0) if prv else 0.0, 2)
            # orders / AOV deltas
            def oc(m: str) -> float:
                engine = get_engine()
                with engine.connect() as conn:
                    v = conn.execute(text(
                        f'SELECT COUNT(*) FROM "{table}" '
                        f'WHERE substr("{date_col}",1,7) = :m'), {"m": m}).scalar()
                return float(v or 0)
            oc_last, oc_prev = oc(last), oc(prev)
            kpi_deltas["order_count"] = round(
                ((oc_last - oc_prev) / oc_prev * 100.0) if oc_prev else 0.0, 2)
            rev_last = bym(rev_expr, last) if rev_expr else 0.0
            rev_prev = bym(rev_expr, prev) if rev_expr else 0.0
            aov_last = rev_last / oc_last if oc_last else 0.0
            aov_prev = rev_prev / oc_prev if oc_prev else 0.0
            kpi_deltas["avg_order_value"] = round(
                ((aov_last - aov_prev) / aov_prev * 100.0) if aov_prev else 0.0, 2)

    # --- the 4 series ---------------------------------------------
    def series(dim_col: Optional[str], value_expr: Optional[str],
               label_key: str) -> list[dict]:
        if not dim_col or not value_expr:
            return []
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text(
                f'SELECT "{dim_col}" AS label, {value_expr} AS v '
                f'FROM "{table}" GROUP BY "{dim_col}" ORDER BY v DESC'
            )).fetchall()
        return [{label_key: str(r[0]) if r[0] is not None else "(null)",
                 "value": float(r[1] or 0)} for r in rows]

    revenue_by_month = []
    if date_col and rev_expr:
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text(
                f'SELECT substr("{date_col}",1,7) AS m, {rev_expr} AS v '
                f'FROM "{table}" WHERE "{date_col}" IS NOT NULL '
                f'GROUP BY m ORDER BY m'
            )).fetchall()
        revenue_by_month = [{"month": r[0], "value": float(r[1] or 0)} for r in rows]

    revenue_by_region   = series(region_col,   rev_expr,    "region")
    revenue_by_category = series(category_col, rev_expr,    "category")
    margin_by_category  = series(category_col, margin_expr, "category")

    return {
        "version": version,
        "kpis": {
            "total_revenue":   {"value": total_revenue,   "unit": "$",
                                "delta_pct": kpi_deltas["total_revenue"]},
            "order_count":     {"value": order_count,     "unit": "orders",
                                "delta_pct": kpi_deltas["order_count"]},
            "avg_order_value": {"value": avg_order_value, "unit": "$",
                                "delta_pct": kpi_deltas["avg_order_value"]},
            "gross_margin":    {"value": gross_margin,    "unit": "ratio",
                                "delta_pct": kpi_deltas["gross_margin"]},
        },
        "revenue_by_month":    revenue_by_month,
        "revenue_by_region":   revenue_by_region,
        "revenue_by_category": revenue_by_category,
        "margin_by_category":  margin_by_category,
    }


def build_dashboard(version: int = 0) -> dict:
    """Dispatch on the active dataset. Demo → legacy star-schema logic;
    uploaded → column-adaptive logic against the active table."""
    ds = get_active_dataset()
    if ds.kind == "uploaded":
        return _build_uploaded_dashboard(ds, version)
    return _build_demo_dashboard(version)


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
