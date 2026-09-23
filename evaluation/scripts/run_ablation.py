"""Ablate the reliability layer without touching the main system.

We swap `settings.confidence_weights` for each of three configurations,
re-run the benchmark against the real orchestrator, and compare:

  A "SQL-only"        — 100 % weight on sql_validity + schema_match
  B "SQL + KPI"       — SQL + schema + kpi_match + context_consistency
  C "Full InsightFlow"— the shipped seven-signal weighting (default)

Thresholds and every other pipeline stage are unchanged. The confidence
scores under A/B are re-projected onto the same signals the shipped
engine already emits, so nothing else about behaviour is faked.

Usage:
    python evaluation/scripts/run_ablation.py
"""
from __future__ import annotations

import copy
import csv
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
EVAL_DIR = HERE.parent
BACKEND = EVAL_DIR.parent / "backend"
RESULTS_DIR = EVAL_DIR / "results"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(HERE))  # sibling scripts

from insightflow.config import settings, DEFAULT_WEIGHTS  # noqa: E402
from insightflow.execution.executor import reset_engine  # noqa: E402
from insightflow.knowledge.schema_agent import refresh_schema  # noqa: E402
from insightflow.orchestrator import Orchestrator  # noqa: E402

from run_evaluation import evaluate, _load_benchmark  # noqa: E402
from calculate_metrics import (  # noqa: E402
    business_metrics, decision_metrics, reliability_metrics,
    calibration, sql_text_metrics,
)


CONFIGS: dict[str, dict[str, float]] = {
    "A_sql_only": {
        "sql_validity":        0.60,
        "schema_match":        0.40,
        "kpi_match":           0.00,
        "context_consistency": 0.00,
        "data_completeness":   0.00,
        "evidence_strength":   0.00,
        "result_consistency":  0.00,
    },
    "B_sql_kpi": {
        "sql_validity":        0.30,
        "schema_match":        0.20,
        "kpi_match":           0.30,
        "context_consistency": 0.20,
        "data_completeness":   0.00,
        "evidence_strength":   0.00,
        "result_consistency":  0.00,
    },
    "C_full": copy.deepcopy(DEFAULT_WEIGHTS),
}


def _row_dict(rows):
    """Convert dataclass rows into plain dicts, matching what calculate_metrics
    expects (it accepts JSON dicts)."""
    from dataclasses import asdict
    return [asdict(r) for r in rows]


def _summarise(rows_json: list[dict]) -> dict:
    return {
        "text_to_sql": sql_text_metrics(rows_json),
        "business": business_metrics(rows_json),
        "reliability": reliability_metrics(rows_json),
        "decision": decision_metrics(rows_json),
        "calibration": {
            "ece": calibration(rows_json)["ece"],
            "brier": calibration(rows_json)["brier"],
        },
    }


def main() -> int:
    reset_engine()
    refresh_schema()
    benchmark = _load_benchmark()

    original = dict(settings.confidence_weights)
    summaries: dict[str, dict] = {}
    per_run_rows: dict[str, list[dict]] = {}

    for cfg_name, weights in CONFIGS.items():
        # Set weights globally; orchestrator reads settings on each ask.
        settings.confidence_weights = dict(weights)
        orch = Orchestrator()
        rows = evaluate(orch, benchmark)
        rows_json = _row_dict(rows)
        per_run_rows[cfg_name] = rows_json
        summaries[cfg_name] = _summarise(rows_json)
        print(f"\n=== {cfg_name} ===")
        for k, v in summaries[cfg_name].items():
            print(f"  {k}: {v}")

    # restore weights so anything running after this script sees defaults
    settings.confidence_weights = original

    out = {"configs": CONFIGS, "results": summaries}
    (RESULTS_DIR / "ablation.json").write_text(json.dumps(out, indent=2))

    # ablation.csv — one row per config with the headline metrics
    headline_keys = [
        ("execution_accuracy", ("text_to_sql", "execution_accuracy")),
        ("sql_validity_rate", ("text_to_sql", "sql_validity_rate")),
        ("business_answer_correctness", ("business", "answer_correctness")),
        ("evidence_support_rate", ("business", "evidence_support_rate")),
        ("avg_confidence", ("reliability", "avg_confidence")),
        ("high_confidence_error_rate", ("reliability", "high_confidence_error_rate")),
        ("decision_correctness", ("decision", "decision_correctness")),
        ("unsafe_answer_rate", ("decision", "unsafe_answer_rate")),
        ("ece", ("calibration", "ece")),
        ("brier", ("calibration", "brier")),
    ]
    csv_path = RESULTS_DIR / "ablation.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric"] + list(CONFIGS.keys()))
        for name, path in headline_keys:
            row = [name]
            for cfg in CONFIGS:
                v = summaries[cfg]
                for step in path:
                    v = v[step] if v is not None and step in v else None
                    if v is None:
                        break
                row.append("" if v is None else v)
            w.writerow(row)
    print(f"\nWrote {csv_path} and ablation.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
