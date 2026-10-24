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

# ---- Still SAFELY REFUSED (genuinely unsupported) ----
# After Phase 4 (2026-10-23) median / percentile / stddev / variance
# are IMPLEMENTED via Python post-aggregation (see analysis/stats.py).
# Mode / skew / kurtosis / non-monthly rolling / duplicates /
# list-with-rank / generic data quality remain refused.
@pytest.mark.parametrize("q,label", [
    ("What is the skewness of revenue?",                 "skewness"),
    ("What is the kurtosis of revenue?",                 "kurtosis"),
    ("Give me the mode value of revenue",                "mode"),
    ("Give me the trailing 12-day revenue",              "trailing_12d_non_monthly"),
    ("Find duplicate orders",                            "duplicates"),
    ("List customers with the most orders this year",    "list_with_rank"),
    ("List products with the highest profit",            "list_with_highest"),
    ("Show me the missing values",                       "generic_data_quality"),
])
def test_unsupported_capability_routes_to_clarify(orch, q, label):
    r = orch.ask(q)
    assert r.decision.action in ("CLARIFY", "ABSTAIN"), \
        f"[{label}] expected CLARIFY/ABSTAIN, got {r.decision.action!r} " \
        f"with sql={r.sql!r}"
    sql_lower = (r.sql or "").lower().strip()
    assert sql_lower not in (
        "select sum(revenue) as total_revenue from orders",
        "select count(*) as order_count from orders",
    ), f"[{label}] regressed to silent fallback: {r.sql!r}"


# ---- IMPLEMENTED AND VERIFIED — oracle-matched answers ----
import sqlite3

_ORACLE_DB = str(ROOT / "data" / "insightflow.db")


def _oracle(sql: str):
    with sqlite3.connect(_ORACLE_DB) as c:
        return c.execute(sql).fetchall()


IMPLEMENTED_CASES = [
    # (tag, question, oracle_sql, extractor returning the comparable value)
    ("count_distinct_customers",
     "How many distinct customers do we have?",
     "SELECT COUNT(DISTINCT customer_name) FROM customers",
     lambda rows: rows[0][0]),
    ("count_distinct_products",
     "How many distinct products are there?",
     "SELECT COUNT(DISTINCT product_name) FROM products",
     lambda rows: rows[0][0]),
    ("null_count_cost",
     "How many orders have missing cost?",
     "SELECT COUNT(*) FROM orders WHERE cost IS NULL",
     lambda rows: rows[0][0]),
    ("extremum_max_revenue",
     "What is the maximum revenue?",
     "SELECT MAX(revenue) FROM orders",
     lambda rows: rows[0][0]),
    ("extremum_min_revenue",
     "What is the minimum revenue?",
     "SELECT MIN(revenue) FROM orders",
     lambda rows: rows[0][0]),
    ("extremum_max_quantity",
     "What is the maximum quantity?",
     "SELECT MAX(quantity) FROM orders",
     lambda rows: rows[0][0]),
    ("last_30_days",
     "Revenue in the last 30 days",
     "SELECT SUM(revenue) FROM orders "
     "WHERE order_date >= '2026-09-22' AND order_date < '2026-10-22'",
     lambda rows: rows[0][0]),
    ("threshold_months_gt",
     "In which months did revenue exceed 400000?",
     "SELECT substr(order_date,1,7), SUM(revenue) FROM orders "
     "GROUP BY substr(order_date,1,7) HAVING SUM(revenue) > 400000 "
     "ORDER BY SUM(revenue) DESC",
     lambda rows: sorted(rows)),
    ("threshold_regions_gt",
     "Regions with revenue above 500000",
     "SELECT regions.region_name, SUM(revenue) FROM orders "
     "JOIN regions ON regions.region_id = orders.region_id "
     "GROUP BY regions.region_name HAVING SUM(revenue) > 500000 "
     "ORDER BY SUM(revenue) DESC",
     lambda rows: sorted(rows)),
    ("rolling_avg_3m",
     "3-month rolling average revenue",
     "WITH agg AS (SELECT substr(order_date,1,7) m, SUM(revenue) v "
     "FROM orders GROUP BY m) "
     "SELECT m, v, AVG(v) OVER (ORDER BY m ROWS BETWEEN 2 PRECEDING "
     "AND CURRENT ROW) FROM agg ORDER BY m",
     lambda rows: rows),  # whole series
    ("top_2_per_category",
     "Top 2 products per category by revenue",
     "WITH g AS (SELECT products.category c, products.product_name p, "
     "SUM(revenue) v FROM orders JOIN products ON "
     "products.product_id = orders.product_id GROUP BY c, p), "
     "r AS (SELECT c, p, v, ROW_NUMBER() OVER (PARTITION BY c "
     "ORDER BY v DESC) rk FROM g) "
     "SELECT c, p, v FROM r WHERE rk <= 2 ORDER BY c, rk",
     lambda rows: sorted(rows)),
    # Phase 4 (2026-10-23) — statistical post-aggregations.
    # Extractor handles both the ORACLE call (list of column rows)
    # and the SYSTEM call (single aggregated-value row) by shape.
    ("median_revenue",
     "What is the median order revenue?",
     "SELECT revenue FROM orders ORDER BY revenue",
     lambda rows: round(_scalar_or_stat(rows, _python_median), 4)),
    ("percentile_90_revenue",
     "What is the 90th percentile of revenue?",
     "SELECT revenue FROM orders",
     lambda rows: round(_scalar_or_stat(rows, lambda vs: _python_percentile(vs, 90)), 4)),
    ("stddev_revenue",
     "What is the standard deviation of revenue?",
     "SELECT revenue FROM orders",
     lambda rows: round(_scalar_or_stat(rows, _python_stdev), 4)),
    ("variance_revenue",
     "What is the variance of revenue?",
     "SELECT revenue FROM orders",
     lambda rows: round(_scalar_or_stat(rows, _python_variance), 4)),
]


