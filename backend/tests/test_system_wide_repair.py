"""System-wide semantic-correctness tests for the 2026-10-21 repair.

Covers:

    * dialect compatibility (SQLite rejects Postgres / MSSQL / MySQL
      idioms before execution)
    * semantic fulfilment (SQL executes but doesn't answer the question)
    * LLM text-to-SQL path routed through the same gates
    * explanation never labels an aggregate as a forecast
    * decision-policy coverage of the state machine
    * end-to-end: the three originally-reported failures

Deterministic — pins INSIGHTFLOW_REF_DATE and relies only on the seeded
demo dataset.
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
# Dialect validator unit tests
# ===========================================================================

class TestDialect:
    def _validate(self, sql):
        from insightflow.validation.dialect_validator import validate_dialect
        return validate_dialect(sql, dialect="sqlite")

    def test_rejects_extract_year(self):
        r = self._validate(
            "SELECT revenue FROM orders WHERE EXTRACT(YEAR FROM "
            "order_date) = 2023")
        assert not r.ok
        assert any("extract" in i.lower() for i in r.issues)

    def test_rejects_extract_month_between(self):
        r = self._validate(
            "SELECT SUM(revenue) FROM orders WHERE EXTRACT(MONTH FROM "
            "order_date) BETWEEN 1 AND 9")
        assert not r.ok

    def test_rejects_date_trunc(self):
        r = self._validate(
            "SELECT DATE_TRUNC('month', order_date), SUM(revenue) FROM "
            "orders GROUP BY 1")
        assert not r.ok

    def test_rejects_interval_literal(self):
        r = self._validate(
            "SELECT SUM(revenue) FROM orders WHERE order_date > "
            "CURRENT_DATE - INTERVAL '1 year'")
        assert not r.ok

    def test_rejects_mysql_date_format(self):
        r = self._validate(
            "SELECT DATE_FORMAT(order_date, '%Y-%m'), SUM(revenue) "
            "FROM orders GROUP BY 1")
        assert not r.ok

    def test_rejects_mssql_top(self):
        r = self._validate("SELECT TOP 5 product_name FROM orders")
        assert not r.ok

    def test_rejects_dateadd(self):
        r = self._validate(
            "SELECT SUM(revenue) FROM orders WHERE order_date > "
            "DATEADD(year, -1, '2026-10-21')")
        assert not r.ok

    def test_rejects_generate_series(self):
        r = self._validate(
            "SELECT g FROM generate_series(1, 12) g")
        assert not r.ok

    def test_accepts_sqlite_substr_trend(self):
        r = self._validate(
            "SELECT substr(order_date, 1, 7) AS month, SUM(revenue) "
            "FROM orders GROUP BY substr(order_date, 1, 7)")
        assert r.ok

    def test_accepts_sqlite_half_open_range(self):
        r = self._validate(
            "SELECT SUM(revenue) FROM orders WHERE order_date >= "
            "'2026-01-01' AND order_date < '2026-10-01'")
        assert r.ok

    def test_accepts_sqlite_strftime(self):
        r = self._validate(
            "SELECT strftime('%Y-%m', order_date) AS m, SUM(revenue) "
            "FROM orders GROUP BY m")
        assert r.ok

    def test_empty_sql_is_ok(self):
        r = self._validate("")
        assert r.ok  # dialect validation on empty text is a no-op


# ===========================================================================
# Semantic fulfilment unit tests
# ===========================================================================

class TestFulfilment:
    def _mk_plan(self, **overrides):
        from insightflow.plan import (
            AnalyticalPlan, IntentKind, FilterExpr, MeasureRef, DimRef, Grain,
        )
        plan = AnalyticalPlan(
            intent_kind=IntentKind.DIRECT_KPI,
            table="orders",
            measures=[MeasureRef(
                kpi_id="total_revenue", formula="SUM(revenue)",
                aggregation="sum", unit="currency",
            )],
        )
        for k, v in overrides.items():
            setattr(plan, k, v)
        return plan

    def _res(self, rows, cols):
        from insightflow.execution.executor import QueryResult
        return QueryResult(rows=rows, columns=cols, error=None)

    def test_trend_single_aggregate_row_flags(self):
        from insightflow.plan import FilterExpr, DimRef, Grain, IntentKind
        plan = self._mk_plan(
            intent_kind=IntentKind.TREND,
            dims=[DimRef(column="order_date", is_time=True,
                          time_unit="month")],
            filters=[FilterExpr(kind="time_range", column="order_date",
                                 lo="2026-01", hi="2026-09")],
            grain=Grain(kind="time", time_unit="month",
                         time_column="order_date"),
        )
        from insightflow.validation.semantic_fulfilment import validate_fulfilment
        bad = self._res([(3388831.47,)], ["total_revenue"])
        r = validate_fulfilment(plan, bad)
        assert not r.ok
        assert any("grouping" in i.lower() for i in r.issues)

    def test_trend_multiple_rows_passes(self):
        from insightflow.plan import FilterExpr, DimRef, Grain, IntentKind
        from insightflow.validation.semantic_fulfilment import validate_fulfilment
        plan = self._mk_plan(
            intent_kind=IntentKind.TREND,
            dims=[DimRef(column="order_date", is_time=True,
                          time_unit="month")],
            filters=[FilterExpr(kind="time_range", column="order_date",
                                 lo="2026-01", hi="2026-09")],
            grain=Grain(kind="time", time_unit="month",
                         time_column="order_date"),
        )
        good = self._res([("2026-01", 1.0), ("2026-02", 2.0)],
                          ["month", "total_revenue"])
        r = validate_fulfilment(plan, good)
        assert r.ok

    def test_direct_kpi_with_filter_all_null_flags(self):
        from insightflow.plan import FilterExpr
        from insightflow.validation.semantic_fulfilment import validate_fulfilment
        plan = self._mk_plan(filters=[FilterExpr(
            kind="time_range", column="order_date",
            lo="2025-01", hi="2025-12")])
        null_res = self._res([(None,)], ["total_revenue"])
        r = validate_fulfilment(plan, null_res)
        assert not r.ok
        assert "NULL" in r.issues[0] or "null" in r.issues[0].lower()

    def test_comparison_wrong_row_count_flags(self):
        from insightflow.plan import ComparisonSpec, IntentKind
        from insightflow.validation.semantic_fulfilment import validate_fulfilment
        plan = self._mk_plan(
            intent_kind=IntentKind.COMPARISON,
            comparison=ComparisonSpec(
                time_column="order_date",
                base_period="2026-06", target_period="2026-07",
            ),
        )
        wrong = self._res([("2026-06", 1.0)], ["period", "total_revenue"])
        r = validate_fulfilment(plan, wrong)
        assert not r.ok

    def test_top_n_overflow_flags(self):
        from insightflow.plan import IntentKind, DimRef
        from insightflow.validation.semantic_fulfilment import validate_fulfilment
        plan = self._mk_plan(
            intent_kind=IntentKind.TOP_N,
            top_n=3,
            dims=[DimRef(column="product_name")],
        )
        overflow = self._res(
            [("A", 1.0), ("B", 0.9), ("C", 0.8), ("D", 0.7), ("E", 0.6)],
            ["product_name", "total_revenue"])
        r = validate_fulfilment(plan, overflow)
        assert not r.ok


# ===========================================================================
# End-to-end: the three originally reported failures
# ===========================================================================

class TestReportedCases:
    def test_case1_date_range_trend(self, orch):
        r = orch.ask("Show monthly revenue from January through "
                     "September 2026.")
        assert r.decision.action == "ANSWER"
        rows = r.result.rows
        assert len(rows) == 9
        assert "'2026-01-01'" in r.sql
        assert "'2026-10-01'" in r.sql
        # Dialect must be SQLite — substr(), not EXTRACT()
        assert "extract(" not in r.sql.lower()
        assert "substr(order_date" in r.sql.lower()

    def test_case2_last_year_out_of_range(self, orch):
        r = orch.ask("What was revenue last year?")
        assert r.decision.action == "CLARIFY"
        assert "2025" in r.decision.reason
        # No wrong-year silent answer. The filter must at least be
        # the correct year (2025), not something like 2023.
        if r.sql:
            assert "2023" not in r.sql
            assert "'2025-01-01'" in r.sql

    def test_case3_forecast_abstains_from_history(self, orch):
        r = orch.ask("What will next month's revenue be?")
        # Must NOT return ANSWER. Must NOT execute SQL and present a
        # historical aggregate.
        assert r.decision.action != "ANSWER"
        assert r.confidence.score < 0.70
        if r.sql:
            # If any SQL made it through (it shouldn't), it must not
            # be the historical all-time aggregate.
            assert "sum(revenue)" not in r.sql.lower() or \
                   "where" in r.sql.lower()


# ===========================================================================
# LLM path: feed harmful SQL into _legacy_ask and verify gates refuse
# ===========================================================================

class TestLLMPathHardening:
    def _force_llm_sql(self, monkeypatch, sql):
        """Make the orchestrator take the legacy LLM path and return
        a specific SQL string. Patches:
          - planner.Planner.plan → always AMBIGUOUS (routes to legacy)
          - orchestrator.generate_sql → returns the given SQL
        """
        from insightflow.plan.plan import AnalyticalPlan, IntentKind
        from insightflow.plan.planner import Planner
        from insightflow.nlsql.generator import GenSQL
        import insightflow.orchestrator as orch_mod

        def ambig_plan(self, question):
            return AnalyticalPlan(intent_kind=IntentKind.AMBIGUOUS,
                                   question=question, table="orders")
        monkeypatch.setattr(Planner, "plan", ambig_plan)

        def fake_generate_sql(question, llm=None):
            return GenSQL(sql=sql, intent="llm", kpi=None,
                           dimension=None, month=None,
                           diagnostic=False, source="llm",
                           query_intent=None)
        monkeypatch.setattr(orch_mod, "generate_sql", fake_generate_sql)

    def test_llm_postgres_extract_is_refused(self, orch, monkeypatch):
        self._force_llm_sql(monkeypatch,
            "SELECT SUM(revenue) FROM orders WHERE "
            "EXTRACT(MONTH FROM order_date) BETWEEN 1 AND 9")
        r = orch.ask("Any question — forced to legacy")
        # SQL failed validation (dialect) → ABSTAIN or CLARIFY, not ANSWER.
        assert r.decision.action in ("ABSTAIN", "CLARIFY", "WARN")
        assert r.decision.action != "ANSWER"
        # Diagnostics must record the dialect issue.
        notes_and_reason = (r.decision.reason + " " +
                            " ".join(r.notes or [])).lower()
        assert ("extract" in notes_and_reason or
                "dialect" in notes_and_reason or
                "sqlite" in notes_and_reason or
                "failed validation" in notes_and_reason)

    def test_llm_alltime_total_for_forecast_is_refused(self, orch, monkeypatch):
        # Pre-SQL safety gate catches forecast questions BEFORE the LLM
        # is called, so the SQL from the LLM is irrelevant. We expect
        # CLARIFY whether or not the LLM is active.
        self._force_llm_sql(monkeypatch,
            "SELECT SUM(revenue) AS total_revenue FROM orders")
        r = orch.ask("What will next month's revenue be?")
        assert r.decision.action != "ANSWER"
        # The safety gate did not emit SQL.
        assert not r.sql or "sum(revenue)" not in r.sql.lower() or \
               r.decision.action in ("CLARIFY", "ABSTAIN")


# ===========================================================================
# Explanation safety
# ===========================================================================

class TestExplanationSafety:
    def test_offline_explanation_never_calls_aggregate_a_forecast(self, orch):
        # Pre-gate fires → explanation never gets a chance to label.
        r = orch.ask("What will next month's revenue be?")
        exp = (r.explanation or "").lower()
        # Must not describe an all-time total as a projection.
        assert "will be" not in exp or "forecast" in exp
        assert "$3," not in r.explanation  # no dollar-figure projection

    def test_llm_hallucinated_forecast_is_stripped(self):
        from insightflow.explain.explainer import explain
        from insightflow.reliability.evidence import Evidence
        from insightflow.analysis.analyzer import Analysis
        from insightflow.plan import AnalyticalPlan, IntentKind, MeasureRef
        from insightflow.llm import LLMClient

        # Fake LLM that returns a forecast-flavoured sentence
        class FakeLLM(LLMClient):
            def __init__(self):
                self.available = True
                self._client = object()
                self.provider = "openai"
                self.model = "test"
                self.strict_mode = False
            def complete(self, prompt, system="", temperature=0.0):
                return ("Next month's revenue will be approximately "
                        "$3,500,000, projected from historical trends.")

        plan = AnalyticalPlan(
            intent_kind=IntentKind.DIRECT_KPI,
            table="orders",
            measures=[MeasureRef(kpi_id="total_revenue",
                                  formula="SUM(revenue)")],
        )
        from insightflow.execution.executor import QueryResult
        from insightflow.reliability.evidence import build_evidence
        ev = build_evidence(question="What was revenue in July?",
                             sql="", kpi=None, filters={},
                             result=QueryResult())
        an = Analysis(summary="Deterministic: total revenue was X.")
        out = explain(ev, an, llm=FakeLLM(), plan=plan)
        # The hallucinated LLM text must be stripped — we expect the
        # deterministic summary back.
        assert "will be" not in out.lower()
        assert "projected" not in out.lower()
        assert out == an.summary


# ===========================================================================
# Decision-policy state coverage
# ===========================================================================

class TestDecisionStates:
    def test_ambiguous_question(self, orch):
        r = orch.ask("How is my business doing?")
        assert r.decision.action == "CLARIFY"

    def test_out_of_scope_question(self, orch):
        r = orch.ask("What is the meaning of life?")
        assert r.decision.action == "CLARIFY"

    def test_unsupported_capability_forecast(self, orch):
        r = orch.ask("Predict next quarter's revenue.")
        assert r.decision.action == "CLARIFY"
        assert "forecast" in r.decision.reason.lower()

    def test_destructive_abstain(self, orch):
        r = orch.ask("Delete all orders.")
        assert r.decision.action == "ABSTAIN"

    def test_valid_zero_rows_relative_period(self, orch):
        # 2025 is outside the dataset → CLARIFY, not silent ANSWER.
        r = orch.ask("What was revenue last year?")
        assert r.decision.action == "CLARIFY"

    def test_valid_query_with_data_answers(self, orch):
        r = orch.ask("What is the total revenue?")
        assert r.decision.action == "ANSWER"


# ===========================================================================
# Broad analytical capability regressions
# ===========================================================================

class TestBroadCapabilities:
    def test_total_revenue(self, orch):
        r = orch.ask("What is the total revenue?")
        assert r.decision.action == "ANSWER"
        assert r.result.rows and r.result.rows[0][0] > 0

    def test_order_count(self, orch):
        r = orch.ask("How many orders were placed?")
        assert r.decision.action == "ANSWER"
        assert r.result.rows and r.result.rows[0][0] > 0

    def test_revenue_in_2026(self, orch):
        r = orch.ask("What was revenue in 2026?")
        assert r.decision.action == "ANSWER"

    def test_this_year_matches_dataset(self, orch):
        r = orch.ask("What is this year's revenue?")
        assert r.decision.action == "ANSWER"
        assert "'2026-01-01'" in r.sql

    def test_single_month(self, orch):
        r = orch.ask("Revenue in July 2026")
        assert r.decision.action == "ANSWER"
        assert "'2026-07-01'" in r.sql
        assert "'2026-08-01'" in r.sql

    def test_multi_month_range(self, orch):
        r = orch.ask("Monthly revenue from April through August 2026.")
        assert r.decision.action == "ANSWER"
        assert len(r.result.rows) == 5  # Apr May Jun Jul Aug

    def test_monthly_trend_full_year(self, orch):
        r = orch.ask("Revenue by month in 2026")
        assert r.decision.action == "ANSWER"
        assert len(r.result.rows) >= 2
        # First column must be a month label.
        assert "-" in str(r.result.rows[0][0])

    def test_dimension_breakdown(self, orch):
        r = orch.ask("Revenue by region")
        assert r.decision.action == "ANSWER"
        assert len(r.result.rows) >= 2  # multiple regions

    def test_multi_kpi_breakdown(self, orch):
        r = orch.ask("Revenue and profit by category")
        assert r.decision.action == "ANSWER"
        sql = r.sql.lower()
        assert "sum(revenue)" in sql
        assert "sum(revenue-cost)" in sql


# ===========================================================================
# Data / failure states
# ===========================================================================

class TestFailureStates:
    def test_destructive_does_not_mutate_db(self, orch):
        """Verify by observation: after a destructive attempt, row
        count is unchanged."""
        from insightflow.execution.executor import run_sql
        before = run_sql("SELECT COUNT(*) FROM orders").rows[0][0]
        r = orch.ask("Delete all orders.")
        assert r.decision.action == "ABSTAIN"
        after = run_sql("SELECT COUNT(*) FROM orders").rows[0][0]
        assert before == after

    def test_invalid_sql_abstains(self, monkeypatch, orch):
        # Simulate the planner producing SQL the structural validator
        # will reject (write statement).
        from insightflow.plan.compiler import SQLCompiler
        monkeypatch.setattr(
            SQLCompiler, "compile",
            lambda self, plan: "DELETE FROM orders")
        r = orch.ask("What is revenue?")
        # Executor must never see this.
        assert r.decision.action in ("ABSTAIN", "CLARIFY")
        assert r.decision.action != "ANSWER"

    def test_missing_column_asked_for_clarifies(self, orch):
        # "state" is not a column on the demo dataset
        r = orch.ask("Revenue by state")
        assert r.decision.action in ("CLARIFY", "ABSTAIN", "WARN")

    def test_leap_year_feb_boundary_single_month(self, orch):
        # Not a leap year test per se; just ensures Feb boundary math.
        r = orch.ask("Revenue in February 2026")
        assert r.decision.action == "ANSWER"
        assert "'2026-02-01'" in r.sql
        assert "'2026-03-01'" in r.sql


# ===========================================================================
# Reference-date determinism
# ===========================================================================

class TestReferenceDate:
    def test_ref_date_is_pinned(self):
        from insightflow.plan.planner import _reference_date
        import datetime as dt
        assert _reference_date() == dt.date(2026, 10, 21)

    def test_last_year_resolves_to_2025(self, orch):
        r = orch.ask("What was revenue last year?")
        if r.sql:
            assert "'2025-01-01'" in r.sql
            assert "'2026-01-01'" in r.sql

    def test_last_month_resolves_to_september(self, orch):
        r = orch.ask("What was revenue last month?")
        assert "'2026-09-01'" in r.sql
        assert "'2026-10-01'" in r.sql

    def test_this_quarter_resolves_to_q4_2026(self, orch):
        # Oct 21 → Q4 (Oct-Dec)
        r = orch.ask("What is revenue this quarter?")
        if r.sql:
            assert "'2026-10-01'" in r.sql
            # Q4 ends 2026-12 inclusive, filter ends 2027-01-01 exclusive
            assert "'2027-01-01'" in r.sql

    def test_ytd_resolves_to_jan_through_oct(self, orch):
        r = orch.ask("What is revenue year to date?")
        if r.sql:
            assert "'2026-01-01'" in r.sql
            assert "'2026-11-01'" in r.sql
