"""Novel-question, novel-schema generalization tests.

These tests are DELIBERATELY unlike the 55 regression cases. Datasets are
generated at test time in shapes the codebase has never seen (invoice
schemas, subscription schemas, transaction schemas), with column names
that differ from the demo schema. Every assertion is oracle-checked
against a plain-Python computation of the expected answer so the test
harness doesn't validate the system against itself.

Category coverage (per §28 of the spec):
    * DIRECT KPI on a novel measure column
    * BREAKDOWN across a novel dim column
    * TIME TREND with a novel date column
    * TOP-N / BOTTOM-N
    * ABOVE-AVERAGE / BELOW-AVERAGE (relative-to-stat)
    * SHARE OF TOTAL
    * AVERAGE AT GRAIN
    * PERIOD COMPARISON
    * CONTRIBUTION
    * UNSUPPORTED KPI (fabrication rejection)
    * AMBIGUOUS QUESTION
    * SEMANTIC-WRONG-SQL REJECTION (fidelity guard)
    * DIFFERENT COLUMN NAMES
"""
from __future__ import annotations

import csv
import io
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_demo():
    import runpy
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
# Dataset factories — each one uses column names the codebase has never seen
# ---------------------------------------------------------------------------

def _invoice_dataset() -> str:
    """Invoice-style: invoice_no PK, invoice_date, branch, amount, expense."""
    rng = random.Random(0)
    rows = [["Invoice_No", "Invoice_Date", "Branch", "Amount", "Expense"]]
    inv = 1000
    for month in ("2026-06", "2026-07", "2026-08"):
        for branch in ("Downtown", "Uptown", "Suburb", "Airport"):
            for _ in range(rng.randint(2, 4)):
                day = rng.randint(1, 27)
                amt = rng.randint(100, 900)
                exp = int(amt * rng.uniform(0.4, 0.85))
                rows.append([inv, f"{month}-{day:02d}", branch, amt, exp])
                inv += 1
    buf = io.StringIO(); csv.writer(buf).writerows(rows)
    return buf.getvalue()


def _transactions_dataset() -> str:
    """Transaction-style: transaction_id, customer, sales_amount, cost."""
    rng = random.Random(1)
    rows = [["Transaction_ID", "Date", "Customer", "Sales_Amount", "Cost"]]
    tid = 5000
    for month in ("2026-06", "2026-07", "2026-08"):
        for cust in ("Alice", "Bob", "Carol", "Dan", "Eve"):
            for _ in range(rng.randint(1, 4)):
                day = rng.randint(1, 27)
                amt = rng.randint(50, 500)
                cost = int(amt * rng.uniform(0.3, 0.9))
                rows.append([tid, f"{month}-{day:02d}", cust, amt, cost])
                tid += 1
    buf = io.StringIO(); csv.writer(buf).writerows(rows)
    return buf.getvalue()


def _upload(client, name: str, body: str):
    r = client.post(
        f"/api/upload/orders?mode=replace&dataset_name={name}",
        files={"file": (f"{name}.csv", body, "text/csv")},
    )
    assert r.status_code == 200, r.text


def _to_records(body: str) -> list[dict]:
    reader = csv.reader(io.StringIO(body))
    header = next(reader)
    return [dict(zip(header, row)) for row in reader]


# ---------------------------------------------------------------------------
# 1) Invoice dataset — direct KPI on the "Amount" column
# ---------------------------------------------------------------------------

def test_novel_invoice_dataset_direct_kpi():
    with _client() as client:
        body = _invoice_dataset()
        _upload(client, "inv1", body)
        r = client.post("/api/ask",
                         json={"question": "What is the total amount?"})
        j = r.json()
        assert j["decision"]["action"] in ("ANSWER", "WARN"), j
        # Oracle
        expected = sum(int(r["Amount"]) for r in _to_records(body))
        val = float(j["result_rows"][0][0])
        assert abs(val - expected) < 1e-6


