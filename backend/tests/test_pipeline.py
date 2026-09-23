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


def test_upload_orders_csv_creates_new_active_dataset():
    """POST /api/upload/orders now stores each upload as its OWN table
    (dataset_<slug>) and registers it as the active dataset. The demo
    orders table is left untouched. This is the fixed-behaviour test —
    the previous version verified the buggy 'shoehorn into orders' path.
    """
    from fastapi.testclient import TestClient
    from api.main import app
    from insightflow.execution.executor import reset_engine, run_sql
    from insightflow.knowledge.schema_agent import refresh_schema
    from insightflow.knowledge.dataset_registry import (
        set_active, DEMO_ID, get_active_dataset,
    )

    csv_body = (
        "order_date,region,category,product,customer,segment,"
        "quantity,revenue,cost,discount\n"
        "2026-03-10,North,Electronics,Widget,Acme,Enterprise,2,1200,800,25\n"
        "2026-03-11,South,Furniture,Chair,Zeta,SMB,1,450,290,0\n"
    )

    orig_orders = run_sql("SELECT COUNT(*) FROM orders").rows[0][0]
    assert orig_orders > 0
    try:
        with TestClient(app) as client:
            r = client.post(
                "/api/upload/orders?mode=replace&dataset_name=upload_a",
                files={"file": ("upload_a.csv", csv_body, "text/csv")},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["ok"] is True
            assert body["rows_inserted"] == 2
            assert body["dataset_name"] == "upload_a"
            assert body["table_name"].startswith("dataset_")
            assert body["is_active"] is True

            # Demo table left untouched
            n = run_sql("SELECT COUNT(*) FROM orders").rows[0][0]
            assert n == orig_orders

            # Uploaded rows landed in the new table
            table = body["table_name"]
            up_n = run_sql(f'SELECT COUNT(*) FROM "{table}"').rows[0][0]
            assert up_n == 2

            # Active dataset is the new one
            active = get_active_dataset()
            assert active.kind == "uploaded"
            assert active.table == table

            # Second upload creates a SECOND dataset and switches to it
            csv_body_b = (
                "date,department,orders,amount,profit\n"
                "2026-06-01,North,10,1000,200\n"
                "2026-07-01,North,8,800,100\n"
            )
            r = client.post(
                "/api/upload/orders?mode=replace&dataset_name=upload_b",
                files={"file": ("upload_b.csv", csv_body_b, "text/csv")},
            )
            assert r.status_code == 200
            b2 = r.json()
            assert b2["dataset_name"] == "upload_b"
            assert b2["table_name"] != body["table_name"]
            active = get_active_dataset()
            assert active.name == "upload_b"

            # Datasets endpoint lists both plus demo
            r = client.get("/api/datasets")
            assert r.status_code == 200
            names = [d["name"] for d in r.json()]
            assert "upload_a" in names
            assert "upload_b" in names
            assert "Demo sales" in names

            # Reactivate demo via the API
            r = client.post("/api/datasets/activate/demo")
            assert r.status_code == 200
            assert get_active_dataset().kind == "demo"

            # Bad CSV rejected
            r = client.post(
                "/api/upload/orders",
                files={"file": ("bad.csv", "\n", "text/csv")},
            )
            assert r.status_code == 400

            # Wrong extension rejected
            r = client.post(
                "/api/upload/orders",
                files={"file": ("notes.docx", b"garbage",
                                "application/octet-stream")},
            )
            assert r.status_code == 400
    finally:
        # Restore demo as active for downstream tests
        import runpy
        from pathlib import Path
        runpy.run_path(str(Path(__file__).resolve().parent.parent / "data" / "seed.py"),
                       run_name="__main__")
        reset_engine(); refresh_schema()
        set_active(DEMO_ID)


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
