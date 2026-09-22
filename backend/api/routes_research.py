"""Read-only endpoint that serves the pre-computed research results.

Nothing runs on request — the endpoint just loads the JSON artefacts
written by the evaluation scripts. If they're missing, returns an
explicit `not_ready` payload rather than fabricating anything.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter


router = APIRouter()

# resolve /path/to/repo/evaluation/results
EVAL_RESULTS = Path(__file__).resolve().parent.parent.parent / "evaluation" / "results"


def _load(name: str):
    p = EVAL_RESULTS / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:
        return {"error": f"{name}: {e}"}


@router.get("/api/research")
def research():
    metrics = _load("metrics.json")
    ablation = _load("ablation.json")
    if metrics is None:
        return {
            "status": "not_ready",
            "detail": (
                "No evaluation results found. Run "
                "`python evaluation/scripts/run_evaluation.py` and "
                "`python evaluation/scripts/calculate_metrics.py` first."
            ),
            "results_dir": str(EVAL_RESULTS),
        }
    return {
        "status": "ok",
        "metrics": metrics,
        "ablation": ablation,
    }