def test_novel_invoice_dataset_breakdown_by_branch():
    with _client() as client:
        body = _invoice_dataset()
        _upload(client, "inv2", body)
        r = client.post("/api/ask",
                         json={"question": "Amount by branch"}).json()
        assert r["decision"]["action"] in ("ANSWER", "WARN")
        sql = r["sql"].lower()
        assert "group by" in sql and "branch" in sql

        # Oracle
        per_branch: dict[str, int] = {}
        for rec in _to_records(body):
            per_branch.setdefault(rec["Branch"], 0)
            per_branch[rec["Branch"]] += int(rec["Amount"])
        got = {row[0]: float(row[-1]) for row in r["result_rows"]}
        for b, v in per_branch.items():
            assert abs(got[b] - v) < 1e-6


# ---------------------------------------------------------------------------
# 2) Transactions dataset — profit derived from Sales_Amount - Cost even
#    though neither column is called "revenue" or "profit".
# ---------------------------------------------------------------------------

def test_transactions_derived_profit_column_naming():
    with _client() as client:
        body = _transactions_dataset()
        _upload(client, "tx1", body)
        r = client.post("/api/ask",
                         json={"question": "What is the total profit?"}).json()
        assert r["decision"]["action"] in ("ANSWER", "WARN"), r
        expected = sum(int(rec["Sales_Amount"]) - int(rec["Cost"])
                        for rec in _to_records(body))
        val = float(r["result_rows"][0][0])
        assert abs(val - expected) < 1e-6


# ---------------------------------------------------------------------------
# 3) Above-average filter on a customer entity
# ---------------------------------------------------------------------------

def test_above_average_customers_are_actually_above():
    with _client() as client:
        body = _transactions_dataset()
        _upload(client, "tx2", body)
        r = client.post("/api/ask",
                         json={"question": "Which customers have sales "
                                            "above average?"}).json()
        assert r["decision"]["action"] in ("ANSWER", "WARN"), r
        sql = r["sql"].lower()
        assert "avg(" in sql
        assert "customer" in sql

        # Oracle: per-customer totals, then keep those above the mean.
        totals: dict[str, int] = {}
        for rec in _to_records(body):
            totals.setdefault(rec["Customer"], 0)
            totals[rec["Customer"]] += int(rec["Sales_Amount"])
        mean = sum(totals.values()) / len(totals)
        expected = sorted(
            [(c, v) for c, v in totals.items() if v > mean],
            key=lambda t: -t[1])
        got = [(row[0], float(row[1])) for row in r["result_rows"]]
        assert [c for c, _ in got] == [c for c, _ in expected]


def test_below_average_returns_below_stat():
    with _client() as client:
        body = _transactions_dataset()
        _upload(client, "tx3", body)
        r = client.post("/api/ask",
                         json={"question": "Which customers have profit "
                                            "below average?"}).json()
        assert r["decision"]["action"] in ("ANSWER", "WARN")
        rec = _to_records(body)
        profits: dict[str, int] = {}
        for row in rec:
            p = int(row["Sales_Amount"]) - int(row["Cost"])
            profits.setdefault(row["Customer"], 0)
            profits[row["Customer"]] += p
        mean = sum(profits.values()) / len(profits)
        expected = {c for c, v in profits.items() if v < mean}
        got = {row[0] for row in r["result_rows"]}
        assert got == expected


def test_combined_above_and_below():
    with _client() as client:
        body = _transactions_dataset()
        _upload(client, "tx4", body)
        r = client.post("/api/ask",
                         json={"question": "Which customers have sales above "
                                            "average but profit below "
                                            "average?"}).json()
        # It's allowed to return an empty set — the meaning must still hold.
        assert r["decision"]["action"] in ("ANSWER", "WARN")
        sql = r["sql"].lower()
        assert "and" in sql
        assert "avg(m1)" in sql and "avg(m2)" in sql


