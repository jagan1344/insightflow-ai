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


def test_dashboard_payload_shape():
    """/api/dashboard returns the four KPI keys and the four series."""
    from api.routes_dashboard import build_dashboard
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.schema_agent import refresh_schema
    reset_engine()
    refresh_schema()
    payload = build_dashboard(version=99)
    assert payload["version"] == 99
    for k in ("total_revenue", "order_count", "avg_order_value", "gross_margin"):
        assert k in payload["kpis"]
        for f in ("value", "unit", "delta_pct"):
            assert f in payload["kpis"][k]
    assert len(payload["revenue_by_month"]) >= 9
    assert payload["revenue_by_region"], "expected regions"
    assert payload["revenue_by_category"], "expected categories"
    assert payload["margin_by_category"], "expected margin series"
    # margins in [0,1]
    for r in payload["margin_by_category"]:
        assert 0.0 <= float(r["value"]) <= 1.0


def test_ask_endpoint_via_fastapi():
    """POST /api/ask returns a well-formed answer."""
    from fastapi.testclient import TestClient
    from api.main import app
    with TestClient(app) as client:
        r = client.post("/api/ask", json={"question": "What is the total revenue?"})
        assert r.status_code == 200
        body = r.json()
        assert body["decision"]["action"] == "ANSWER"
        assert body["confidence"]["score"] >= 0.7
        assert body["sql"].strip().lower().startswith("select")


def test_upload_orders_csv_replaces_table():
    """POST /api/upload/orders replaces the orders table from a CSV and
    triggers the change signature so a dashboard broadcast will fire."""
    from fastapi.testclient import TestClient
    from api.main import app
    from insightflow.execution.executor import get_engine, reset_engine, run_sql
    from insightflow.knowledge.schema_agent import refresh_schema
    from sqlalchemy import text

    csv_body = (
        "order_date,region,category,product,customer,segment,"
        "quantity,revenue,cost,discount\n"
        "2026-03-10,North,Electronics,Widget,Acme,Enterprise,2,1200,800,25\n"
        "2026-03-11,South,Furniture,Chair,Zeta,SMB,1,450,290,0\n"
    )

    # snapshot original count so we can restore
    orig = run_sql("SELECT COUNT(*) FROM orders").rows[0][0]
    assert orig > 0
    try:
        with TestClient(app) as client:
            r = client.post(
                "/api/upload/orders?mode=replace",
                files={"file": ("upload.csv", csv_body, "text/csv")},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["ok"] is True
            assert body["rows_inserted"] == 2
            assert body["mode"] == "replace"

            # 2 rows must be in the DB now
            n = run_sql("SELECT COUNT(*) FROM orders").rows[0][0]
            assert n == 2

            # Dims upserted
            assert body["dims_upserted"]["customers"] >= 1

            # append mode adds rows without deleting
            r = client.post(
                "/api/upload/orders?mode=append",
                files={"file": ("upload.csv", csv_body, "text/csv")},
            )
            assert r.status_code == 200
            n2 = run_sql("SELECT COUNT(*) FROM orders").rows[0][0]
            assert n2 == 4

            # Invalid CSV (no revenue column) is rejected 400
            r = client.post(
                "/api/upload/orders",
                files={"file": ("bad.csv", "foo,bar\n1,2\n", "text/csv")},
            )
            assert r.status_code == 400

            # .xlsx round-trip: build an in-memory workbook with Superstore-style
            # headers (Sales, Order Date, Customer Name, Product Name, Region,
            # Sub-Category, Segment, Quantity, Profit, Discount) and upload it.
            import io
            from openpyxl import Workbook
            wb = Workbook()
            ws = wb.active
            ws.append(["Order Date", "Region", "Sub-Category", "Product Name",
                       "Customer Name", "Segment", "Quantity", "Sales",
                       "Profit", "Discount"])
            ws.append(["2026-04-01", "West", "Chairs", "Office Chair",
                       "Alice Kim", "Consumer", 2, 300.0, 60.0, 0.0])
            ws.append(["2026-04-02", "East", "Binders", "Ring Binder",
                       "Bob Lee", "SMB", 5, 45.0, 15.0, 0.1])
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)
            r = client.post(
                "/api/upload/orders?mode=replace",
                files={"file": ("superstore.xlsx", buf.read(),
                                "application/vnd.openxmlformats-officedocument"
                                ".spreadsheetml.sheet")},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["ok"] is True
            assert body["rows_inserted"] == 2

            # cost should have been derived from profit (300 - 60 = 240,
            # 45 - 15 = 30). Verify from the DB.
            costs = [row[0] for row in run_sql(
                "SELECT cost FROM orders ORDER BY revenue DESC").rows]
            assert costs == [240.0, 30.0], costs

            # Sub-Category should have filled the category column
            cats = [row[0] for row in run_sql(
                "SELECT DISTINCT category FROM products "
                "WHERE product_name IN ('Office Chair','Ring Binder')").rows]
            assert set(cats) == {"Chairs", "Binders"}, cats

            # Wrong file extension rejected
            r = client.post(
                "/api/upload/orders",
                files={"file": ("notes.docx", b"garbage",
                                "application/octet-stream")},
            )
            assert r.status_code == 400
    finally:
        # Restore demo dataset for other tests
        import runpy
        from pathlib import Path
        runpy.run_path(str(Path(__file__).resolve().parent.parent / "data" / "seed.py"),
                       run_name="__main__")
        reset_engine(); refresh_schema()


def test_realtime_watcher_broadcasts_on_change():
    """A change to orders triggers a dashboard_update via the watcher."""
    import asyncio
    from api import realtime
    from insightflow.execution.executor import get_engine
    from sqlalchemy import text

    received: list[dict] = []

    class _FakeWS:
        async def send_json(self, payload):
            received.append(payload)

    async def scenario():
        fake = _FakeWS()
        await realtime.register(fake)  # type: ignore[arg-type]
        # short-poll watcher
        watcher = asyncio.create_task(realtime.watcher_loop(poll_seconds=0.1))
        try:
            # Give watcher a tick to prime signature
            await asyncio.sleep(0.3)
            engine = get_engine()
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO orders(customer_id, product_id, region_id, "
                    "order_date, quantity, revenue, cost, discount) "
                    "VALUES (1, 1, 1, '2026-09-30', 1, 500.00, 350.00, 5.00)"
                ))
            # allow watcher to detect and broadcast
            for _ in range(30):
                if any(m.get("type") == "dashboard_update" for m in received):
                    break
                await asyncio.sleep(0.1)
        finally:
            watcher.cancel()
            await realtime.unregister(fake)  # type: ignore[arg-type]

    asyncio.run(scenario())
    updates = [m for m in received if m.get("type") == "dashboard_update"]
    assert updates, "expected a dashboard_update broadcast after insert"
    # version must be positive
    assert updates[-1]["version"] > 0
