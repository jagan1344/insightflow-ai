"""Phase 5 — stateful follow-up resolver.

Covers the three documented rewrite rules:
  1. "now by X" / "and by X" → replace dim in the last question
  2. "and in <period>" / "for <period>" → change the time filter
  3. "compare it to <X>" → promote the last question into a comparison

Also covers safety rules:
  * dataset switch between turns must disable follow-up rewrite
  * CLARIFY'd / ABSTAIN'd questions do not become the new anchor
  * references with no prior anchor pass through unchanged (planner
    then CLARIFIEs on its own)
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


def _fresh_orch():
    """A FRESH orchestrator per test, so follow-up state doesn't leak
    between tests."""
    from insightflow.orchestrator import Orchestrator
    return Orchestrator()


# ===========================================================================
# Resolver unit tests (no DB)
# ===========================================================================

class TestResolverUnits:
    def _r(self, prev, q):
        from insightflow.conversation import (
            resolve_followup, capture_context, ConversationContext)
        ctx = ConversationContext()
        capture_context(prev, ctx, dataset_id="demo")
        return resolve_followup(q, ctx, active_dataset_id="demo")

    def test_now_by_region_rewrites(self):
        out = self._r("What was revenue in July 2026?", "Now by region")
        lo = out.lower()
        assert "revenue" in lo and "by region" in lo and "july 2026" in lo

    def test_and_by_category_rewrites(self):
        out = self._r("Revenue in July 2026", "And by category")
        lo = out.lower()
        assert "revenue" in lo and "by category" in lo and "july 2026" in lo

    def test_what_about_june_rewrites_period(self):
        out = self._r("Revenue in July 2026", "What about in June 2026")
        assert "june 2026" in out.lower()

    def test_compare_to_last_month_rewrites(self):
        out = self._r("Revenue in July 2026",
                       "Compare it to last month")
        assert "last month" in out.lower()
        assert "revenue" in out.lower() and "july" in out.lower()

    def test_no_prior_anchor_passes_through(self):
        from insightflow.conversation import (
            resolve_followup, ConversationContext)
        ctx = ConversationContext()
        q = "Now by region"
        assert resolve_followup(q, ctx) == q

    def test_dataset_change_disables_rewrite(self):
        from insightflow.conversation import (
            resolve_followup, capture_context, ConversationContext)
        ctx = ConversationContext()
        capture_context("Revenue in July 2026", ctx, dataset_id="demo")
        # Different active dataset — must NOT rewrite.
        out = resolve_followup("Now by region", ctx,
                                active_dataset_id="uploaded_123")
        assert out == "Now by region"

    def test_non_followup_passes_through(self):
        assert self._r("Revenue in July 2026",
                        "What is the total revenue?") \
               == "What is the total revenue?"


# ===========================================================================
# End-to-end integration tests
# ===========================================================================

class TestFollowupE2E:
    def test_now_by_region_preserves_filter(self):
        orch = _fresh_orch()
        r1 = orch.ask("What was revenue in July 2026?")
        assert r1.decision.action == "ANSWER"
        r2 = orch.ask("Now by region")
        assert r2.decision.action == "ANSWER"
        # Must still filter to July 2026 AND group by region.
        sql = r2.sql.lower()
        assert "'2026-07-01'" in sql and "'2026-08-01'" in sql
        assert "group by regions.region_name" in sql
        # And return multiple regions.
        assert len(r2.result.rows) >= 2

    def test_and_in_june_rewrites_time(self):
        orch = _fresh_orch()
        r1 = orch.ask("Revenue in July 2026")
        assert r1.decision.action == "ANSWER"
        r2 = orch.ask("And in June 2026")
        assert r2.decision.action == "ANSWER"
        sql = r2.sql.lower()
        assert "'2026-06-01'" in sql
        assert "'2026-07-01'" in sql  # exclusive end

    def test_clarify_does_not_overwrite_anchor(self):
        orch = _fresh_orch()
        r1 = orch.ask("What was revenue in July 2026?")  # anchor
        assert r1.decision.action == "ANSWER"
        # Follow-up that fails: force a destructive-ish anchor replacement attempt
        r2 = orch.ask("Delete all orders.")
        assert r2.decision.action == "ABSTAIN"
        # The next follow-up must still rewrite against the July 2026 anchor.
        r3 = orch.ask("Now by region")
        assert r3.decision.action == "ANSWER"
        assert "'2026-07-01'" in r3.sql.lower()

    def test_bare_followup_without_anchor_falls_back(self):
        orch = _fresh_orch()
        r = orch.ask("Now by region")  # no prior successful anchor
        # Planner sees "Now by region" and handles it as a fresh question.
        # Must still ANSWER (it's a plain breakdown) OR CLARIFY, not crash.
        assert r.decision.action in ("ANSWER", "WARN", "CLARIFY")

    def test_fresh_orchestrator_has_no_shared_state(self):
        a, b = _fresh_orch(), _fresh_orch()
        a.ask("What was revenue in July 2026?")
        # b has never been asked anything; its state is untouched.
        from insightflow.conversation import ConversationContext
        assert b._ctx.last_question is None