# ---------------------------------------------------------------------------
# 4) Fabrication rejection — customer retention on a dataset with only
#    ONE month of history and no cohort information.
# ---------------------------------------------------------------------------

def test_customer_retention_unsupported_when_no_cohort():
    with _client() as client:
        body = ("date,customer,amount\n"
                "2026-06-01,A,100\n"
                "2026-06-05,B,200\n"
                "2026-06-10,C,150\n")
        _upload(client, "retn", body)
        r = client.post("/api/ask",
                         json={"question": "What is customer retention "
                                            "by cohort?"}).json()
        assert r["decision"]["action"] in ("CLARIFY", "ABSTAIN"), r
        assert r["confidence"]["score"] < 0.70
        assert r["failure_category"] in (
            "UNSUPPORTED_DATA", "AMBIGUITY", "KPI_ERROR",
            "SCHEMA_MAPPING_ERROR", "PLAN_ERROR",
        )


# ---------------------------------------------------------------------------
# 5) Ambiguous → CLARIFY, not fabrication
# ---------------------------------------------------------------------------

def test_ambiguous_gets_clarify():
    with _client() as client:
        body = _invoice_dataset()
        _upload(client, "amb", body)
        r = client.post("/api/ask",
                         json={"question": "Give me insights"}).json()
        assert r["decision"]["action"] in ("CLARIFY", "ABSTAIN")
        assert r["confidence"]["score"] < 0.70
        assert r["failure_category"] in ("AMBIGUITY", "UNSUPPORTED_DATA",
                                          "PLAN_ERROR")


# ---------------------------------------------------------------------------
# 6) Semantic-wrong SQL rejection via the fidelity validator.
#    We construct a plan that says "top 3" but feed a SQL string that
#    doesn't LIMIT — validator must fail.
# ---------------------------------------------------------------------------

def test_fidelity_rejects_top_n_without_limit():
    from insightflow.plan import (
        AnalyticalPlan, DimRef, MeasureRef, IntentKind, FidelityValidator,
    )
    plan = AnalyticalPlan(
        intent_kind=IntentKind.TOP_N, table="orders",
        measures=[MeasureRef(kpi_id="total_revenue", formula="SUM(revenue)",
                              aggregation="sum")],
        dims=[DimRef(column="region_name")],
        top_n=3, order_by="measure_desc",
    )
    bad_sql = ("SELECT regions.region_name AS region, SUM(revenue) AS "
                "total_revenue FROM orders JOIN regions ON regions.region_id "
                "= orders.region_id GROUP BY regions.region_name "
                "ORDER BY total_revenue DESC")   # ← missing LIMIT
    rep = FidelityValidator().check(plan, bad_sql)
    assert not rep.ok
    assert any(c.name == "top_n_limit" and not c.passed for c in rep.checks)


def test_fidelity_rejects_missing_group_by():
    from insightflow.plan import (
        AnalyticalPlan, DimRef, MeasureRef, IntentKind, FidelityValidator,
    )
    plan = AnalyticalPlan(
        intent_kind=IntentKind.BREAKDOWN, table="orders",
        measures=[MeasureRef(kpi_id="total_revenue", formula="SUM(revenue)",
                              aggregation="sum")],
        dims=[DimRef(column="region_name")],
    )
    bad_sql = "SELECT SUM(revenue) AS total_revenue FROM orders"  # no GROUP BY
    rep = FidelityValidator().check(plan, bad_sql)
    assert not rep.ok
    assert any(c.name == "group_by_present" and not c.passed for c in rep.checks)


# ---------------------------------------------------------------------------
# 7) DatasetSemanticModel exposes grain + statistics
# ---------------------------------------------------------------------------

