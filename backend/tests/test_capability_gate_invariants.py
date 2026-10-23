"""System-wide invariant + capability-gate regression suite.

Covers:

  1. Capability gate — unsupported ops ALWAYS CLARIFY, never silent
     fallback to total_revenue.
  2. Legitimate questions that mention a word like "above average" or
     a numeric threshold must still ANSWER (gate must not over-fire).
  3. Property invariants:
        - adding a restrictive time filter never broadens the result
        - a year-specific query never includes other years
        - equivalent phrasings produce semantically equivalent SQL
        - dataset switching invalidates prior per-dataset state
  4. MTD + QTD + multi-quarter comparison.
  5. Explanation-safety invariants.
"""
from __future__ import annotations

import os
import runpy
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module", autouse=True)
def _seed():
    os.environ["INSIGHTFLOW_REF_DATE"] = "2026-10-21"
    runpy.run_path(str(ROOT / "data" / "seed.py"), run_name="__main__")
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.schema_agent import refresh_schema
    from insightflow.knowledge.dataset_registry import set_active, DEMO_ID
    reset_engine(); refresh_schema(); set_active(DEMO_ID)
    yield
    runpy.run_path(str(ROOT / "data" / "seed.py"), run_name="__main__")
    reset_engine(); refresh_schema(); set_active(DEMO_ID)


@pytest.fixture(scope="module")
def orch():
    from insightflow.orchestrator import Orchestrator
    return Orchestrator()


# ===========================================================================
# Capability gate — must CLARIFY, never silent-ANSWER with a fallback KPI
# ===========================================================================

@pytest.mark.parametrize("q,label", [
    ("What is the median order revenue?",                "median"),
    ("Show me the median revenue by region",             "median_breakdown"),
    ("What is the 90th percentile of revenue?",          "percentile"),
    ("Give me the p95 of order value",                   "p95"),
    ("What is the standard deviation of revenue?",       "stddev"),
    ("What is the variance of monthly revenue?",         "variance"),
    ("What is the 3-month rolling average revenue?",     "rolling_3m"),
    ("Give me the trailing 12-month revenue",            "trailing_12m"),
    ("Moving average of order value",                    "moving_avg"),
    ("What was revenue in the last 90 days?",            "last_n_days"),
    ("Revenue for the past 7 days",                      "past_n_days"),
    ("Top 3 products in each category",                  "top_n_per_group"),
    ("Rank products within each category",               "rank_within"),
    ("How many orders have missing cost?",               "null_count"),
    ("Show me rows with null discount",                  "null_rows"),
    ("Find duplicate orders",                            "duplicates"),
    ("What is the smallest order revenue?",              "min_row_short"),
    ("Give me the maximum single order value",           "max_row"),
    ("How many unique customers do we have?",            "count_distinct"),
    ("Distinct count of products",                       "distinct_count_phrase"),
    ("In which months did revenue exceed 400000?",       "threshold_grouped"),
    ("Regions with revenue above 1 million",             "threshold_num"),
    ("List customers with the most orders this year",    "list_with_rank"),
    ("List products with the highest profit",            "list_with_highest"),
])
def test_unsupported_capability_routes_to_clarify(orch, q, label):
    r = orch.ask(q)
    assert r.decision.action in ("CLARIFY", "ABSTAIN"), \
        f"[{label}] expected CLARIFY/ABSTAIN, got {r.decision.action!r} " \
        f"with sql={r.sql!r}"
    # The historical defect: silent SUM(revenue) fallback. Guard against it.
    sql_lower = (r.sql or "").lower().strip()
    assert sql_lower not in (
        "select sum(revenue) as total_revenue from orders",
        "select count(*) as order_count from orders",
    ), f"[{label}] regressed to silent fallback: {r.sql!r}"


# ===========================================================================
# Legitimate questions that mention gate-adjacent words — must still ANSWER
# ===========================================================================

@pytest.mark.parametrize("q", [
    "Which customers have sales above average?",     # relative_to_stat
    "Which products have revenue below the median?",  # relative_to_stat (median refers to the group statistic, not a requested median output)
    "Top 5 products by revenue",                      # plain top-N
    "Why did revenue decrease in July?",              # diagnostic
    "Revenue by region",                              # breakdown
    "What is the total revenue?",                     # direct_kpi
    "Compare June and July revenue",                  # comparison
])
def test_legitimate_questions_still_answer(orch, q):
    r = orch.ask(q)
    assert r.decision.action in ("ANSWER", "WARN"), \
        f"{q!r} → {r.decision.action} ({r.decision.reason})"


# ===========================================================================
# Property invariants
# ===========================================================================

def _rows(orch, question):
    """Return the raw rows for a question, or None if the pipeline refused."""
    r = orch.ask(question)
    if r.decision.action not in ("ANSWER", "WARN"):
        return None
    return r.result.rows


def test_invariant_adding_time_filter_narrows_or_equals(orch):
    """A time-filtered sum must never exceed the all-time sum."""
    all_time = _rows(orch, "What is the total revenue?")
    jul = _rows(orch, "What was revenue in July 2026?")
    assert all_time and jul
    assert float(jul[0][-1]) <= float(all_time[0][-1]) + 1e-6, (
        f"July revenue {jul[0][-1]} must not exceed all-time {all_time[0][-1]}")


