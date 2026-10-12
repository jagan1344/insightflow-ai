"""Deterministic fault-injection checks for join and KPI-value guardrails.

This is a targeted mutation experiment, separate from the paper benchmark.
It deliberately alters join predicates and KPI result columns to verify
that the guards accept legitimate cases and reject known failure modes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from insightflow.execution.executor import QueryResult
from insightflow.knowledge.kpi import KPI
from insightflow.plan.join_fidelity import check_join_fidelity
from insightflow.validation.kpi_validator import validate_kpi


REVENUE = KPI(
    key="total_revenue",
    name="Total Revenue",
    sql_expr="SUM(revenue)",
    description="Revenue level",
    unit="currency",
    non_negative=True,
)

JOIN_CASES = [
    (
        "valid_fact_to_dimension_pk",
        "SELECT SUM(orders.revenue) FROM orders JOIN products "
        "ON products.product_id = orders.product_id",
        True,
    ),
    (
        "mutated_non_key_join",
        "SELECT SUM(orders.revenue) FROM orders JOIN products "
        "ON products.category = orders.product_id",
        False,
    ),
    (
        "mutated_unrelated_safe_predicate",
        "SELECT SUM(orders.revenue) FROM orders JOIN products "
        "ON customers.customer_id = orders.customer_id",
        False,
    ),
    (
        "mutated_or_bypass",
        "SELECT SUM(orders.revenue) FROM orders JOIN products "
        "ON products.product_id = orders.product_id OR 1 = 1",
        False,
    ),
    (
        "unknown_schema_join",
        "SELECT SUM(orders.revenue) FROM orders JOIN promotions "
        "ON promotions.region_id = orders.region_id",
        False,
    ),
    (
        "grouped_cte_join_on_group_key",
        "WITH base AS (SELECT region, SUM(revenue) AS v FROM sales "
        "GROUP BY region), targ AS (SELECT region, SUM(revenue) AS v "
        "FROM sales GROUP BY region) SELECT base.region FROM base "
        "LEFT JOIN targ ON base.region = targ.region",
        True,
    ),
    (
        "mutated_grouped_cte_non_group_key",
        "WITH base AS (SELECT region, SUM(revenue) AS v FROM sales "
        "GROUP BY region), targ AS (SELECT region, SUM(revenue) AS v "
        "FROM sales GROUP BY region) SELECT base.region FROM base "
        "LEFT JOIN targ ON base.v = targ.v",
        False,
    ),
]


def main() -> int:
    results = []
    for name, sql, expected in JOIN_CASES:
        observed = check_join_fidelity(sql).ok
        results.append({
            "case": name,
            "expected_safe": expected,
            "observed_safe": observed,
            "passed": observed is expected,
        })

    delta = validate_kpi(
        REVENUE,
        QueryResult(columns=["region", "delta"], rows=[("West", -25.0)]),
    )
    results.append({
        "case": "negative_revenue_delta_is_not_level",
        "expected_safe": True,
        "observed_safe": delta.rules_passed,
        "passed": delta.rules_passed is True,
    })

    negative_level = validate_kpi(
        REVENUE,
        QueryResult(columns=["total_revenue"], rows=[(-25.0,)]),
    )
    results.append({
        "case": "negative_revenue_level_is_rejected",
        "expected_safe": False,
        "observed_safe": negative_level.rules_passed,
        "passed": negative_level.rules_passed is False,
    })

    report = {
        "experiment": "join_fidelity_and_kpi_delta_fault_injection",
        "n_cases": len(results),
        "n_passed": sum(r["passed"] for r in results),
        "n_failed": sum(not r["passed"] for r in results),
        "results": results,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["n_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