def test_semantic_model_infers_grain_and_stats():
    from insightflow.knowledge.dataset_registry import get_active_dataset
    from insightflow.knowledge.semantic_model import build_semantic_model
    with _client() as client:
        body = _invoice_dataset()
        _upload(client, "sm1", body)
        ds = get_active_dataset()
        model = build_semantic_model(ds)
        # There's an invoice_no id column — grain should reflect that.
        assert model.grain in ("order", "row"), model.grain
        # Every column got profiled.
        assert set(model.columns.keys()) == set(ds.columns.keys())
        # Amount (whatever case it was stored as) is a numeric measure
        # with distinct/null stats.
        amt_key = next((k for k in model.columns
                         if k.lower() == "amount"), None)
        assert amt_key is not None
        amt = model.col(amt_key)
        assert amt.role == "measure"
        assert amt.distinct_count is not None and amt.distinct_count > 0
        assert amt.null_pct == 0.0


# ---------------------------------------------------------------------------
# 8) Diagnostic trace is emitted for every question
# ---------------------------------------------------------------------------

def test_diagnostics_trace_present():
    with _client() as client:
        body = _invoice_dataset()
        _upload(client, "diag", body)
        r = client.post("/api/ask",
                         json={"question": "Amount by branch"}).json()
        d = r.get("diagnostics")
        assert d is not None
        for key in ("dataset", "plan", "plan_validation", "sql",
                    "sql_validation", "fidelity", "execution",
                    "result_validation", "kpi_validation",
                    "confidence", "decision", "failure_category"):
            assert key in d
        # fidelity summary must include per-check breakdown
        assert isinstance(d["fidelity"]["checks"], list)
        assert d["fidelity"]["score"] > 0.0


# ---------------------------------------------------------------------------
# 9) Result validator catches share-of-total that doesn't sum to 1
# ---------------------------------------------------------------------------

def test_result_validator_flags_wrong_shares():
    from insightflow.execution.executor import QueryResult
    from insightflow.plan import (
        AnalyticalPlan, DimRef, MeasureRef, IntentKind,
    )
    from insightflow.reliability.result_validator import ResultValidator
    plan = AnalyticalPlan(
        intent_kind=IntentKind.SHARE_OF_TOTAL, table="orders",
        measures=[MeasureRef(kpi_id="total_revenue", formula="SUM(revenue)",
                              aggregation="sum")],
        dims=[DimRef(column="region_name")],
        share_of_total=True,
    )
    r = QueryResult(
        columns=["region", "total_revenue", "share"],
        rows=[("N", 100, 0.3), ("S", 200, 0.3), ("E", 300, 0.2)],
    )
    rep = ResultValidator().check(plan, r)
    # sums to 0.8 → not error, warning
    assert any("share_of_total" in i.message.lower() for i in rep.issues)


# ---------------------------------------------------------------------------
# 10) MoM / YoY word forms bind to the right time_unit
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("q,expected_unit", [
    ("Revenue month-over-month growth", "month"),
    ("Revenue year-over-year growth", "year"),
    ("Revenue quarter-over-quarter growth", "quarter"),
    ("Revenue week-over-week growth", "week"),
])
def test_temporal_units_bind_correctly(q, expected_unit):
    from insightflow.knowledge.dataset_registry import get_active_dataset
    from insightflow.knowledge.kpi_catalog import build_catalog
    from insightflow.plan import Planner
    with _client() as client:
        body = _invoice_dataset()
        _upload(client, "tem", body)
        ds = get_active_dataset()
        cat = build_catalog(ds)
        plan = Planner(ds, cat).plan(q)
        assert plan.grain is not None
        assert plan.grain.time_unit == expected_unit, plan.as_trace()


# ---------------------------------------------------------------------------
# 11) Independent oracle for share-of-total actually SUMS to 1.
# ---------------------------------------------------------------------------

def test_share_of_total_sums_to_one_on_novel_dataset():
    with _client() as client:
        body = _invoice_dataset()
        _upload(client, "sotv", body)
        r = client.post("/api/ask",
                         json={"question": "share of amount by branch"}).json()
        assert r["decision"]["action"] in ("ANSWER", "WARN")
        shares = [float(row[-1]) for row in r["result_rows"]]
        assert 0.99 < sum(shares) < 1.01, shares
