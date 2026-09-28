"""Chart-spec chooser."""
from __future__ import annotations

from typing import Any, Dict

from ..execution.executor import QueryResult


def chart_spec(result: QueryResult, intent: str) -> Dict[str, Any]:
    if not result.ok or not result.rows:
        return {"kind": "none"}

    if intent == "trend":
        return {
            "kind": "line",
            "x": result.columns[0],
            "y": result.columns[-1],
        }

    if len(result.rows) == 1 and len(result.columns) == 1:
        return {
            "kind": "metric",
            "x": None,
            "y": result.columns[-1],
        }

    if len(result.columns) >= 2 and len(result.rows) > 1:
        # Prefer the share column when present so a share_of_total
        # question's bars show % of total, not raw values.
        lower_cols = [c.lower() for c in result.columns]
        y_col = result.columns[-1]
        y_unit = None
        for i, c in enumerate(lower_cols):
            if c == "share" or c.endswith("_share") or c.endswith("_pct"):
                y_col = result.columns[i]
                y_unit = "percent"
                break
        spec = {
            "kind": "bar",
            "x": result.columns[0],
            "y": y_col,
        }
        if y_unit:
            spec["y_unit"] = y_unit
        return spec

    return {"kind": "metric", "x": None, "y": result.columns[-1]}
