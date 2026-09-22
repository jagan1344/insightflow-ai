"""Run the InsightFlow orchestrator against the Reliability Benchmark.

Every field written to results/ comes from a real call to
`insightflow.orchestrator.Orchestrator.ask` — no synthetic or
hand-written outputs are emitted.

Usage:
    python evaluation/scripts/run_evaluation.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


HERE = Path(__file__).resolve().parent
EVAL_DIR = HERE.parent
BACKEND = EVAL_DIR.parent / "backend"
DATASET_DIR = EVAL_DIR / "dataset"
RESULTS_DIR = EVAL_DIR / "results"

sys.path.insert(0, str(BACKEND))

from sqlalchemy import text  # noqa: E402
from insightflow.execution.executor import get_engine, reset_engine  # noqa: E402
from insightflow.knowledge.schema_agent import refresh_schema  # noqa: E402
from insightflow.orchestrator import Orchestrator  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _order_sensitive(sql: str) -> bool:
    """Match BIRD's EX rule: only order-sensitive when SQL has ORDER BY.
    (LIMIT is a coarse proxy — when a LIMIT is present without ORDER BY,
    treat as order-sensitive too for safety.)"""
    s = sql.lower()
    return "order by" in s or "limit" in s


def _normalise_row(r: Any) -> tuple:
    out = []
    for v in r:
        if isinstance(v, float):
            out.append(round(v, 4))
        else:
            out.append(v)
    return tuple(out)


def _same_result_set(pred_rows: list, gold_rows: list, order_sensitive: bool) -> bool:
    """BIRD-style multiset equality (or ordered equality if order matters)."""
    if pred_rows is None or gold_rows is None:
        return pred_rows == gold_rows
    P = [_normalise_row(r) for r in pred_rows]
    G = [_normalise_row(r) for r in gold_rows]
    if order_sensitive:
        return P == G
    # multiset compare
    return sorted(P) == sorted(G)


def _run_sql_direct(sql: str) -> Optional[list]:
    """Run predicted SQL on the DB to fetch its result set (for EX)."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            return [tuple(r) for r in conn.execute(text(sql)).fetchall()]
    except Exception:
        return None


def _decision_matches(pred: str, gold: str) -> bool:
    """Compare policy actions. WARN counts as a soft match for ANSWER
    (it's the same 'we answered' branch); an explicit gold WARN would only
    match WARN. Otherwise strict equality."""
    if pred == gold:
        return True
    if gold == "ANSWER" and pred == "WARN":
        return True
    return False


# ---------------------------------------------------------------------------

@dataclass
class RowOut:
    question_id: str
    question: str
    difficulty: str
    answerability: str
    expected_decision: str
    generated_sql: str
    sql_execution_status: str
    exact_match: Optional[bool]
    execution_accuracy: Optional[bool]
    sql_validity: float
    schema_match: float
    kpi_match: float
    context_consistency: float
    data_completeness: float
    evidence_strength: float
    result_consistency: float
    overall_confidence: float
    decision: str
    decision_match: bool
    generated_answer: str
    expected_answer_repr: str
    business_correct: Optional[bool]
    unsafe_answer: bool          # answered w/ high confidence but wrong
    notes: str = ""


def _load_benchmark() -> list[dict]:
    path = DATASET_DIR / "reliability_benchmark.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _exact_match(pred_sql: str, gold_sql: Optional[str]) -> Optional[bool]:
    if gold_sql is None:
        return None
    if not pred_sql:
        return False
    norm = lambda s: re.sub(r"\s+", " ", s.strip().rstrip(";").lower())
    return norm(pred_sql) == norm(gold_sql)