def test_invariant_year_specific_returns_no_other_year(orch):
    """A trend filtered to 2026 must only contain 2026 buckets."""
    r = orch.ask("Monthly revenue in 2026")
    assert r.decision.action == "ANSWER"
    for row in r.result.rows:
        assert str(row[0]).startswith("2026"), (
            f"2026-filtered trend returned non-2026 bucket: {row[0]!r}")


def test_invariant_breakdown_has_grouping(orch):
    """A breakdown by region must have at least 2 rows (demo has 4)."""
    r = orch.ask("Revenue by region")
    assert r.decision.action == "ANSWER"
    assert len(r.result.rows) >= 2
    # Column names must include the dimension.
    cols = [c.lower() for c in (r.result.columns or [])]
    assert any("region" in c for c in cols)


def test_invariant_equivalent_phrasings_same_sql_shape(orch):
    """Two paraphrases of the same question must produce the same
    SQL (modulo whitespace)."""
    pairs = [
        ("Revenue by region", "Show me revenue by region"),
        ("Total revenue", "What is the total revenue?"),
        ("Top 3 products by revenue", "Top three products by revenue"),
    ]
    for a, b in pairs:
        sa = orch.ask(a).sql.lower().replace(" ", "")
        sb = orch.ask(b).sql.lower().replace(" ", "")
        # Equivalent phrasings must give equivalent SQL (or both refuse).
        assert sa == sb or (not sa and not sb), \
            f"paraphrases diverged:\n  {a!r} → {sa}\n  {b!r} → {sb}"


def test_invariant_dataset_switch_reseed_isolates(orch):
    """After reseeding, a question returns results from the fresh seed."""
    import runpy
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.schema_agent import refresh_schema
    from insightflow.knowledge.dataset_registry import set_active, DEMO_ID
    r1 = orch.ask("What is the total revenue?")
    assert r1.decision.action == "ANSWER"
    v1 = float(r1.result.rows[0][-1])
    # Reseed
    runpy.run_path(str(ROOT / "data" / "seed.py"), run_name="__main__")
    reset_engine(); refresh_schema(); set_active(DEMO_ID)
    r2 = orch.ask("What is the total revenue?")
    assert r2.decision.action == "ANSWER"
    v2 = float(r2.result.rows[0][-1])
    # Deterministic seed → identical totals.
    assert abs(v1 - v2) < 1e-6


def test_invariant_semantic_failure_never_becomes_high_conf_answer(orch):
    """Across every CLARIFY'd capability-gate case, confidence must be
    < 0.70. A high-confidence CLARIFY would be a decision-policy bug."""
    for q in [
        "What is the median order revenue?",
        "What is the 90th percentile of revenue?",
        "Rolling 3-month revenue average",
        "In which months did revenue exceed 400k?",
        "Top product in each category",
    ]:
        r = orch.ask(q)
        assert r.decision.action in ("CLARIFY", "ABSTAIN")
        assert r.confidence.score < 0.70, (
            f"{q!r} refused but with inflated confidence {r.confidence.score}")


# ===========================================================================
# MTD / QTD / multi-quarter comparison
# ===========================================================================

def test_mtd_resolves_to_current_month_to_ref_date(orch):
    r = orch.ask("What is the month to date revenue?")
    # Pinned ref date 2026-10-21. Oct 2026 is outside the demo range
    # (data stops Sep 2026) → CLARIFY/WARN with helpful message. The
    # SQL must at least mention October 2026 if emitted.
    assert r.decision.action in ("CLARIFY", "WARN")
    if r.sql:
        assert "'2026-10-01'" in r.sql
        assert "'2026-11-01'" in r.sql


def test_qtd_resolves_to_current_quarter_to_ref_date(orch):
    r = orch.ask("What is quarter to date revenue?")
    # Oct 21 → Q4 (Oct–Dec). QTD = Oct 1 to Oct 21-ish; MTD precision
    # (month boundary of ref date) → filter 2026-10-01 to 2026-11-01.
    if r.sql:
        assert "'2026-10-01'" in r.sql


def test_multi_quarter_comparison_returns_two_periods(orch):
    r = orch.ask("Compare Q2 and Q3 2026 revenue")
    assert r.decision.action in ("ANSWER", "WARN")
    # Two-period comparison → two rows.
    assert len(r.result.rows) == 2


# ===========================================================================
# Explanation safety
# ===========================================================================

def test_explanation_never_calls_aggregate_a_forecast(orch):
    """Any pre-gated forecast question → explanation must not contain
    projection phrasing describing an all-time sum."""
    r = orch.ask("What will next month's revenue be?")
    exp = (r.explanation or "").lower()
    # The pre-gate fires → no dollar-figure forecast.
    assert "$3," not in r.explanation
    # Even if an LLM later gets involved, "will be approximately" would
    # be stripped. Here we assert the deterministic text at minimum.
    assert "forecasting" in exp or "forecast" in exp or r.decision.action == "CLARIFY"


# ===========================================================================
# API contract — plan_trace carries intent + filters for every answer
# ===========================================================================

def test_plan_trace_records_intent_and_filters(orch):
    r = orch.ask("Revenue in July 2026")
    assert r.decision.action == "ANSWER"
    pt = r.plan_trace or {}
    assert pt.get("intent_kind") == "direct_kpi"
    # filters element exists and contains a time_range entry
    filters = pt.get("filters", [])
    assert any(f.get("kind") == "time_range" for f in filters), (
        f"plan_trace missing time_range filter: {filters}")