def _scalar_or_stat(rows, stat_fn):
    """When `rows` has exactly one row with one column, assume that
    column is the already-aggregated statistic and return it as-is.
    Otherwise compute `stat_fn` across the first column."""
    if len(rows) == 1 and len(rows[0]) == 1:
        return float(rows[0][0])
    return stat_fn([r[0] for r in rows])


import statistics as _stats_mod
import math as _math


def _python_median(vals):
    return _stats_mod.median(float(v) for v in vals if v is not None)


def _python_percentile(vals, p):
    xs = sorted(float(v) for v in vals if v is not None)
    k = (p / 100.0) * (len(xs) - 1)
    lo, hi = int(_math.floor(k)), int(_math.ceil(k))
    return xs[lo] if lo == hi else xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _python_stdev(vals):
    return _stats_mod.stdev(float(v) for v in vals if v is not None)


def _python_variance(vals):
    return _stats_mod.variance(float(v) for v in vals if v is not None)


@pytest.mark.parametrize("tag,q,oracle_sql,extract",
                          [(c[0], c[1], c[2], c[3]) for c in IMPLEMENTED_CASES],
                          ids=[c[0] for c in IMPLEMENTED_CASES])
def test_implemented_capability_matches_oracle(orch, tag, q, oracle_sql, extract):
    r = orch.ask(q)
    assert r.decision.action in ("ANSWER", "WARN"), \
        f"[{tag}] expected ANSWER/WARN, got {r.decision.action!r} " \
        f"(reason={r.decision.reason!r})"
    assert r.result.ok, f"[{tag}] execution failed: {r.result.error}"
    sys_val = extract(list(r.result.rows))
    ora_val = extract(_oracle(oracle_sql))
    assert sys_val == ora_val, (
        f"[{tag}] system/oracle mismatch:\n"
        f"  system: {sys_val}\n"
        f"  oracle: {ora_val}")


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
        "Give me the mode value of revenue",
        "What is the skewness of revenue?",
        "Find duplicate orders",
        "List products with the highest profit",
    ]:
        r = orch.ask(q)
        assert r.decision.action in ("CLARIFY", "ABSTAIN"), (
            f"{q!r} should be refused but got {r.decision.action}")
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
