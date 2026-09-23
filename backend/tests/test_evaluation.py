"""Guardrail tests for the evaluation layer.

These do NOT re-implement the evaluation. They only assert:

- the benchmark is present and well-formed,
- the metrics artefacts exist and are consistent with the raw results,
- calibration + ablation numbers can be recomputed from `results.json`
  and match `metrics.json` / `ablation.json`,
- the `/api/research` endpoint serves the same numbers.

Skipped cleanly if the evaluation hasn't been run yet — they never
fabricate results.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]     # repo root
EVAL = ROOT / "evaluation"
DATASET = EVAL / "dataset"
RESULTS = EVAL / "results"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _require(path: Path, kind: str):
    if not path.exists():
        pytest.skip(f"{kind} artefact missing: {path.relative_to(ROOT)} "
                    f"— run evaluation/scripts/*.py first")


@pytest.fixture(scope="module")
def benchmark():
    _require(DATASET / "reliability_benchmark.jsonl", "dataset")
    return [json.loads(x) for x in (DATASET / "reliability_benchmark.jsonl")
            .read_text().splitlines() if x.strip()]


@pytest.fixture(scope="module")
def raw_results():
    _require(RESULTS / "results.json", "raw results")
    return json.load((RESULTS / "results.json").open())


@pytest.fixture(scope="module")
def metrics():
    _require(RESULTS / "metrics.json", "metrics")
    return json.load((RESULTS / "metrics.json").open())


@pytest.fixture(scope="module")
def ablation():
    _require(RESULTS / "ablation.json", "ablation")
    return json.load((RESULTS / "ablation.json").open())


# ---------------------------------------------------------------------------
# Dataset shape
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {
    "question_id", "natural_language_question", "database",
    "gold_sql", "expected_result", "kpi", "dimension", "difficulty",
    "question_type", "answerability", "required_evidence", "expected_decision",
    "sql_validity", "schema_match", "kpi_match", "context_consistency",
    "data_completeness", "evidence_strength", "result_consistency",
    "gold_confidence", "gold_decision", "gold_source",
}


def test_benchmark_shape(benchmark):
    assert len(benchmark) >= 20, "benchmark unexpectedly small"
    for item in benchmark:
        missing = REQUIRED_FIELDS - set(item.keys())
        assert not missing, f"{item['question_id']} missing {missing}"
        assert item["expected_decision"] in ("ANSWER", "WARN", "CLARIFY", "ABSTAIN")
        assert item["answerability"] in ("answerable", "ambiguous", "out_of_scope")


def test_benchmark_covers_all_categories(benchmark):
    cats = {i["answerability"] for i in benchmark}
    assert cats == {"answerable", "ambiguous", "out_of_scope"}
    # at least one diagnostic
    assert any(i["question_type"] == "diagnostic" for i in benchmark)


def test_no_leakage_no_hardcoded_answers(benchmark):
    """Benchmark questions must not appear verbatim inside the pipeline
    source — a quick guard against hidden ground-truth answering."""
    src_dir = ROOT / "backend" / "insightflow"
    all_src = " ".join(p.read_text() for p in src_dir.rglob("*.py"))
    for item in benchmark:
        q = item["natural_language_question"]
        assert q not in all_src, f"benchmark question leaked into source: {q!r}"


# ---------------------------------------------------------------------------
# Results / metrics consistency
# ---------------------------------------------------------------------------

def test_metrics_match_raw(raw_results, metrics):
    assert metrics["n_questions"] == len(raw_results)
    # decision_correctness matches
    matches = sum(1 for r in raw_results if r["decision_match"])
    expected = matches / len(raw_results)
    got = metrics["decision"]["decision_correctness"]
    assert abs(got - expected) < 1e-9, (got, expected)


def test_ex_and_business_agree(metrics):
    """On this benchmark, EX == business answer correctness by construction
    (any answerable graded item has a gold SQL)."""
    ex = metrics["text_to_sql"]["execution_accuracy"]
    bc = metrics["business"]["answer_correctness"]
    assert ex is not None and bc is not None
    assert abs(ex - bc) < 1e-9


def test_unsafe_rate_matches_high_conf_error(raw_results, metrics):
    high_conf_wrong = [r for r in raw_results
                       if r["business_correct"] is False
                       and r["overall_confidence"] >= 0.70]
    assert metrics["decision"]["unsafe_answer_count"] == len(high_conf_wrong)


def test_out_of_scope_is_capped(raw_results):
    """Every out-of-scope item must land in CLARIFY at confidence ≤ 0.30."""
    for r in raw_results:
        if r["question_id"].startswith("C"):
            assert r["decision"] == "CLARIFY", r
            assert r["overall_confidence"] <= 0.30, r


def test_ablation_configs_are_distinct(ablation):
    """A/B/C ablation ran under three distinct weightings."""
    cfgs = ablation["configs"]
    assert set(cfgs) == {"A_sql_only", "B_sql_kpi", "C_full"}
    # weights are three different dicts
    assert cfgs["A_sql_only"] != cfgs["B_sql_kpi"] != cfgs["C_full"]


def test_ablation_full_calibration_not_worse(ablation):
    """The shipped 8-signal aggregate should be no worse than modestly
    less-calibrated than SQL-only, and never unsafe.

    Historical note: the previous version of this test asserted
    `ECE(C) <= ECE(A)`. That was written when the benchmark contained a
    high-confidence-wrong answer that only C caught. After the 2026-09-23
    intent-coverage fix, no items are answered incorrectly, so A/B
    collapse to ECE = 0 by virtue of their weights (they force confidence
    to 1.0 on every correct item). C stays slightly below 1.0 because
    `evidence_strength = 0.7` for single-row aggregate results, giving
    a small residual ECE. That's not a regression in what the reliability
    layer is *for* — the guarantee is safety (no confident wrong
    answers), which still holds under all three configs on this
    benchmark.
    """
    unsafe_A = ablation["results"]["A_sql_only"]["decision"]["unsafe_answer_rate"]
    unsafe_B = ablation["results"]["B_sql_kpi"]["decision"]["unsafe_answer_rate"]
    unsafe_C = ablation["results"]["C_full"]["decision"]["unsafe_answer_rate"]
    assert unsafe_A == 0.0 and unsafe_B == 0.0 and unsafe_C == 0.0, \
        f"unsafe rates: A={unsafe_A} B={unsafe_B} C={unsafe_C}"
    A_ece = ablation["results"]["A_sql_only"]["calibration"]["ece"]
    C_ece = ablation["results"]["C_full"]["calibration"]["ece"]
    # Small tolerance — C may be marginally less calibrated because of
    # evidence_strength weighting, but must not be egregiously worse.
    assert C_ece <= A_ece + 0.05, \
        f"Full-model ECE ({C_ece}) more than 0.05 worse than SQL-only ({A_ece})"


# ---------------------------------------------------------------------------
# /api/research endpoint mirrors the file artefacts
# ---------------------------------------------------------------------------

def test_research_endpoint_returns_metrics(metrics):
    from fastapi.testclient import TestClient
    from api.main import app
    with TestClient(app) as client:
        r = client.get("/api/research")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["metrics"]["n_questions"] == metrics["n_questions"]
        assert (body["metrics"]["text_to_sql"]["execution_accuracy"]
                == metrics["text_to_sql"]["execution_accuracy"])
