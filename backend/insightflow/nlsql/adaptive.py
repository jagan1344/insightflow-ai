"""Schema-adaptive NL→SQL for uploaded datasets.

Fired only when `dataset_registry.get_active_dataset().kind == "uploaded"`.
The demo dataset continues to use `generator._rule_generate` verbatim so
none of the existing behaviour changes.

What the adaptive path does:

1. Read the active dataset's real columns and their inferred roles
   (measure / dimension / date), from the physical table introspection
   done in `dataset_registry.py`.
2. Fuzzy-match phrases in the user's question to those columns.
   `revenue`/`sales`/`amount` → the first measure column whose name
   contains one of those tokens (or a numeric fallback if none matches).
   `region`/`state`/`department` → same, over dimension columns.
3. Emit SQL referencing the actual table name and actual column names
   as bound in the SELECT. Never a hardcoded `FROM orders`.
4. If a requested metric or dimension has no plausible column, mark it
   `unavailable` on the returned `QueryIntent` so the orchestrator
   CLARIFIES instead of guessing.
"""
from __future__ import annotations

import re
from typing import Optional

from ..knowledge.dataset_registry import ActiveDataset, get_active_dataset
from ..knowledge.kpi import KPI, KPIS


# ---------------------------------------------------------------------------
# Column-fuzzy matching
# ---------------------------------------------------------------------------

# Metric intent → tokens we look for in a measure-column name.
_METRIC_TOKENS: dict[str, tuple[str, ...]] = {
    "revenue":       ("revenue", "sales", "amount", "turnover", "gross"),
    "profit":        ("profit", "gain"),
    "cost":          ("cost", "cogs", "expense"),
    "discount":      ("discount"),
    "quantity":      ("quantity", "qty", "units"),
    "orders":        ("order", "transaction"),
    "margin":        ("margin",),
}

# Dimension intent → tokens we look for in a dim-column name.
_DIM_TOKENS: dict[str, tuple[str, ...]] = {
    "region":       ("region",),
    "state":        ("state", "province"),
    "city":         ("city", "town"),
    "country":      ("country", "nation"),
    "category":     ("category",),
    "sub_category": ("sub_category", "subcategory", "sub-category"),
    "product":      ("product", "item", "sku"),
    "customer":     ("customer", "client"),
    "segment":      ("segment", "tier"),
    "channel":      ("channel", "platform"),
    "department":   ("department", "dept", "division", "team"),
}


def _pick_column(ds: ActiveDataset, tokens: tuple[str, ...],
                 required_role: str) -> Optional[str]:
    """Return the best-matching column of the given role, or None."""
    for name, col in ds.columns.items():
        if col.role != required_role:
            continue
        lower = name.lower().replace(" ", "_").replace("-", "_")
        for tok in tokens:
            if tok in lower:
                return name
    return None


def _resolve_metric(ds: ActiveDataset, metric_key: str) -> Optional[dict]:
    """Return {expr, alias} for the metric expressed against actual columns."""
    if metric_key == "orders":
        return {"expr": "COUNT(*)", "alias": "order_count"}
    if metric_key == "quantity":
        col = _pick_column(ds, _METRIC_TOKENS["quantity"], "measure")
        return {"expr": f'SUM("{col}")', "alias": "units_sold"} if col else None
    if metric_key == "revenue":
        col = _pick_column(ds, _METRIC_TOKENS["revenue"], "measure")
        if col is None:
            # last-ditch: any numeric-looking measure not tagged profit/cost/discount
            for name, c in ds.columns.items():
                lname = name.lower()
                if c.role == "measure" and not any(
                        t in lname for t in ("cost", "profit", "discount", "qty")):
                    col = name
                    break
        return {"expr": f'SUM("{col}")', "alias": "total_revenue"} if col else None
    if metric_key == "profit":
        # Prefer an explicit profit column; else derive from revenue-cost.
        col = _pick_column(ds, _METRIC_TOKENS["profit"], "measure")
        if col:
            return {"expr": f'SUM("{col}")', "alias": "profit"}
        rev = _pick_column(ds, _METRIC_TOKENS["revenue"], "measure")
        cost = _pick_column(ds, _METRIC_TOKENS["cost"], "measure")
        if rev and cost:
            return {"expr": f'SUM("{rev}" - "{cost}")', "alias": "profit"}
        return None
    if metric_key == "gross_margin":
        col_p = _pick_column(ds, _METRIC_TOKENS["profit"], "measure")
        rev = _pick_column(ds, _METRIC_TOKENS["revenue"], "measure")
        if col_p and rev:
            return {"expr": f'SUM("{col_p}") * 1.0 / SUM("{rev}")',
                    "alias": "gross_margin"}
        cost = _pick_column(ds, _METRIC_TOKENS["cost"], "measure")
        if rev and cost:
            return {"expr": f'SUM("{rev}" - "{cost}") * 1.0 / SUM("{rev}")',
                    "alias": "gross_margin"}
        return None
    if metric_key == "avg_order_value":
        rev = _pick_column(ds, _METRIC_TOKENS["revenue"], "measure")
        if rev:
            return {"expr": f'SUM("{rev}") * 1.0 / COUNT(*)',
                    "alias": "avg_order_value"}
        return None
    if metric_key == "discount_rate":
        d = _pick_column(ds, _METRIC_TOKENS["discount"], "measure")
        if d:
            return {"expr": f'AVG("{d}")', "alias": "avg_discount"}
        return None
    if metric_key == "order_count":
        return {"expr": "COUNT(*)", "alias": "order_count"}
    if metric_key == "units_sold":
        col = _pick_column(ds, _METRIC_TOKENS["quantity"], "measure")
        return {"expr": f'SUM("{col}")', "alias": "units_sold"} if col else None
    if metric_key == "total_revenue":
        return _resolve_metric(ds, "revenue")
    return None


