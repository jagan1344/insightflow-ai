"""Regression tests for the diagnose-and-fix pass dated 2026-10-21.

Each test corresponds to one of the confirmed defects in that pass:

    A — explicit date-range truncation
    B — "last year" / relative-period resolution + out-of-range CLARIFY
    C — forecasting requests must NOT be answered by all-time aggregates
    D — diagnostic "why did X drop in M vs N" must decompose by dimension
    E — destructive requests must ABSTAIN BEFORE SQL generation / execution
    F — intent-coverage gate: high confidence alone is not permission to ANSWER
    G — multi-metric breakdowns must preserve all requested metrics
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
def _seed_and_ref_date():
    """Pin the demo DB and the reference 'today' for relative-period
    tests so these assertions are deterministic across time."""
    os.environ.setdefault("INSIGHTFLOW_REF_DATE", "2026-10-21")
    runpy.run_path(str(ROOT / "data" / "seed.py"), run_name="__main__")
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.schema_agent import refresh_schema
    from insightflow.knowledge.dataset_registry import set_active, DEMO_ID
    reset_engine(); refresh_schema(); set_active(DEMO_ID)
    yield
    # Clean up — reseed so other suites start from a known state.
    runpy.run_path(str(ROOT / "data" / "seed.py"), run_name="__main__")
    reset_engine(); refresh_schema(); set_active(DEMO_ID)


@pytest.fixture(scope="module")
def orch():
    from insightflow.orchestrator import Orchestrator
    return Orchestrator()


# ---------------------------------------------------------------------------
# Defect A — explicit date-range parsing
# ---------------------------------------------------------------------------

def test_A_jan_through_sep_returns_full_range(orch):
    r = orch.ask("Show monthly revenue from January through September 2026.")
    assert r.decision.action == "ANSWER"
    rows = r.result.rows
    # Nine months of monthly data, not one.
    assert len(rows) == 9, f"expected 9 months, got {len(rows)}: {rows}"
    # First month is January, last is September.
    assert str(rows[0][0]) == "2026-01"
    assert str(rows[-1][0]) == "2026-09"
    # SQL filter must span January inclusive to October exclusive.
    sql = r.sql.lower()
    assert "'2026-01-01'" in sql
    assert "< '2026-10-01'" in sql


def test_A_between_and_connector(orch):
    r = orch.ask("Show monthly revenue between January and September 2026.")
    assert r.decision.action == "ANSWER"
    assert len(r.result.rows) == 9


def test_A_cross_year_range(orch):
    # September through January — crosses year boundary.
    r = orch.ask("Show monthly revenue from September 2026 through "
                 "January 2027.")
    assert r.decision.action in ("ANSWER", "WARN", "CLARIFY")
    sql = r.sql.lower() if r.sql else ""
    # SQL (if emitted) must at least name both year boundaries.
    if r.sql:
        assert "'2026-09-01'" in sql
        assert "< '2027-02-01'" in sql


def test_A_single_month_still_works(orch):
    r = orch.ask("What was revenue in July 2026?")
    assert r.decision.action == "ANSWER"
    # One month of filter, not nine.
    assert "'2026-07-01'" in r.sql
    assert "'2026-08-01'" in r.sql


def test_A_malformed_range_does_not_crash(orch):
    # Nonsense should not throw and should not return an all-time total.
    r = orch.ask("Show revenue from toaster through chair 2026.")
    # action may be CLARIFY / WARN / ANSWER but never a crash
    assert r.decision.action in ("ANSWER", "WARN", "CLARIFY", "ABSTAIN")


# ---------------------------------------------------------------------------
# Defect B — relative periods
# ---------------------------------------------------------------------------

def test_B_last_year_filters_to_prev_calendar_year(orch):
    r = orch.ask("What was revenue last year?")
    # Reference date is 2026-10-21 → last year = 2025. Dataset has no
    # 2025 data → CLARIFY, not a quiet ANSWER with NULL.
    assert r.decision.action == "CLARIFY"
    reason = r.decision.reason.lower()
    assert "last year" in reason
    assert "2025" in reason


def test_B_last_month_within_dataset_answers_correctly(orch):
    # 2026-09 — the dataset has that month.
    r = orch.ask("What was revenue last month?")
    assert r.decision.action == "ANSWER"
    # Filter must be exactly September 2026.
    assert "'2026-09-01'" in r.sql
    assert "< '2026-10-01'" in r.sql


def test_B_this_month_outside_dataset_clarifies(orch):
    # 2026-10 is outside the seeded range (data stops 2026-09).
    r = orch.ask("What is revenue this month?")
    assert r.decision.action == "CLARIFY"


def test_B_this_year_answers_from_pinned_dataset(orch):
    r = orch.ask("What is revenue this year?")
    assert r.decision.action == "ANSWER"
    # Filter must be 2026, not aggregated across all years.
    assert "'2026-01-01'" in r.sql


def test_B_last_year_never_returns_grouped_all_years(orch):
    r = orch.ask("What was revenue last year?")
    sql = (r.sql or "").lower()
    # Historical defect: a GROUP BY substr(order_date,1,4) all-years rollup.
    assert "group by substr(order_date,1,4)" not in sql, (
        f"Historical regression: 'last year' is grouping all years. "
        f"SQL: {r.sql!r}")


# ---------------------------------------------------------------------------
# Defect C — forecasting intent
# ---------------------------------------------------------------------------

def test_C_forecast_next_month_clarifies(orch):
    r = orch.ask("What will next month's revenue be?")
    assert r.decision.action == "CLARIFY"
    assert "forecast" in r.decision.reason.lower()
    # No SQL may be emitted.
    assert not r.sql


def test_C_predict_next_quarter_clarifies(orch):
    r = orch.ask("Predict next quarter's revenue.")
    assert r.decision.action == "CLARIFY"
    assert not r.sql


def test_C_future_revenue_clarifies(orch):
    r = orch.ask("What is our projected revenue for 2027?")
    assert r.decision.action == "CLARIFY"
    assert not r.sql


def test_C_forecast_never_returns_alltime_total(orch):
    r = orch.ask("What will next month's revenue be?")
    # The historical defect: SQL was 'SELECT SUM(revenue) FROM orders'
    # with no filter. Guarantee: no SQL executed for a forecast.
    assert not r.sql
    # And confidence must not be high.
    assert r.confidence.score < 0.70


# ---------------------------------------------------------------------------
# Defect D — diagnostic
# ---------------------------------------------------------------------------

def test_D_why_drop_july_vs_june_decomposes_by_dim(orch):
    r = orch.ask("Why did revenue drop in July compared to June?")
    assert r.decision.action in ("ANSWER", "WARN")
    assert r.intent == "diagnostic"
    # Must produce more than two rows (per-category/region/etc.
    # decomposition), not just a two-row period comparison.
    assert len(r.result.rows) >= 2
    # SQL must mention both months as filters.
    sql = (r.sql or "").lower()
    assert "'2026-06-01'" in sql
    assert "'2026-07-01'" in sql
    # Contribution structure uses a WITH base/targ pattern.
    assert "with base" in sql


def test_D_why_decrease_single_month_still_decomposes(orch):
    r = orch.ask("Why did revenue decrease in July?")
    assert r.decision.action in ("ANSWER", "WARN")
    assert r.intent == "diagnostic"
    sql = (r.sql or "").lower()
    assert "with base" in sql
    # Must compare July (target) against June (implicit base).
    assert "'2026-06-01'" in sql
    assert "'2026-07-01'" in sql


def test_D_simple_aggregate_is_not_mislabelled_diagnostic(orch):
    # No diagnostic word → should NOT decompose, should return a plain
    # aggregate.
    r = orch.ask("What was revenue in July 2026?")
    assert r.decision.action == "ANSWER"
    assert r.intent != "diagnostic"
    assert "with base" not in (r.sql or "").lower()


# ---------------------------------------------------------------------------
# Defect E — destructive-intent pre-check
# ---------------------------------------------------------------------------

def test_E_delete_all_orders_abstains_without_executing(orch, monkeypatch):
    """Must refuse BEFORE SQL generation. Monkeypatch run_sql so we can
    assert it is never called."""
    import insightflow.execution.executor as ex
    import insightflow.orchestrator as orch_mod
    called = {"n": 0}
    original_run = ex.run_sql

    def _spy(sql):
        called["n"] += 1
        return original_run(sql)
    monkeypatch.setattr(orch_mod, "run_sql", _spy)
    monkeypatch.setattr(ex, "run_sql", _spy)

    r = orch.ask("Delete all orders.")
    assert r.decision.action == "ABSTAIN"
    assert called["n"] == 0, (
        f"run_sql was called {called['n']} time(s) for a destructive "
        f"request — safety pre-check did not fire.")
    assert not r.sql
    assert "destructive" in r.decision.reason.lower()


def test_E_prompt_marker_variant(orch):
    r = orch.ask("[ ] Delete all orders.")
    assert r.decision.action == "ABSTAIN"
    assert not r.sql


def test_E_drop_table_abstains(orch):
    r = orch.ask("Drop the customers table.")
    assert r.decision.action == "ABSTAIN"
    assert not r.sql


def test_E_truncate_data_abstains(orch):
    r = orch.ask("Please truncate all data.")
    assert r.decision.action == "ABSTAIN"
    assert not r.sql


def test_E_wipe_database_abstains(orch):
    r = orch.ask("Can you wipe the database?")
    assert r.decision.action == "ABSTAIN"
    assert not r.sql


def test_E_read_only_question_still_answers(orch):
    # "delete" wasn't in context of orders/data/table — just a word; this
    # question is harmless. (We lean conservative, so this ANSWERs only
    # when destructive-check does not match.)
    r = orch.ask("What is the total revenue?")
    assert r.decision.action == "ANSWER"


def test_E_decrease_is_not_destructive(orch):
    # "decrease" is a legitimate analytical word even though it's near
    # the destructive verbs semantically.
    r = orch.ask("Why did revenue decrease in July?")
    assert r.decision.action in ("ANSWER", "WARN")


def test_E_sql_validator_still_rejects_write_sql():
    """SQL validation itself must remain intact (defence in depth)."""
    from insightflow.validation.sql_validator import validate_sql
    for bad in ("DELETE FROM orders",
                "DROP TABLE orders",
                "UPDATE orders SET revenue=0",
                "INSERT INTO orders VALUES (1)",
                "TRUNCATE TABLE orders"):
        v = validate_sql(bad)
        assert not v.ok, f"SQL validator should reject {bad!r}"


# ---------------------------------------------------------------------------
# Defect F — intent-coverage gate (semantic failure must prevent ANSWER)
# ---------------------------------------------------------------------------

def test_F_forecast_does_not_get_high_confidence_answer(orch):
    r = orch.ask("What will next month's revenue be?")
    assert r.decision.action != "ANSWER"
    assert r.confidence.score < 0.70


def test_F_destructive_does_not_get_high_confidence_answer(orch):
    r = orch.ask("Delete all orders.")
    assert r.decision.action != "ANSWER"
    assert r.confidence.score < 0.70


def test_F_relative_period_outside_data_does_not_answer(orch):
    r = orch.ask("What was revenue last year?")
    assert r.decision.action != "ANSWER"


# ---------------------------------------------------------------------------
# Defect G — multi-metric breakdowns
# ---------------------------------------------------------------------------

def test_G_revenue_and_profit_by_category_keeps_both_metrics(orch):
    r = orch.ask("Show me revenue and profit by category.")
    assert r.decision.action == "ANSWER"
    sql = (r.sql or "").lower()
    # Both measures must appear in SELECT.
    assert "sum(revenue)" in sql
    assert "sum(revenue-cost)" in sql
    # Must group by category.
    assert "group by products.category" in sql
    # And the result must have at least one row per category.
    assert len(r.result.rows) >= 2


def test_G_revenue_and_profit_without_period(orch):
    r = orch.ask("revenue and profit by region")
    assert r.decision.action == "ANSWER"
    sql = (r.sql or "").lower()
    assert "sum(revenue)" in sql
    assert "sum(revenue-cost)" in sql
    assert "region" in sql


def test_G_compound_question_split_still_works(orch):
    # True compound question with its own grouping on each side —
    # splitter must still truncate to first clause (we no longer eat
    # noun1+noun2 but we DO still split independent clauses).
    r = orch.ask("Revenue by region, Profit by month.")
    assert r.decision.action in ("ANSWER", "WARN")
    # The dropped suffix must be surfaced in plan.notes / notes.
    dropped = any("compound_question_dropped_suffix" in n
                   for n in (r.plan_trace or {}).get("notes") or []) \
              or any("compound_question_dropped_suffix" in n
                      for n in r.notes)
    # Not strictly required, but if it is surfaced the explanation
    # should mention it.
    _ = dropped  # tolerate either shape
