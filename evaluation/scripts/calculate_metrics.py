"""Compute the metrics defined in evaluation/reports/alignment.md
from the raw run outputs. No metric is computed if the underlying
ground-truth isn't available for it — it's marked `null`.

Usage:
    python evaluation/scripts/calculate_metrics.py
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
EVAL_DIR = HERE.parent
RESULTS_DIR = EVAL_DIR / "results"


BINS = [(0.00, 0.40), (0.40, 0.70), (0.70, 1.01)]   # last upper bound inclusive
HIGH_THRESHOLD = 0.70


def _load() -> list[dict]:
    return json.load((RESULTS_DIR / "results.json").open())


def _tribool(v: Any) -> Any:
    """Reinterpret CSV/JSON "" or None as None for optional booleans."""
    if v in ("", None):
        return None
    if isinstance(v, str):
        return v.lower() == "true"
    return bool(v)


def _rate(k: int, n: int) -> float | None:
    return (k / n) if n else None


def _mean(xs: list[float]) -> float | None:
    return (sum(xs) / len(xs)) if xs else None


def calibration(rows: list[dict]) -> dict:
    """Confidence binning + ECE + Brier on rows that have a business truth."""
    scored = [r for r in rows if _tribool(r["business_correct"]) is not None]

    bins_out = []
    total = len(scored)
    ece = 0.0
    for lo, hi in BINS:
        bucket = [r for r in scored if lo <= r["overall_confidence"] < hi]
        n = len(bucket)
        correct = sum(1 for r in bucket if _tribool(r["business_correct"]))
        acc = _rate(correct, n)
        avg_conf = _mean([r["overall_confidence"] for r in bucket])
        bins_out.append({
            "range": [round(lo, 2), round(hi, 2)],
            "n": n,
            "correct": correct,
            "incorrect": n - correct,
            "accuracy": acc,
            "avg_confidence": avg_conf,
        })
        if acc is not None and avg_conf is not None:
            ece += (n / total) * abs(avg_conf - acc)

    # Brier score
    brier = None
    if scored:
        brier = sum((r["overall_confidence"] - (1.0 if _tribool(r["business_correct"]) else 0.0)) ** 2
                    for r in scored) / len(scored)

    return {"bins": bins_out, "ece": ece if scored else None, "brier": brier,
            "n_scored": total}


def sql_text_metrics(rows: list[dict]) -> dict:
    """Text-to-SQL metrics on items that have gold SQL (answerable + diagnostic)."""
    graded = [r for r in rows if _tribool(r["execution_accuracy"]) is not None]
    n = len(graded)
    if n == 0:
        return {"n": 0, "execution_accuracy": None, "exact_match": None,
                "sql_validity_rate": None, "schema_matching_accuracy": None}

    ex = sum(1 for r in graded if _tribool(r["execution_accuracy"])) / n
    em_scored = [r for r in graded if _tribool(r["exact_match"]) is not None]
    em = (sum(1 for r in em_scored if _tribool(r["exact_match"])) / len(em_scored)) if em_scored else None
    validity = _mean([r["sql_validity"] for r in graded])
    schema = _mean([r["schema_match"] for r in graded])

    return {
        "n": n,
        "execution_accuracy": ex,
        "exact_match": em,
        "sql_validity_rate": validity,
        "schema_matching_accuracy": schema,
    }


def business_metrics(rows: list[dict]) -> dict:
    graded = [r for r in rows if _tribool(r["business_correct"]) is not None]
    n = len(graded)
    correct = sum(1 for r in graded if _tribool(r["business_correct"]))
    kpi = _mean([r["kpi_match"] for r in graded])
    evi = _mean([r["evidence_strength"] for r in graded])
    rc  = _mean([r["result_consistency"] for r in graded])
    return {
        "n": n,
        "answer_correctness": _rate(correct, n),
        "kpi_matching_accuracy": kpi,
        "evidence_support_rate": evi,
        "result_consistency": rc,
    }


def reliability_metrics(rows: list[dict]) -> dict:
    scored = [r for r in rows if _tribool(r["business_correct"]) is not None]
    avg = _mean([r["overall_confidence"] for r in rows])
    avg_correct = _mean([r["overall_confidence"] for r in scored
                         if _tribool(r["business_correct"])])
    avg_wrong = _mean([r["overall_confidence"] for r in scored
                       if _tribool(r["business_correct"]) is False])
    high_wrong = [r for r in scored
                  if _tribool(r["business_correct"]) is False
                  and r["overall_confidence"] >= HIGH_THRESHOLD]
    high_conf = [r for r in scored if r["overall_confidence"] >= HIGH_THRESHOLD]
    high_error_rate = _rate(len(high_wrong), len(high_conf))
    return {
        "avg_confidence": avg,
        "avg_confidence_correct": avg_correct,
        "avg_confidence_incorrect": avg_wrong,
        "high_confidence_error_rate": high_error_rate,
        "n_high_confidence": len(high_conf),
    }


def decision_metrics(rows: list[dict]) -> dict:
    n = len(rows)
    counts = {"ANSWER": 0, "WARN": 0, "CLARIFY": 0, "ABSTAIN": 0}
    for r in rows:
        counts[r["decision"]] = counts.get(r["decision"], 0) + 1

    matches = sum(1 for r in rows if r["decision_match"])
    unsafe = sum(1 for r in rows if r["unsafe_answer"])

    # ANSWER precision on items with a business truth: of the answered ones,
    # what fraction are business_correct?
    answered = [r for r in rows if r["decision"] in ("ANSWER", "WARN")
                and _tribool(r["business_correct"]) is not None]
    answer_prec = _rate(
        sum(1 for r in answered if _tribool(r["business_correct"])),
        len(answered),
    )

    return {
        "distribution": counts,
        "distribution_rate": {k: (v / n if n else 0.0) for k, v in counts.items()},
        "decision_correctness": _rate(matches, n),
        "answer_precision": answer_prec,
        "unsafe_answer_count": unsafe,
        "unsafe_answer_rate": _rate(unsafe, n),
        "n_answered_with_truth": len(answered),
    }


def per_category(rows: list[dict]) -> dict:
    out = {}
    for key in ("answerability", "difficulty"):
        by = {}
        for r in rows:
            k = r[key]
            b = by.setdefault(k, {"n": 0, "correct_dec": 0,
                                  "ex_true": 0, "ex_total": 0,
                                  "unsafe": 0, "avg_conf_sum": 0.0})
            b["n"] += 1
            b["avg_conf_sum"] += r["overall_confidence"]
            if r["decision_match"]:
                b["correct_dec"] += 1
            ex = _tribool(r["execution_accuracy"])
            if ex is not None:
                b["ex_total"] += 1
                if ex:
                    b["ex_true"] += 1
            if r["unsafe_answer"]:
                b["unsafe"] += 1
        for k, b in by.items():
            b["decision_correctness"] = b["correct_dec"] / b["n"]
            b["execution_accuracy"] = (b["ex_true"] / b["ex_total"]) if b["ex_total"] else None
            b["avg_confidence"] = b["avg_conf_sum"] / b["n"]
            b["unsafe_answer_rate"] = b["unsafe"] / b["n"]
            del b["avg_conf_sum"]
        out[key] = by
    return out


def main() -> int:
    rows = _load()

    metrics = {
        "n_questions": len(rows),
        "text_to_sql": sql_text_metrics(rows),
        "business": business_metrics(rows),
        "reliability": reliability_metrics(rows),
        "decision": decision_metrics(rows),
        "calibration": calibration(rows),
        "per_category": per_category(rows),
    }

    out_json = RESULTS_DIR / "metrics.json"
    out_json.write_text(json.dumps(metrics, indent=2))

    # summary.csv — headline scalars
    summary = {
        "n_questions": len(rows),
        "execution_accuracy": metrics["text_to_sql"]["execution_accuracy"],
        "exact_match": metrics["text_to_sql"]["exact_match"],
        "sql_validity_rate": metrics["text_to_sql"]["sql_validity_rate"],
        "schema_matching_accuracy": metrics["text_to_sql"]["schema_matching_accuracy"],
        "business_answer_correctness": metrics["business"]["answer_correctness"],
        "kpi_matching_accuracy": metrics["business"]["kpi_matching_accuracy"],
        "evidence_support_rate": metrics["business"]["evidence_support_rate"],
        "avg_confidence": metrics["reliability"]["avg_confidence"],
        "avg_confidence_correct": metrics["reliability"]["avg_confidence_correct"],
        "avg_confidence_incorrect": metrics["reliability"]["avg_confidence_incorrect"],
        "high_confidence_error_rate": metrics["reliability"]["high_confidence_error_rate"],
        "decision_correctness": metrics["decision"]["decision_correctness"],
        "answer_precision": metrics["decision"]["answer_precision"],
        "unsafe_answer_rate": metrics["decision"]["unsafe_answer_rate"],
        "ece": metrics["calibration"]["ece"],
        "brier": metrics["calibration"]["brier"],
    }
    csv_path = RESULTS_DIR / "summary.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for k, v in summary.items():
            w.writerow([k, "" if v is None else v])

    # Human-readable print
    print(f"n_questions:                    {metrics['n_questions']}")
    print(f"execution_accuracy (SQL truth): {summary['execution_accuracy']}")
    print(f"exact_match:                    {summary['exact_match']}")
    print(f"sql_validity_rate:              {summary['sql_validity_rate']}")
    print(f"schema_matching_accuracy:       {summary['schema_matching_accuracy']}")
    print(f"business_answer_correctness:    {summary['business_answer_correctness']}")
    print(f"kpi_matching_accuracy:          {summary['kpi_matching_accuracy']}")
    print(f"evidence_support_rate:          {summary['evidence_support_rate']}")
    print(f"avg_confidence:                 {summary['avg_confidence']:.3f}")
    print(f"avg_conf (correct):             {summary['avg_confidence_correct']}")
    print(f"avg_conf (incorrect):           {summary['avg_confidence_incorrect']}")
    print(f"high_conf_error_rate:           {summary['high_confidence_error_rate']}")
    print(f"decision_correctness:           {summary['decision_correctness']}")
    print(f"answer_precision:               {summary['answer_precision']}")
    print(f"unsafe_answer_rate:             {summary['unsafe_answer_rate']}")
    print(f"ECE:                            {summary['ece']:.4f}")
    print(f"Brier:                          {summary['brier']:.4f}")
    print(f"\nWrote {out_json} and {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