def _resolve_dimension(ds: ActiveDataset, dim: str) -> Optional[str]:
    """Return the physical column name for the requested dimension, or None."""
    if dim == "month":
        d = _first_date(ds)
        return d
    tokens = _DIM_TOKENS.get(dim)
    if tokens:
        picked = _pick_column(ds, tokens, "dimension")
        if picked:
            return picked
    # last-ditch: exact match (case-insensitive) on any column name
    dl = dim.lower()
    for name, col in ds.columns.items():
        if name.lower() == dl:
            return name
    return None


def _first_date(ds: ActiveDataset) -> Optional[str]:
    for name, col in ds.columns.items():
        if col.role == "date":
            return name
    return None


# ---------------------------------------------------------------------------
# The adaptive generator
# ---------------------------------------------------------------------------

def _month_predicate(date_col: str, month: int, year: int = 2026) -> str:
    return (f"substr(\"{date_col}\",1,7) = '{year:04d}-{month:02d}'")


def _range_year(date_col: str) -> tuple[int, int]:
    """Placeholder — returns (2020, 2030) so no filter is applied when
    year is unknown. Kept for future use."""
    return (2020, 2030)


def adaptive_generate(intent, question: str,
                      ds: Optional[ActiveDataset] = None) -> Optional[dict]:
    """Given the extracted intent, produce SQL against the active
    uploaded dataset. Returns a dict {sql, unavailable, dim, metric,
    intent_type} or None to fall through to the legacy path.

    `unavailable` lists any intent element that couldn't be mapped to
    a real column — the caller (orchestrator) uses it to CLARIFY.
    """
    if ds is None:
        ds = get_active_dataset()
    if ds.kind != "uploaded":
        return None
    if not ds.columns:
        return None

    unavailable: list[str] = []

    # 1) Metrics — map every requested intent metric to a real column.
    resolved_metrics: list[dict] = []
    for m in intent.metrics or ["total_revenue"]:
        resolved = _resolve_metric(ds, m)
        if resolved is None:
            unavailable.append(f"metric:{m}")
        else:
            resolved_metrics.append({"key": m, **resolved})

    # 2) Dimensions — map to real columns.
    resolved_dims: list[dict] = []
    for d in intent.dimensions:
        col = _resolve_dimension(ds, d)
        if col is None:
            unavailable.append(f"dim:{d}")
        else:
            resolved_dims.append({"key": d, "column": col})

    # 3) If nothing survived, bail — CLARIFY
    if not resolved_metrics and not resolved_dims:
        return {"sql": "", "unavailable": unavailable, "dim": None,
                "metric": None, "intent_type": "unknown"}

    # 4) Build SELECT / GROUP BY.
    select_parts: list[str] = []
    group_by_parts: list[str] = []
    for d in resolved_dims:
        if d["key"] == "month":
            expr = f'substr("{d["column"]}",1,7)'
            select_parts.append(f"{expr} AS month")
            group_by_parts.append(expr)
        else:
            alias = d["key"] if d["key"] not in ("state", "city") else d["key"]
            select_parts.append(f'"{d["column"]}" AS {alias}')
            group_by_parts.append(f'"{d["column"]}"')

    # Metric ordering: loss-filter metric last (so analyzer shows it).
    primary_metric = None
    for f in intent.filters:
        if f.get("kind") == "metric_lt_zero":
            primary_metric = f.get("metric")
            break
    if primary_metric is None and resolved_metrics:
        primary_metric = resolved_metrics[0]["key"]

    ordered = [m for m in resolved_metrics if m["key"] != primary_metric] + \
              [m for m in resolved_metrics if m["key"] == primary_metric]
    for m in ordered:
        select_parts.append(f"{m['expr']} AS {m['alias']}")

    # 5) HAVING (loss filter) + ORDER BY + LIMIT
    having_clause = ""
    order_by_clause = ""
    limit_clause = ""

    for f in intent.filters:
        if f.get("kind") == "metric_lt_zero":
            m = next((r for r in resolved_metrics
                      if r["key"] == f.get("metric")), None)
            if m is not None:
                having_clause = f" HAVING {m['expr']} < 0"
                order_by_clause = f" ORDER BY {m['alias']} ASC"
        elif f.get("kind") == "limit":
            direction = "ASC" if f.get("order") == "asc" else "DESC"
            if resolved_metrics:
                order_by_clause = (f" ORDER BY {resolved_metrics[0]['alias']} "
                                   f"{direction}")
            limit_clause = f" LIMIT {int(f.get('n', 5))}"

    # Chronological trend order for month dim without explicit ranking.
    if resolved_dims and any(d["key"] == "month" for d in resolved_dims) \
            and not order_by_clause:
        order_by_clause = " ORDER BY month"
    elif not order_by_clause and resolved_dims and resolved_metrics:
        order_by_clause = f" ORDER BY {resolved_metrics[0]['alias']} DESC"

    sql = "SELECT " + ", ".join(select_parts) + f' FROM "{ds.table}"'
    if group_by_parts:
        sql += " GROUP BY " + ", ".join(group_by_parts)
    sql += having_clause + order_by_clause + limit_clause

    intent_type = intent.analysis_type or (
        "breakdown" if resolved_dims else "aggregate")
    if any(f.get("kind") == "metric_lt_zero" for f in intent.filters):
        intent_type = "ranking"

    return {
        "sql": sql,
        "unavailable": unavailable,
        "dim": resolved_dims[0]["key"] if resolved_dims else None,
        "metric": resolved_metrics[0]["key"] if resolved_metrics else None,
        "intent_type": intent_type,
        "resolved_metrics": resolved_metrics,
        "resolved_dims": resolved_dims,
    }