def _business_correct(item: dict, sql: str, pred_answer: str) -> Optional[bool]:
    """For answerable/diagnostic items where gold_sql exists, business
    correctness = EX. For ambiguous/OOS items, business correctness is not
    defined (the correct behaviour is decision=CLARIFY, evaluated separately)."""
    gold_sql = item.get("gold_sql")
    if gold_sql is None:
        return None
    if not sql:
        return False
    pred_rows = _run_sql_direct(sql)
    if pred_rows is None:
        return False
    gold_rows = _run_sql_direct(gold_sql)
    if gold_rows is None:
        # Gold SQL failed to execute (should not happen for our benchmark)
        return False
    return _same_result_set(pred_rows, gold_rows, _order_sensitive(gold_sql))


def evaluate(orchestrator: Orchestrator, benchmark: list[dict],
             high_threshold: float = 0.70) -> list[RowOut]:
    rows: list[RowOut] = []
    for item in benchmark:
        resp = orchestrator.ask(item["natural_language_question"])
        sql = resp.sql or ""
        gen_ans = resp.explanation or resp.analysis.summary or ""
        gold_sql = item.get("gold_sql")

        ex = None
        bc = None
        if item["answerability"] == "answerable":
            ex = _business_correct(item, sql, gen_ans)
            bc = ex
        elif item["question_type"] == "diagnostic":
            ex = _business_correct(item, sql, gen_ans)
            bc = ex

        em = _exact_match(sql, gold_sql)

        dec_match = _decision_matches(resp.decision.action, item["expected_decision"])
        # unsafe = confidently answered but wrong on the business answer
        answered = resp.decision.action in ("ANSWER", "WARN")
        unsafe = bool(answered and resp.confidence.score >= high_threshold and bc is False)

        exp_repr = json.dumps(item.get("expected_result"), ensure_ascii=False) \
            if item.get("expected_result") is not None else ""

        rows.append(RowOut(
            question_id=item["question_id"],
            question=item["natural_language_question"],
            difficulty=item["difficulty"],
            answerability=item["answerability"],
            expected_decision=item["expected_decision"],
            generated_sql=sql,
            sql_execution_status=("ok" if resp.result.ok else (resp.result.error or "no_sql")),
            exact_match=em,
            execution_accuracy=ex,
            sql_validity=resp.confidence.signals.get("sql_validity", 0.0),
            schema_match=resp.confidence.signals.get("schema_match", 0.0),
            kpi_match=resp.confidence.signals.get("kpi_match", 0.0),
            context_consistency=resp.confidence.signals.get("context_consistency", 0.0),
            data_completeness=resp.confidence.signals.get("data_completeness", 0.0),
            evidence_strength=resp.confidence.signals.get("evidence_strength", 0.0),
            result_consistency=resp.confidence.signals.get("result_consistency", 0.0),
            overall_confidence=resp.confidence.score,
            decision=resp.decision.action,
            decision_match=dec_match,
            generated_answer=gen_ans,
            expected_answer_repr=exp_repr,
            business_correct=bc,
            unsafe_answer=unsafe,
        ))
    return rows


def write_outputs(rows: list[RowOut], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # raw_results.csv — one row per question, full detail
    csv_path = out_dir / "raw_results.csv"
    fieldnames = list(asdict(rows[0]).keys())
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            row = asdict(r)
            # normalise Optional[bool] → "" for CSV clarity
            for k, v in list(row.items()):
                if v is None:
                    row[k] = ""
                elif isinstance(v, bool):
                    row[k] = "true" if v else "false"
            w.writerow(row)

    # results.json — same, JSON-friendly
    json_path = out_dir / "results.json"
    json_path.write_text(json.dumps([asdict(r) for r in rows], indent=2))

    print(f"Wrote {len(rows)} rows to")
    print(f"  {csv_path}")
    print(f"  {json_path}")


# ---------------------------------------------------------------------------

def main() -> int:
    reset_engine()
    refresh_schema()
    orch = Orchestrator()
    benchmark = _load_benchmark()
    print(f"Loaded {len(benchmark)} benchmark items")
    print(f"Running InsightFlow orchestrator (offline, LLM available={orch.llm.available})...\n")
    rows = evaluate(orch, benchmark)
    write_outputs(rows, RESULTS_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
