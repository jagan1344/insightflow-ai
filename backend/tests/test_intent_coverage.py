"""Regression tests for the 2026-09-23 intent-coverage fix.

Purpose: guarantee the class of failures that motivated this change
cannot silently reappear:

  1. "Which product sub-categories are draining cash instead of making
     money" — must GROUP BY sub_category and HAVING SUM(profit) < 0.
  2. "Are high discounts killing our profit margins in certain regions?
     (Analyze using: Discount, Profit, Region)" — must GROUP BY region
     and touch profit + margin + discount.
  3. Bare aggregate "What is the total revenue?" — must still ANSWER
     with high confidence (regression guard).
  4. A specific breakdown asked against the demo dataset (no sub_category
     column) — must CLARIFY naming the missing column.
  5. Coverage math: bare-aggregate intent → 1.0; mismatched SQL → < 1.0.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module", autouse=True)
def _seed_demo():
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.schema_agent import refresh_schema
    import runpy
    runpy.run_path(str(ROOT / "data" / "seed.py"), run_name="__main__")
    reset_engine(); refresh_schema()
    yield
    # restore demo for downstream tests
    runpy.run_path(str(ROOT / "data" / "seed.py"), run_name="__main__")
    reset_engine(); refresh_schema()


def _superstore_bytes() -> bytes:
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    ws.append(["Order Date", "Region", "Category", "Sub-Category", "Product Name",
               "Customer Name", "Segment", "Quantity", "Sales", "Profit", "Discount"])
    for row in [
        ("2026-05-01", "West",  "Furniture",  "Chairs",    "Big Chair",   "Alice", "SMB",       3,  900, 270, 0.0),
        ("2026-05-04", "North", "Furniture",  "Chairs",    "Mesh Chair",  "Bob",   "Enterprise",2,  600, 200, 0.0),
        ("2026-05-10", "East",  "Furniture",  "Tables",    "Big Table",   "Cara",  "Consumer",  1,  300, -80, 0.2),
        ("2026-05-15", "East",  "Furniture",  "Tables",    "Dining Set",  "Dara",  "SMB",       1,  700, -120, 0.3),
        ("2026-05-20", "East",  "Furniture",  "Bookcases", "Wall Rack",   "Eve",   "Consumer",  1,  400, -160, 0.4),
        ("2026-05-22", "East",  "Office",     "Binders",   "3-Ring",      "Fay",   "Enterprise",8,   80,   4, 0.5),
        ("2026-05-27", "West",  "Office",     "Paper",     "A4 Ream",     "Hank",  "Enterprise",10, 120,  55, 0.0),
        ("2026-05-30", "South", "Technology", "Phones",    "XPhone",      "Iris",  "Consumer",  1, 1200, 300, 0.05),
    ]:
        ws.append(row)
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


# ---------------------------------------------------------------------------
# 1) After a Superstore-shaped upload, both failing questions ANSWER
#    with the *correct* SQL and high coverage.
# ---------------------------------------------------------------------------

def test_draining_cash_by_sub_category_after_upload():
    from fastapi.testclient import TestClient
    from api.main import app
    with TestClient(app) as client:
        r = client.post(
            "/api/upload/orders?mode=replace",
            files={"file": ("s.xlsx", _superstore_bytes(),
                            "application/vnd.openxmlformats-officedocument"
                            ".spreadsheetml.sheet")},
        )
        assert r.status_code == 200, r.text
        r = client.post("/api/ask",
                        json={"question": "Which product sub-categories are "
                                          "draining cash instead of making money"})
        body = r.json()
        sql = (body["sql"] or "").lower()
        assert "group by" in sql
        assert "sub_category" in sql
        assert "having" in sql
        assert "< 0" in sql
        assert body["decision"]["action"] in ("ANSWER", "WARN")
        assert body["confidence"]["signals"]["intent_coverage"] >= 0.9
        assert body["confidence"]["score"] >= 0.6


def test_discount_margin_region_after_upload():
    from fastapi.testclient import TestClient
    from api.main import app
    with TestClient(app) as client:
        client.post(
            "/api/upload/orders?mode=replace",
            files={"file": ("s.xlsx", _superstore_bytes(),
                            "application/vnd.openxmlformats-officedocument"
                            ".spreadsheetml.sheet")},
        )
        q = ("Are high discounts killing our profit margins in "
             "certain regions? (Analyze using: Discount, Profit, Region)")
        r = client.post("/api/ask", json={"question": q})
        body = r.json()
        sql = (body["sql"] or "").lower()
        assert "group by" in sql
        # dimension is region
        assert "region" in sql
        # SQL touches all three factors
        assert "discount" in sql
        assert "revenue-cost" in sql       # profit / margin expression
        assert body["decision"]["action"] in ("ANSWER", "WARN")
        assert body["confidence"]["signals"]["intent_coverage"] >= 0.9
        assert body["confidence"]["score"] >= 0.6


# ---------------------------------------------------------------------------
# 2) Regression: simple aggregate must still ANSWER with high confidence.
# ---------------------------------------------------------------------------

def test_total_revenue_still_answers_high_confidence():
    # Reseed to demo so total_revenue is the demo total.
    import runpy
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.schema_agent import refresh_schema
    runpy.run_path(str(ROOT / "data" / "seed.py"), run_name="__main__")
    reset_engine(); refresh_schema()

    from insightflow.orchestrator import Orchestrator
    o = Orchestrator()
    r = o.ask("What is the total revenue?")
    assert r.decision.action == "ANSWER"
    assert r.confidence.score >= 0.75
    assert r.confidence.signals["intent_coverage"] == 1.0
    assert r.sql.lower().startswith("select sum(revenue")


# ---------------------------------------------------------------------------
# 3) On the demo dataset (no sub_category), draining-cash must CLARIFY
#    naming the missing column — never confidently answer the wrong thing.
# ---------------------------------------------------------------------------

def test_missing_dimension_clarifies_on_demo():
    import runpy
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.schema_agent import refresh_schema
    runpy.run_path(str(ROOT / "data" / "seed.py"), run_name="__main__")
    reset_engine(); refresh_schema()

    from insightflow.orchestrator import Orchestrator
    o = Orchestrator()
    r = o.ask("Which product sub-categories are draining cash "
              "instead of making money")
    assert r.decision.action == "CLARIFY"
    assert "sub_category" in r.explanation
    assert r.confidence.score < 0.5
    # Coverage on the intent as extracted is well below 1.0 because
    # required elements were flagged unavailable.
    assert r.confidence.signals["intent_coverage"] < 0.7


# ---------------------------------------------------------------------------
# 4) Coverage math — call the pure function directly with a mismatched SQL.
# ---------------------------------------------------------------------------

def test_intent_coverage_bare_aggregate_is_one():
    from insightflow.nlsql.generator import QueryIntent, compute_intent_coverage
    intent = QueryIntent()   # empty → bare aggregate
    assert compute_intent_coverage(intent, "SELECT SUM(revenue) FROM orders") == 1.0


def test_intent_coverage_flags_mismatched_sql():
    from insightflow.nlsql.generator import QueryIntent, compute_intent_coverage
    intent = QueryIntent(
        metrics=["profit"],
        dimensions=["sub_category"],
        filters=[{"kind": "metric_lt_zero", "metric": "profit"}],
    )
    # A bare aggregate answers a *different* question → coverage should be
    # low (metric only, no group-by, no HAVING).
    bad = "SELECT SUM(revenue) AS total_revenue FROM orders"
    cov = compute_intent_coverage(intent, bad)
    assert cov < 0.5, cov

    good = (
        "SELECT products.sub_category AS sub_category, "
        "SUM(revenue-cost) AS profit "
        "FROM orders JOIN products ON products.product_id = orders.product_id "
        "GROUP BY products.sub_category HAVING SUM(revenue-cost) < 0"
    )
    cov_good = compute_intent_coverage(intent, good)
    assert cov_good == 1.0, cov_good
