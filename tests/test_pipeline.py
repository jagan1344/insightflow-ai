"""End-to-end pipeline tests."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# Seed the demo DB once for the whole session, using the standard path.
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "insightflow.db"


@pytest.fixture(scope="session", autouse=True)
def _seed_db():
    if not DB_PATH.exists():
        import runpy
        runpy.run_path(str(ROOT / "data" / "seed.py"), run_name="__main__")
    yield


@pytest.fixture(scope="module")
def orch():
    # Fresh imports so the engine binds to the seeded DB
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.schema_agent import refresh_schema
    from insightflow.orchestrator import Orchestrator
    reset_engine()
    refresh_schema()
    return Orchestrator()


# ---------------------------------------------------------------------------

def test_total_revenue_answers(orch):
    resp = orch.ask("What is the total revenue?")
    assert resp.decision.action == "ANSWER", resp.decision
    assert resp.confidence.score >= 0.7
    assert resp.sql.strip().lower().startswith("select")


def test_diagnostic_july(orch):
    resp = orch.ask("Why did revenue decrease in July?")
    assert resp.intent == "diagnostic"
    negs = [c for c in resp.analysis.contributors if c.delta < 0]
    assert negs, "expected some negative contributors"
    worst = min(negs, key=lambda c: c.delta)
    assert worst.name in ("Furniture", "East"), \
        f"top negative contributor should be Furniture or East, got {worst}"
    # a recommendation should have been produced
    if resp.decision.action in ("ANSWER", "WARN"):
        assert resp.recommendation is not None


def test_meaning_of_life_clarifies(orch):
    resp = orch.ask("What is the meaning of life?")
    assert resp.decision.action == "CLARIFY"
    assert resp.confidence.score <= 0.4


def test_sql_validator_rejects_drop():
    from insightflow.validation.sql_validator import validate_sql
    r = validate_sql("DROP TABLE orders")
    assert not r.ok
    assert any("only SELECT" in i or "forbidden" in i for i in r.issues)

    r2 = validate_sql("UPDATE orders SET revenue = 0")
    assert not r2.ok


def test_gross_margin_within_range(orch):
    resp = orch.ask("What is the gross margin by category?")
    assert resp.result.ok
    assert resp.result.rows
    # KPI validation should have passed (values in [0,1])
    from insightflow.knowledge.kpi import KPIS
    from insightflow.validation.kpi_validator import validate_kpi
    kv = validate_kpi(KPIS["gross_margin"], resp.result)
    assert kv.rules_passed, kv.issues
    # explicit numeric check
    for row in resp.result.rows:
        val = row[-1]
        assert 0.0 <= float(val) <= 1.0
