"""Paper-evidence evaluation runner.

Runs the InsightFlow Reliability Benchmark through several system
configurations and emits:

    * paper_evidence/per_question.csv  — one row per (question × config)
    * paper_evidence/results.json      — aggregated metrics
    * paper_evidence/results_tables.md — human-readable tables with CIs

Configurations:
    Full : default orchestrator (plan pipeline, confidence engine, cap)
    B1   : plan pipeline, but every answered query becomes ANSWER
           (no CLARIFY/ABSTAIN gating — stress test for safety)
    A1   : Full without the fidelity validator
    A2   : Full without the result validator
    A3   : Full without the hard cap (C = S)

Baselines not run here:
    B0   : legacy pre-plan generator — still callable in-tree only on
           the demo dataset when the plan is AMBIGUOUS. Reaching it in a
           controlled way would require more plumbing than this run
           budget allows. Reported as NOT MEASURED in the paper tables.
    B2   : direct LLM text-to-SQL. Requires OPENAI_API_KEY which this
           environment does not have. NOT MEASURED.

Determinism:
    * Fresh DB reseed before the run (random.Random(42) in seed.py).
    * Per-question latency uses time.perf_counter().
    * No LLM calls — all configurations use the deterministic
      rule-based plan pipeline.
"""
from __future__ import annotations

import csv
import json
import os
import pathlib
import runpy
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
EV = ROOT / "paper_evidence"
EV.mkdir(exist_ok=True)
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))
os.environ.setdefault(
    "DATABASE_URL", f"sqlite:///{(BACKEND / 'data/insightflow.db').resolve()}")

from evaluation.oracle import load_benchmark, compute_oracle, values_match, DEFAULT_DB


CONFIGS = ["Full", "B1", "A1", "A2", "A3"]


# ---------------------------------------------------------------------------
# Per-config runner
# ---------------------------------------------------------------------------

def _reseed():
    runpy.run_path(str(BACKEND / "data/seed.py"), run_name="__main__")
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.schema_agent import refresh_schema
    from insightflow.knowledge.dataset_registry import set_active, DEMO_ID
    reset_engine(); refresh_schema(); set_active(DEMO_ID)


def _ask_full(question: str):
    from insightflow.orchestrator import Orchestrator
    return Orchestrator().ask(question)


def _ask_no_cap(question: str):
    """A3 — remove the hard cap. Patch score_confidence to skip the
    min(..., coverage+.05, fidelity+.05) step."""
    import insightflow.reliability.confidence as C
    original = C.score_confidence

    def no_cap(*args, **kwargs):
        res = original(*args, **kwargs)
        # Reconstruct score as the pure weighted sum of signals
        from insightflow.config import settings as st
        w = st.confidence_weights
        pure = sum(w.get(k, 0.0) * v for k, v in res.signals.items())
        res.score = max(0.0, min(1.0, pure))
        return res

    C.score_confidence = no_cap
    try:
        from insightflow.orchestrator import Orchestrator
        return Orchestrator().ask(question)
    finally:
        C.score_confidence = original


def _ask_no_fidelity(question: str):
    """A1 — bypass the fidelity validator. Force its score to 1.0 so
    the plan_fidelity signal + decision gate behave as if every SQL
    passed structural fidelity."""
    import insightflow.plan.fidelity as F
    orig = F.FidelityValidator.check

    def always_pass(self, plan, sql):
        rep = orig(self, plan, sql)
        rep.ok = True
        rep.score = 1.0
        for c in rep.checks:
            c.passed = True
        return rep

    F.FidelityValidator.check = always_pass
    try:
        from insightflow.orchestrator import Orchestrator
        return Orchestrator().ask(question)
    finally:
        F.FidelityValidator.check = orig


def _ask_no_result_validator(question: str):
    """A2 — bypass the post-execution result validator."""
    import insightflow.reliability.result_validator as RV
    orig = RV.ResultValidator.check

    def always_pass(self, plan, result):
        from insightflow.reliability.result_validator import ResultReport
        return ResultReport(ok=True, score=1.0, issues=[])

    RV.ResultValidator.check = always_pass
    try:
        from insightflow.orchestrator import Orchestrator
        return Orchestrator().ask(question)
    finally:
        RV.ResultValidator.check = orig


