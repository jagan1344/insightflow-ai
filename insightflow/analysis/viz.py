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
        return {
            "kind": "bar",
            "x": result.columns[0],
            "y": result.columns[-1],
        }

    return {"kind": "metric", "x": None, "y": result.columns[-1]}
