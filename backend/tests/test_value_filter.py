"""Phase 2 of the exec-accuracy audit (2026-10-24).

Previously, questions like "Revenue in East region in July 2026" were
silently answered with the all-region July total (202 536.65 instead
of 30 479.76). The planner recognised "East region" as a dim mention
but had no detector for VALUE-equality on that dim.

These tests pin the fix: a dim-value filter is extracted, the
redundant grouping is dropped, and the executed result matches an
INDEPENDENT sqlite3 oracle.
"""
from __future__ import annotations

import os
import runpy
import sqlite3
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


def _fresh_orch():
    from insightflow.orchestrator import Orchestrator
    return Orchestrator()


def _oracle(sql):
    with sqlite3.connect(str(ROOT / "data" / "insightflow.db")) as c:
        return c.execute(sql).fetchall()


class TestValueFilterExecAccuracy:
    def test_region_and_time_scalar(self):
        """Revenue in East region in July 2026 — compound filter."""
        orch = _fresh_orch()
        r = orch.ask("Revenue in East region in July 2026")
        assert r.decision.action == "ANSWER"
        expected = _oracle(
            "SELECT SUM(revenue) FROM orders "
            "JOIN regions ON regions.region_id = orders.region_id "
            "WHERE regions.region_name = 'East' "
            "AND order_date >= '2026-07-01' AND order_date < '2026-08-01'"
        )[0][0]
        assert len(r.result.rows) == 1
        assert abs(float(r.result.rows[0][-1]) - float(expected)) < 1e-4

    def test_category_filter_drops_breakdown(self):
        """Revenue in Furniture category — filter, NOT a breakdown."""
        orch = _fresh_orch()
        r = orch.ask("Revenue in Furniture category in July 2026")
        assert r.decision.action == "ANSWER"
        expected = _oracle(
            "SELECT SUM(revenue) FROM orders "
            "JOIN products ON products.product_id = orders.product_id "
            "WHERE products.category = 'Furniture' "
            "AND order_date >= '2026-07-01' AND order_date < '2026-08-01'"
        )[0][0]
        # Must be ONE row (scalar), not a per-category breakdown.
        assert len(r.result.rows) == 1
        assert abs(float(r.result.rows[0][-1]) - float(expected)) < 1e-4

    def test_segment_value_filter(self):
        """SMB segment revenue — value filter + aggregate scalar."""
        orch = _fresh_orch()
        r = orch.ask("SMB segment revenue")
        assert r.decision.action == "ANSWER"
        expected = _oracle(
            "SELECT SUM(revenue) FROM orders "
            "JOIN customers ON customers.customer_id = orders.customer_id "
            "WHERE customers.segment = 'SMB'"
        )[0][0]
        assert len(r.result.rows) == 1
        assert abs(float(r.result.rows[0][-1]) - float(expected)) < 1e-4

    def test_breakdown_without_value_still_groups(self):
        """Regression: 'Revenue by region' (no value filter) still
        produces a 4-row region breakdown, unchanged."""
        orch = _fresh_orch()
        r = orch.ask("Revenue by region")
        assert r.decision.action == "ANSWER"
        assert len(r.result.rows) == 4

    def test_region_value_filter_outside_dataset_abstains(self):
        """A region name that doesn't exist in the data should NOT be
        extracted as a value filter — the question falls through
        normally and the planner handles it."""
        orch = _fresh_orch()
        r = orch.ask("Revenue in Antarctica region")
        # "Antarctica" is not in regions.region_name → no eq filter
        # extracted → planner handles the dim mention as a breakdown
        # question (or CLARIFY). Either is acceptable; the specific
        # anti-regression is that we don't ANSWER with ALL-region
        # revenue as if the filter was ignored silently.
        if r.decision.action in ("ANSWER", "WARN"):
            # If answered, it should have GROUP BY region (breakdown
            # shape), not a bare SUM.
            assert "group by regions.region_name" in r.sql.lower()


class TestNoRegressionOnRelativeToStat:
    """The value-filter detector must NOT swallow 'above the median'
    etc. and incorrectly produce an eq filter."""
    def test_above_average_customers_still_relative_to_stat(self):
        orch = _fresh_orch()
        r = orch.ask("Which customers have sales above average?")
        assert r.decision.action in ("ANSWER", "WARN")
        # Should be the relative-to-stat SQL shape, not an eq filter.
        assert "with agg as" in r.sql.lower()
