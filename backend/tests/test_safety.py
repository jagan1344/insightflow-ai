"""Broad safety regression: for a wide range of natural-language questions,
the system must either answer correctly OR clarify — never confidently
answer with SQL that doesn't match the intent.

This is the guarantee the user asked for: "not only these questions —
all questions asked by user should be able to answer, if not don't give
wrong answer." No system can *answer* every question; what we guarantee
is that we never confidently answer a *different* question.

Each case declares what its acceptable outcomes are:

  "ANSWER"   → decision must be ANSWER (or WARN) and the specified
               keywords must all appear in the generated SQL.
  "CLARIFY"  → decision must be CLARIFY. We never guess.
  "SAFE"     → any decision is fine as long as it isn't "ANSWER at
               high confidence with mismatched SQL". Practically: if
               decision is ANSWER, `intent_coverage` must be ≥ 0.9.

Anything failing this test is by definition an unsafe answer.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module", autouse=True)
def _seed_demo():
    """Fresh demo DB so every case runs against the known-good schema."""
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.schema_agent import refresh_schema
    runpy.run_path(str(ROOT / "data" / "seed.py"), run_name="__main__")
    reset_engine(); refresh_schema()
    yield
    runpy.run_path(str(ROOT / "data" / "seed.py"), run_name="__main__")
    reset_engine(); refresh_schema()


# ---------------------------------------------------------------------------
# The safety matrix — 25 cases across question shapes.
# ---------------------------------------------------------------------------

# (question, expected_class, [required_sql_keywords], notes)
CASES: list[tuple[str, str, list[str], str]] = [
    # -------- clean answerable ---------------------------------------
    ("What is the total revenue?",               "ANSWER",  ["sum(revenue"],                        "simple aggregate"),
    ("Show revenue by region",                   "ANSWER",  ["region_name", "group by"],            "breakdown"),
    ("Revenue by month",                         "ANSWER",  ["substr(order_date", "group by"],      "trend"),
    ("Top 5 products by revenue",                "ANSWER",  ["product_name", "limit"],              "ranking"),
    ("Gross margin by category",                 "ANSWER",  ["products.category", "group by"],      "breakdown+kpi"),
    ("What is the average order value in August?","ANSWER", ["sum(revenue)*1.0/count", "2026-08-01"],"filtered aggregate"),
    ("How many orders did we get?",              "ANSWER",  ["count(*"],                            "order count"),
    ("Revenue in July compared to June",         "ANSWER",  ["2026-07-01"],                         "'in July' hint"),

    # -------- vague / open-ended → CLARIFY ---------------------------
    ("How is my business doing?",                "CLARIFY", [], "narrative ask"),
    ("Give me insights",                         "CLARIFY", [], "no KPI"),
    ("What should I do?",                        "CLARIFY", [], "judgement"),
    ("Give me the numbers",                      "CLARIFY", [], "vague"),
    ("Anything interesting?",                    "CLARIFY", [], "vague"),
    ("Tell me about the business",               "CLARIFY", [], "vague"),

    # -------- out of scope → CLARIFY ---------------------------------
    ("What is the meaning of life?",             "CLARIFY", [], "OOS"),
    ("What is the weather?",                     "CLARIFY", [], "OOS"),
    ("How many employees do we have?",           "CLARIFY", [], "HR not in schema"),
    ("What is our marketing spend?",             "CLARIFY", [], "not in schema"),

    # -------- specific breakdown that DOESN'T exist on demo → CLARIFY -
    ("Which sub-categories are losing money?",   "CLARIFY", [], "sub_category not on demo"),
    ("Revenue by state",                         "CLARIFY", [], "state not on demo"),

    # -------- safe fallback cases ------------------------------------
    # Ambiguous phrasing — either the system understands and answers, or
    # it clarifies. Both are acceptable; a wrong-SQL ANSWER is not.
    ("How's revenue?",                           "SAFE",    [], "vague-ish, has KPI"),
    ("Sales?",                                   "SAFE",    [], "one-word KPI"),

    # -------- diagnostic ---------------------------------------------
    ("Why did revenue decrease in July?",        "ANSWER",  ["2026-07-01"],                         "diagnostic"),

    # -------- specific breakdowns on demo that DO exist --------------
    ("Show gross margin by category",            "ANSWER",  ["products.category", "group by"],      "breakdown"),
    ("Top products by revenue",                  "ANSWER",  ["product_name", "limit"],              "ranking default"),
]


@pytest.fixture(scope="module")
def orch():
    from insightflow.orchestrator import Orchestrator
    return Orchestrator()


def _check_answer(resp, keywords):
    sql = (resp.sql or "").lower()
    for kw in keywords:
        assert kw.lower() in sql, f"missing keyword {kw!r} in SQL: {sql!r}"


@pytest.mark.parametrize("question,cls,keywords,note", CASES,
                         ids=[c[0][:40] for c in CASES])
def test_safety_matrix(orch, question, cls, keywords, note):
    resp = orch.ask(question)
    action = resp.decision.action
    coverage = resp.confidence.signals.get("intent_coverage", 1.0)
    confidence = resp.confidence.score

    if cls == "ANSWER":
        # Must ANSWER (or WARN) and produce SQL matching keywords.
        assert action in ("ANSWER", "WARN"), \
            f"{question!r}: expected ANSWER/WARN, got {action} ({resp.decision.reason})"
        _check_answer(resp, keywords)
        # A high-confidence ANSWER must have high coverage — otherwise
        # something else in the pipeline is wrong.
        if action == "ANSWER":
            assert coverage >= 0.9, \
                f"{question!r}: ANSWER at coverage {coverage} — unsafe"

    elif cls == "CLARIFY":
        assert action == "CLARIFY", \
            f"{question!r}: expected CLARIFY, got {action} conf={confidence:.2f}"
        # Must be below the ANSWER threshold — CLARIFY itself is safe, but
        # the score should not indicate an answer was owed.
        assert confidence < 0.70, \
            f"{question!r}: CLARIFY at confidence {confidence} — unexpectedly high"

    elif cls == "SAFE":
        # Any decision is fine; but if we ANSWER, coverage must be high.
        if action == "ANSWER":
            assert coverage >= 0.9, \
                f"{question!r}: ANSWER at coverage {coverage} — unsafe"

    else:
        pytest.fail(f"unknown class: {cls}")


def test_no_unsafe_answers_across_matrix(orch):
    """Aggregate guarantee: across every case, there is NO
    high-confidence-wrong-SQL answer."""
    unsafe: list[str] = []
    for question, cls, keywords, _ in CASES:
        resp = orch.ask(question)
        coverage = resp.confidence.signals.get("intent_coverage", 1.0)
        # Definition of unsafe here: decided ANSWER at high confidence,
        # but coverage says the SQL didn't match the question.
        if resp.decision.action == "ANSWER" and resp.confidence.score >= 0.70 \
                and coverage < 0.9:
            unsafe.append(
                f"  {question!r} → conf={resp.confidence.score:.2f} "
                f"coverage={coverage:.2f} sql={resp.sql!r}"
            )
    assert not unsafe, "unsafe answers detected:\n" + "\n".join(unsafe)
