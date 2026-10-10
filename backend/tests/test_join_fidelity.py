"""Regression tests for join cardinality and KPI change semantics."""
from insightflow.execution.executor import QueryResult
from insightflow.knowledge.kpi import KPI
from insightflow.validation.kpi_validator import validate_kpi
from insightflow.plan.join_fidelity import check_join_fidelity


def test_known_fact_to_dimension_primary_key_join_is_accepted():
    sql = (
        "SELECT SUM(orders.revenue) AS total_revenue FROM orders "
        "JOIN products ON products.product_id = orders.product_id "
        "GROUP BY products.category"
    )
    report = check_join_fidelity(sql)
    assert report.ok, report.checks


def test_join_on_non_key_column_is_flagged_as_possible_fanout():
    sql = (
        "SELECT SUM(orders.revenue) AS total_revenue FROM orders "
        "JOIN products ON products.category = orders.product_id"
    )
    report = check_join_fidelity(sql)
    assert not report.ok
    assert any("multiply fact rows" in c.detail for c in report.checks if not c.passed)


def test_unknown_join_schema_is_not_certified():
    sql = (
        "SELECT SUM(orders.revenue) FROM orders "
        "JOIN promotions ON promotions.region_id = orders.region_id"
    )
    report = check_join_fidelity(sql)
    assert not report.ok
    assert any("unknown schema/cardinality" in c.detail for c in report.checks)


def test_query_without_join_has_no_join_fanout_risk():
    report = check_join_fidelity("SELECT SUM(revenue) AS total_revenue FROM orders")
    assert report.ok


def test_negative_revenue_delta_is_not_validated_as_revenue_level():
    revenue = KPI(
        key="total_revenue", name="Total Revenue", sql_expr="SUM(revenue)",
        description="Revenue", unit="currency", non_negative=True,
    )
    result = QueryResult(columns=["category", "delta"], rows=[("Furniture", -120.0)])
    report = validate_kpi(revenue, result)
    assert report.rules_passed, report.issues


def test_negative_revenue_level_still_fails_nonnegative_rule():
    revenue = KPI(
        key="total_revenue", name="Total Revenue", sql_expr="SUM(revenue)",
        description="Revenue", unit="currency", non_negative=True,
    )
    result = QueryResult(columns=["total_revenue"], rows=[(-120.0,)])
    report = validate_kpi(revenue, result)
    assert not report.rules_passed
    assert any("must be non-negative" in issue for issue in report.issues)


def test_plan_fidelity_report_includes_join_guard():
    from insightflow.plan.fidelity import FidelityValidator
    from insightflow.plan.plan import AnalyticalPlan, MeasureRef

    plan = AnalyticalPlan(
        table="orders",
        measures=[MeasureRef(kpi_id="total_revenue", formula="SUM(revenue)")],
    )
    sql = (
        "SELECT SUM(revenue) AS total_revenue FROM orders "
        "JOIN products ON products.category = orders.product_id"
    )
    report = FidelityValidator().check(plan, sql)
    assert not report.ok
    assert any(c.name.startswith("join:") and not c.passed for c in report.checks)
