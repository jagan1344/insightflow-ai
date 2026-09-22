"""Result summarisation + diagnostic root-cause analysis."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy import text

from ..execution.executor import QueryResult, get_engine
from ..knowledge.kpi import KPI


@dataclass
class Contributor:
    dimension: str
    name: str
    prev: float
    curr: float
    delta: float
    pct: float


@dataclass
class Analysis:
    summary: str
    headline_value: Optional[float] = None
    contributors: List[Contributor] = field(default_factory=list)
    prev_total: Optional[float] = None
    curr_total: Optional[float] = None


def _fmt(v: Optional[float], unit: str = "") -> str:
    if v is None:
        return "n/a"
    if unit == "ratio":
        return f"{v * 100:.1f}%"
    if unit == "count":
        return f"{v:,.0f}"
    if unit == "currency":
        return f"{v:,.2f}"
    return f"{v:,.2f}"


def _month_range(month: int) -> tuple[str, str]:
    from datetime import date
    yy = 2026
    start = date(yy, month, 1).isoformat()
    end_month = month + 1
    end_year = yy
    if end_month > 12:
        end_month = 1
        end_year = yy + 1
    end = date(end_year, end_month, 1).isoformat()
    return start, end


def _kpi_totals(kpi: KPI, month: int) -> float:
    start, end = _month_range(month)
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text(
            f"SELECT {kpi.sql_expr} AS v FROM orders "
            f"WHERE order_date >= :s AND order_date < :e"
        ), {"s": start, "e": end}).fetchone()
    if row is None or row[0] is None:
        return 0.0
    return float(row[0])


def _kpi_by(kpi: KPI, month: int, dim: str) -> list[tuple[str, float]]:
    start, end = _month_range(month)
    if dim == "region":
        sql = (f"SELECT regions.region_name, {kpi.sql_expr} "
               f"FROM orders JOIN regions ON regions.region_id = orders.region_id "
               f"WHERE order_date >= :s AND order_date < :e "
               f"GROUP BY regions.region_name")
    elif dim == "category":
        sql = (f"SELECT products.category, {kpi.sql_expr} "
               f"FROM orders JOIN products ON products.product_id = orders.product_id "
               f"WHERE order_date >= :s AND order_date < :e "
               f"GROUP BY products.category")
    else:
        raise ValueError(f"unsupported dim: {dim}")

    engine = get_engine()
    with engine.connect() as conn:
        return [(str(r[0]), float(r[1] or 0.0))
                for r in conn.execute(text(sql), {"s": start, "e": end}).fetchall()]


def analyse(kpi: Optional[KPI], result: QueryResult,
            intent: str, month: Optional[int]) -> Analysis:
    if not result.ok:
        return Analysis(summary=f"Query failed: {result.error}")

    if not result.rows:
        return Analysis(summary="No rows returned for this question.")

    unit = kpi.unit if kpi else ""
    name = kpi.name if kpi else "value"

    # ---------- diagnostic ----------
    if intent == "diagnostic" and month is not None and kpi is not None:
        curr = _kpi_totals(kpi, month)
        prev_month = month - 1 if month > 1 else 12
        prev = _kpi_totals(kpi, prev_month)
        delta = curr - prev
        pct = (delta / prev * 100.0) if prev else 0.0

        # per-dimension contributors
        contributors: list[Contributor] = []
        for dim in ("category", "region"):
            prev_map = dict(_kpi_by(kpi, prev_month, dim))
            curr_map = dict(_kpi_by(kpi, month, dim))
            for name_val in set(prev_map) | set(curr_map):
                p = prev_map.get(name_val, 0.0)
                c = curr_map.get(name_val, 0.0)
                d = c - p
                pc = (d / p * 100.0) if p else 0.0
                contributors.append(Contributor(dim, name_val, p, c, d, pc))
        contributors.sort(key=lambda x: x.delta)  # most negative first
        top_neg = [c for c in contributors if c.delta < 0][:2]

        headline = (
            f"{name} changed from {_fmt(prev, unit)} to {_fmt(curr, unit)} "
            f"({_fmt(delta, unit)}, {pct:+.1f}%)."
        )
        if top_neg:
            joined = "; ".join(
                f"{c.dimension} '{c.name}' {c.pct:+.1f}% ({_fmt(c.delta, unit)})"
                for c in top_neg
            )
            summary = f"{headline} The largest negative contributors were {joined}."
        else:
            summary = headline

        return Analysis(
            summary=summary,
            headline_value=curr,
            contributors=contributors,
            prev_total=prev,
            curr_total=curr,
        )

    # ---------- scalar aggregate ----------
    if intent == "aggregate" or (len(result.rows) == 1 and len(result.columns) == 1):
        val = None
        try:
            val = float(result.rows[0][-1]) if result.rows[0][-1] is not None else None
        except (TypeError, ValueError):
            pass
        if month:
            summary = f"{name} for month {month:02d}/2026 is {_fmt(val, unit)}."
        else:
            summary = f"{name} is {_fmt(val, unit)}."
        return Analysis(summary=summary, headline_value=val)

    # ---------- breakdown / trend ----------
    n = len(result.rows)
    # find numeric column
    val_idx = len(result.columns) - 1
    label_idx = 0
    try:
        top_label = result.rows[0][label_idx]
        top_val = float(result.rows[0][val_idx])
        summary = (f"{name} across {n} {result.columns[label_idx]} values — "
                   f"leader: {top_label} ({_fmt(top_val, unit)}).")
    except (TypeError, ValueError):
        summary = f"{name} across {n} rows returned."
    return Analysis(summary=summary)
