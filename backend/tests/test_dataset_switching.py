"""End-to-end acceptance tests for the upload / active-dataset fix.

The two failures the user reported were:

  (a) "uploading is not working correctly" — after upload the demo data
      kept being queried.
  (b) "NL-to-SQL sometimes appears to be regenerated, static, demo-based,
      or disconnected from the actual user question and uploaded dataset."

These tests are the "prove it" step: upload two DIFFERENT small datasets
with the SAME schema shape but MATERIALLY DIFFERENT values, ask the same
question, and check that the returned answers DIFFER. If the answer is
identical, the pipeline still queries something else (bug).
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _seed_and_restore():
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.schema_agent import refresh_schema
    from insightflow.knowledge.dataset_registry import set_active, DEMO_ID
    runpy.run_path(str(ROOT / "data" / "seed.py"), run_name="__main__")
    reset_engine(); refresh_schema()
    set_active(DEMO_ID)
    yield
    runpy.run_path(str(ROOT / "data" / "seed.py"), run_name="__main__")
    reset_engine(); refresh_schema()
    set_active(DEMO_ID)


# ---------------------------------------------------------------------------
# Two arbitrary CSV shapes — deliberately NOT Superstore-shaped, so we
# can't accidentally succeed by shoehorning into the demo schema.
# ---------------------------------------------------------------------------

DATASET_A = (
    "date,product,orders,amount,profit\n"
    "2026-06-01,A,10,1000,200\n"
    "2026-07-01,A,8,800,100\n"
    "2026-08-01,A,12,1200,240\n"
    "2026-06-01,B,5,500,50\n"
)

# Same column names, MUCH bigger numbers.
DATASET_B = (
    "date,product,orders,amount,profit\n"
    "2026-06-01,A,50,5000,2000\n"
    "2026-07-01,A,45,4500,1800\n"
    "2026-08-01,A,60,6000,2400\n"
    "2026-06-01,B,25,2500,500\n"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def _headline(rr: dict) -> float | None:
    """Pull a scalar answer value from an /api/ask response body. Uses the
    first numeric cell of the returned rows."""
    for row in rr.get("result_rows", []):
        for v in row:
            if isinstance(v, (int, float)):
                return float(v)
    # Fallback to parsing the explanation
    import re
    m = re.search(r"(-?\d[\d,]*\.\d+|-?\d[\d,]*)", rr.get("explanation") or "")
    if m:
        return float(m.group(1).replace(",", ""))
    return None


# ---------------------------------------------------------------------------
# 1) Upload A → question uses A's data
# ---------------------------------------------------------------------------

def test_upload_A_then_same_question_uses_A():
    with _client() as client:
        r = client.post(
            "/api/upload/orders?mode=replace&dataset_name=A",
            files={"file": ("A.csv", DATASET_A, "text/csv")},
        )
        assert r.status_code == 200
        # Sanity: active is A, table starts with dataset_
        active = client.get("/api/datasets/active").json()
        assert active["kind"] == "uploaded"
        assert "dataset_" in active["table"]

        # Ask: total amount → SQL must query the uploaded table, not orders
        r = client.post("/api/ask",
                        json={"question": "What is the total revenue?"})
        body = r.json()
        assert body["decision"]["action"] in ("ANSWER", "WARN"), body
        sql = body["sql"].lower()
        assert "dataset_" in sql, f"expected uploaded table in SQL: {sql!r}"
        # Value must equal SUM(amount) in dataset A = 1000+800+1200+500 = 3500
        val = _headline(body)
        assert val is not None
        assert abs(val - 3500.0) < 1e-6, (val, body)


# ---------------------------------------------------------------------------
# 2) SAME question against A vs B must return DIFFERENT answers.
#    This is the anti-"static demo results" acceptance test.
# ---------------------------------------------------------------------------

def test_same_question_different_datasets_yield_different_answers():
    with _client() as client:
        client.post(
            "/api/upload/orders?mode=replace&dataset_name=A",
            files={"file": ("A.csv", DATASET_A, "text/csv")},
        )
        q = "What is the total revenue?"
        rr_a = client.post("/api/ask", json={"question": q}).json()
        val_a = _headline(rr_a)
        assert rr_a["decision"]["action"] in ("ANSWER", "WARN")

        client.post(
            "/api/upload/orders?mode=replace&dataset_name=B",
            files={"file": ("B.csv", DATASET_B, "text/csv")},
        )
        rr_b = client.post("/api/ask", json={"question": q}).json()
        val_b = _headline(rr_b)
        assert rr_b["decision"]["action"] in ("ANSWER", "WARN")

        # Different numbers: A = 3500, B = 18000
        assert val_a is not None and val_b is not None
        assert abs(val_a - val_b) > 1.0, (
            f"same answer {val_a} vs {val_b} — pipeline is not using the "
            f"active dataset")
        assert abs(val_a - 3500.0) < 1e-6, val_a
        assert abs(val_b - 18000.0) < 1e-6, val_b

        # And the SQL text has to reference DIFFERENT tables.
        sql_a = rr_a["sql"].lower()
        sql_b = rr_b["sql"].lower()
        # Both hit dataset_ tables
        assert "dataset_" in sql_a and "dataset_" in sql_b
        # And they are DIFFERENT tables (different slugs)
        import re
        m_a = re.search(r'"(dataset_[a-z0-9_]+)"', rr_a["sql"])
        m_b = re.search(r'"(dataset_[a-z0-9_]+)"', rr_b["sql"])
        assert m_a and m_b and m_a.group(1) != m_b.group(1), (
            m_a and m_a.group(1), m_b and m_b.group(1))


# ---------------------------------------------------------------------------
# 3) Different questions against the same dataset must produce
#    semantically different SQL — not just different NL text.
# ---------------------------------------------------------------------------

def test_different_questions_same_dataset_produce_different_sql():
    with _client() as client:
        client.post(
            "/api/upload/orders?mode=replace&dataset_name=A",
            files={"file": ("A.csv", DATASET_A, "text/csv")},
        )

        q1 = "What is the total number of orders?"
        q2 = "What is the average order value?"
        q3 = "Which month recorded the highest revenue?"
        r1 = client.post("/api/ask", json={"question": q1}).json()
        r2 = client.post("/api/ask", json={"question": q2}).json()
        r3 = client.post("/api/ask", json={"question": q3}).json()

        s1, s2, s3 = r1["sql"].lower(), r2["sql"].lower(), r3["sql"].lower()
        assert s1 != s2 != s3, (s1, s2, s3)
        # order count → COUNT(*)
        assert "count(*" in s1
        # AOV → SUM(...)/COUNT(*)
        assert "* 1.0 / count(*)" in s2 or "*1.0/count(*)" in s2 \
               or "count(*)" in s2 and "sum(" in s2
        # by month → GROUP BY substr(date,1,7)
        assert "group by" in s3 and "substr" in s3


# ---------------------------------------------------------------------------
# 4) Reactivating demo restores the demo data flow (no leftover state).
# ---------------------------------------------------------------------------

def test_reseed_reactivates_demo():
    with _client() as client:
        client.post(
            "/api/upload/orders?mode=replace&dataset_name=A",
            files={"file": ("A.csv", DATASET_A, "text/csv")},
        )
        assert client.get("/api/datasets/active").json()["kind"] == "uploaded"

        r = client.post("/api/seed")
        assert r.status_code == 200
        assert "reseeded" in r.json()["detail"]
        assert client.get("/api/datasets/active").json()["kind"] == "demo"

        # Total revenue on demo — should match the demo total, not A's.
        rr = client.post("/api/ask",
                         json={"question": "What is the total revenue?"}).json()
        val = _headline(rr)
        assert val is not None
        # Demo total is ~3.4M
        assert val > 1_000_000, val