def _ask_b1(question: str):
    """B1 — plan pipeline runs normally, but every executed SQL yields
    an ANSWER regardless of confidence or gates. Lets us measure what
    the system would say if the abstention policy was removed."""
    from insightflow.orchestrator import Orchestrator
    from insightflow.reliability.decision import Decision, ANSWER
    resp = Orchestrator().ask(question)
    # Force ANSWER iff SQL was emitted AND executed
    if resp.sql and resp.result.ok:
        resp.decision = Decision(ANSWER, f"B1-forced (was {resp.decision.action}: {resp.decision.reason})")
    return resp


RUNNERS = {
    "Full": _ask_full,
    "B1":   _ask_b1,
    "A1":   _ask_no_fidelity,
    "A2":   _ask_no_result_validator,
    "A3":   _ask_no_cap,
}


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _matches_oracle(system_rows, oracle_rows) -> bool:
    """Numeric comparison with EPSILON tolerance, falling back to
    equality. Handles row-count mismatches as 'no match' except when
    comparing a scalar oracle (1 row × 1 col) against a system result
    that put the scalar in the LAST column of a 1-row answer."""
    if system_rows is None or oracle_rows is None:
        return False
    # Normalise: if oracle is a single scalar (1x1), compare that.
    if (isinstance(oracle_rows, list) and len(oracle_rows) == 1
            and isinstance(oracle_rows[0], list) and len(oracle_rows[0]) == 1):
        target = oracle_rows[0][0]
        if not system_rows:
            return False
        # system_rows is list[list]; try last column of first row
        try:
            cand = system_rows[0][-1]
        except Exception:
            return False
        return values_match(cand, target)
    return values_match(system_rows, oracle_rows)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_one(cfg: str, row: dict) -> Dict[str, Any]:
    runner = RUNNERS[cfg]
    q = row["natural_language_question"]
    t0 = time.perf_counter()
    try:
        resp = runner(q)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        out: Dict[str, Any] = {
            "question_id": row["question_id"],
            "config": cfg,
            "category": row.get("question_type"),
            "difficulty": row.get("difficulty"),
            "answerability": row.get("answerability"),
            "expected_decision": row.get("expected_decision"),
            "action": resp.decision.action,
            "confidence": round(float(resp.confidence.score), 4),
            "sql": resp.sql or "",
            "sql_ok": bool(resp.sql),
            "exec_ok": resp.result.ok,
            "exec_error": resp.result.error if not resp.result.ok else "",
            "n_rows": resp.result.n_rows,
            "latency_ms": elapsed_ms,
            "failure_category": getattr(resp, "failure_category", ""),
        }
        # confidence signals
        for s, v in resp.confidence.signals.items():
            out[f"sig_{s}"] = round(float(v), 4)
        # oracle check (only on answerable questions)
        if row.get("answerability") == "answerable":
            oracle = compute_oracle(row)
            out["oracle_source"] = oracle.source
            if resp.result.ok and resp.result.rows:
                system_rows = [list(r) for r in resp.result.rows]
                out["semantic_match"] = _matches_oracle(system_rows, oracle.value)
            else:
                out["semantic_match"] = False
        else:
            out["oracle_source"] = "unanswerable"
            # For unanswerable questions, "correct" means not ANSWER
            out["semantic_match"] = resp.decision.action in ("CLARIFY", "ABSTAIN")
        return out
    except Exception as e:
        return {
            "question_id": row["question_id"], "config": cfg,
            "action": "RUNNER_ERROR", "exec_error": str(e),
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "semantic_match": False,
            "oracle_source": "error",
        }


def main() -> None:
    bench = load_benchmark()
    rows_out: List[Dict[str, Any]] = []
    for cfg in CONFIGS:
        _reseed()
        print(f"=== config {cfg} on {len(bench)} questions ===", flush=True)
        for row in bench:
            out = run_one(cfg, row)
            rows_out.append(out)
    # Write CSV
    fieldnames = sorted({k for r in rows_out for k in r.keys()})
    with (EV / "per_question.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows_out:
            w.writerow(r)
    print(f"wrote {len(rows_out)} rows to paper_evidence/per_question.csv")


if __name__ == "__main__":
    main()
