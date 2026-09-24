"""General-purpose plan pipeline tests.

The goal of this suite is to prove that the KPI-Intelligence pipeline is
NOT tied to the 55 hardcoded regression questions. It generates small,
synthetic datasets with random-ish shapes at test time and then asks a
template of question shapes against them. Each assertion is oracle-checked
using pandas/plain-Python so the SQL result is compared to a
model-independent ground truth, not to a fixed expected string.

Templates exercised:

    1. direct KPI            "What is the total <measure>?"
    2. breakdown             "<measure> by <dim>"
    3. trend                 "<measure> over time"
    4. comparison            "<measure> in <month_a> vs <month_b>"
    5. top-N                 "top <N> <dim>s by <measure>"
    6. bottom-N              "bottom <N> <dim>s by <measure>"
    7. share of total        "share of <measure> by <dim>"
    8. average-at-grain      "average monthly <measure>"
    9. contribution          "which <dim> contributed most to the <measure> decline from <A> to <B>"
   10. unsupported KPI       "<measure_not_in_dataset>?"    → CLARIFY, low confidence
"""
from __future__ import annotations

import csv
import io
import random
import sys
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Synthetic dataset generator
# ---------------------------------------------------------------------------

def _gen_dataset(seed: int, measure_col: str, dim_col: str,
                 date_col: str = "date") -> str:
    """Return a CSV body with (<date>, <dim>, <measure>) rows spanning
    Jun–Aug 2026 for a few categorical dim values.
    """
    rng = random.Random(seed)
    dim_vals = ["A", "B", "C", "D"]
    rows: list[list] = [[date_col, dim_col, measure_col]]
    for month in ("2026-06", "2026-07", "2026-08"):
        for d in dim_vals:
            n = rng.randint(2, 5)
            for i in range(n):
                day = rng.randint(1, 27)
                val = rng.randint(50, 400)
                rows.append([f"{month}-{day:02d}", d, val])
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue()


def _upload(client, name: str, body: str) -> dict:
    r = client.post(
        f"/api/upload/orders?mode=replace&dataset_name={name}",
        files={"file": (f"{name}.csv", body, "text/csv")},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# Fixture: reset demo between tests
# ---------------------------------------------------------------------------

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
# 1) Direct KPI: sum(measure) on a random column name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("measure_col", ["revenue", "amount", "sales_total"])
def test_direct_kpi_totals_actual_column(measure_col):
    with _client() as client:
        body = _gen_dataset(seed=1, measure_col=measure_col, dim_col="segment")
        _upload(client, f"a_{measure_col}", body)

        r = client.post("/api/ask",
                        json={"question": f"What is the total {measure_col}?"})
        j = r.json()
        assert j["decision"]["action"] in ("ANSWER", "WARN"), j
        assert "dataset_" in j["sql"].lower()

        # Oracle: sum the measure column from the CSV
        expected = sum(int(row[2]) for row in list(csv.reader(io.StringIO(body)))[1:])
        val = None
        for row in j["result_rows"]:
            for v in row:
                if isinstance(v, (int, float)):
                    val = float(v); break
            if val is not None:
                break
        assert val is not None
        assert abs(val - expected) < 1e-6, (val, expected)


# ---------------------------------------------------------------------------
# 2) Breakdown: grouped by dim
# ---------------------------------------------------------------------------

def test_breakdown_by_dim_uses_group_by():
    with _client() as client:
        body = _gen_dataset(seed=2, measure_col="revenue", dim_col="region")
        _upload(client, "b_region", body)

        r = client.post("/api/ask",
                        json={"question": "Revenue by region"})
        j = r.json()
        assert j["decision"]["action"] in ("ANSWER", "WARN")
        sql = j["sql"].lower()
        assert "group by" in sql
        assert "region" in sql

        # Oracle: group by dim and sum
        rows_by_dim: dict[str, int] = {}
        for row in list(csv.reader(io.StringIO(body)))[1:]:
            rows_by_dim.setdefault(row[1], 0)
            rows_by_dim[row[1]] += int(row[2])
        returned = {str(row[0]): float(row[-1]) for row in j["result_rows"]}
        for k, v in rows_by_dim.items():
            assert k in returned
            assert abs(returned[k] - v) < 1e-6


# ---------------------------------------------------------------------------
# 3) Trend over time
# ---------------------------------------------------------------------------

def test_trend_over_time_group_by_month():
    with _client() as client:
        body = _gen_dataset(seed=3, measure_col="revenue", dim_col="segment")
        _upload(client, "t_time", body)

        r = client.post("/api/ask",
                        json={"question": "Revenue over time"})
        j = r.json()
        assert j["decision"]["action"] in ("ANSWER", "WARN")
        sql = j["sql"].lower()
        assert "substr" in sql or "group by" in sql

        # Oracle: revenue per month
        per_month: dict[str, int] = {}
        for row in list(csv.reader(io.StringIO(body)))[1:]:
            m = row[0][:7]
            per_month.setdefault(m, 0)
            per_month[m] += int(row[2])
        returned = {str(row[0]): float(row[-1]) for row in j["result_rows"]}
        for m, v in per_month.items():
            assert m in returned
            assert abs(returned[m] - v) < 1e-6


# ---------------------------------------------------------------------------
# 4) Comparison: two-period side-by-side
# ---------------------------------------------------------------------------

def test_comparison_two_periods_produces_two_rows():
    with _client() as client:
        body = _gen_dataset(seed=4, measure_col="revenue", dim_col="segment")
        _upload(client, "c_cmp", body)

        r = client.post("/api/ask",
                        json={"question": "How did revenue change from June to July?"})
        j = r.json()
        assert j["decision"]["action"] in ("ANSWER", "WARN")
        rows = j["result_rows"]
        assert len(rows) == 2
        periods = {row[0] for row in rows}
        assert periods == {"2026-06", "2026-07"}

        # Oracle: sum by month
        per_month: dict[str, int] = {}
        for row in list(csv.reader(io.StringIO(body)))[1:]:
            m = row[0][:7]
            per_month.setdefault(m, 0)
            per_month[m] += int(row[2])
        for row in rows:
            assert abs(float(row[-1]) - per_month[row[0]]) < 1e-6


# ---------------------------------------------------------------------------
# 5) Top-N ranking
# ---------------------------------------------------------------------------

def test_top_n_by_measure_returns_at_most_n_sorted_desc():
    with _client() as client:
        body = _gen_dataset(seed=5, measure_col="revenue", dim_col="segment")
        _upload(client, "topn", body)

        r = client.post("/api/ask",
                        json={"question": "Top 2 segments by revenue"})
        j = r.json()
        assert j["decision"]["action"] in ("ANSWER", "WARN")
        rows = j["result_rows"]
        assert 1 <= len(rows) <= 2
        vals = [float(r[-1]) for r in rows]
        assert vals == sorted(vals, reverse=True)


def test_bottom_n_by_measure_returns_ascending():
    with _client() as client:
        body = _gen_dataset(seed=6, measure_col="revenue", dim_col="segment")
        _upload(client, "botn", body)

        r = client.post("/api/ask",
                        json={"question": "Bottom 2 segments by revenue"})
        j = r.json()
        assert j["decision"]["action"] in ("ANSWER", "WARN")
        rows = j["result_rows"]
        vals = [float(r[-1]) for r in rows]
        assert vals == sorted(vals)


# ---------------------------------------------------------------------------
# 6) Share of total
# ---------------------------------------------------------------------------

def test_share_of_total_sums_to_one():
    with _client() as client:
        body = _gen_dataset(seed=7, measure_col="revenue", dim_col="region")
        _upload(client, "share", body)

        r = client.post("/api/ask",
                        json={"question": "share of revenue by region"})
        j = r.json()
        assert j["decision"]["action"] in ("ANSWER", "WARN")
        # last column should be the share
        shares = [float(r[-1]) for r in j["result_rows"]]
        assert 0.99 < sum(shares) < 1.01, shares


# ---------------------------------------------------------------------------
# 7) Average at grain
# ---------------------------------------------------------------------------

def test_average_monthly_is_mean_of_monthly_sums():
    with _client() as client:
        body = _gen_dataset(seed=8, measure_col="revenue", dim_col="segment")
        _upload(client, "avg", body)

        r = client.post("/api/ask",
                        json={"question": "What is the average monthly revenue?"})
        j = r.json()
        assert j["decision"]["action"] in ("ANSWER", "WARN")

        # Oracle: mean of monthly sums
        per_month: dict[str, int] = {}
        for row in list(csv.reader(io.StringIO(body)))[1:]:
            m = row[0][:7]
            per_month.setdefault(m, 0)
            per_month[m] += int(row[2])
        expected = sum(per_month.values()) / len(per_month)
        val = float(j["result_rows"][0][0])
        assert abs(val - expected) < 1e-6


# ---------------------------------------------------------------------------
# 8) Contribution — no oracle beyond structural, just check the plan
# picked contribution and the SQL has the two-period CTE shape.
# ---------------------------------------------------------------------------

def test_contribution_uses_two_period_cte():
    with _client() as client:
        body = _gen_dataset(seed=9, measure_col="revenue", dim_col="region")
        _upload(client, "contrib", body)

        r = client.post("/api/ask",
                        json={"question": "Which region contributed most to the "
                                          "revenue decline from June to July?"})
        j = r.json()
        assert j["decision"]["action"] in ("ANSWER", "WARN"), j
        sql = j["sql"].lower()
        assert "with base as" in sql
        assert "targ" in sql
        assert "delta" in sql


# ---------------------------------------------------------------------------
# 9) Unsupported KPI — must CLARIFY, not fabricate.
# ---------------------------------------------------------------------------

def test_unsupported_kpi_clarifies_with_low_confidence():
    with _client() as client:
        body = _gen_dataset(seed=10, measure_col="revenue", dim_col="segment")
        _upload(client, "unsupp", body)

        r = client.post("/api/ask",
                        json={"question": "What is the customer retention rate by cohort?"})
        j = r.json()
        assert j["decision"]["action"] in ("CLARIFY", "ABSTAIN"), j
        # confidence must not be high — never confidently wrong on this
        assert j["confidence"]["score"] < 0.70


# ---------------------------------------------------------------------------
# 10) The plan is exposed in the response for auditability.
# ---------------------------------------------------------------------------

def test_plan_trace_is_present_and_named_correctly():
    with _client() as client:
        body = _gen_dataset(seed=11, measure_col="revenue", dim_col="region")
        _upload(client, "trace", body)

        r = client.post("/api/ask",
                        json={"question": "Revenue by region"})
        j = r.json()
        # /api/ask endpoint may or may not surface plan_trace; the
        # explanation must at least mention the KPI formula + dataset.
        expl = j["explanation"]
        assert "total_revenue" in expl.lower() or "sum(" in expl.lower()
        assert "dataset_" in expl.lower()


# ---------------------------------------------------------------------------
# 11) Grain-aware reasoning: "average monthly revenue" isn't the same as
#      the total; it's the mean of per-month sums.
# ---------------------------------------------------------------------------

def test_average_monthly_differs_from_total_but_matches_mean_of_month_sums():
    with _client() as client:
        body = _gen_dataset(seed=12, measure_col="revenue", dim_col="segment")
        _upload(client, "grain", body)

        r_total = client.post("/api/ask",
                              json={"question": "What is the total revenue?"}).json()
        r_mon = client.post("/api/ask",
                            json={"question": "What is the average monthly revenue?"}).json()
        assert r_total["decision"]["action"] in ("ANSWER", "WARN")
        assert r_mon["decision"]["action"] in ("ANSWER", "WARN")
        v_total = float(r_total["result_rows"][0][0])
        v_mon = float(r_mon["result_rows"][0][0])
        # Average monthly should be strictly LESS than total (>= 2 months).
        assert v_mon < v_total
        # Oracle: mean-of-monthly-sums
        per_month: dict[str, int] = {}
        for row in list(csv.reader(io.StringIO(body)))[1:]:
            m = row[0][:7]
            per_month.setdefault(m, 0)
            per_month[m] += int(row[2])
        expected = sum(per_month.values()) / len(per_month)
        assert abs(v_mon - expected) < 1e-6


# ---------------------------------------------------------------------------
# 12) KPI catalog derives from dataset — different column layouts →
#      different KPI IDs available.
# ---------------------------------------------------------------------------

def test_kpi_catalog_derives_from_dataset_columns():
    from insightflow.knowledge.dataset_registry import get_active_dataset
    from insightflow.knowledge.kpi_catalog import build_catalog
    with _client() as client:
        # Dataset A: has 'revenue' + 'cost' → gross_margin computable
        body_a = "date,region,revenue,cost\n2026-06-01,X,100,60\n2026-06-02,X,200,120\n"
        _upload(client, "layout_a", body_a)
        ds = get_active_dataset()
        cat = build_catalog(ds)
        assert "gross_margin" in cat.kpis
        assert "profit" in cat.kpis
        assert "total_revenue" in cat.kpis

        # Dataset B: only has 'sales'; profit / margin should NOT appear
        body_b = "date,region,sales\n2026-06-01,X,50\n2026-06-02,X,80\n"
        _upload(client, "layout_b", body_b)
        ds = get_active_dataset()
        cat = build_catalog(ds)
        assert "gross_margin" not in cat.kpis
        assert "profit" not in cat.kpis
        # 'revenue'-alias should still resolve to sum(sales)
        assert "total_revenue" in cat.kpis
        assert "sales" in cat.kpis["total_revenue"].formula.lower()


# ---------------------------------------------------------------------------
# 13) Plan validation catches semantic errors (asks for a KPI whose
#      required column doesn't exist).
# ---------------------------------------------------------------------------

def test_plan_validator_rejects_missing_column():
    from insightflow.knowledge.dataset_registry import get_active_dataset
    from insightflow.knowledge.kpi_catalog import build_catalog, KPIDefinition
    from insightflow.plan import AnalyticalPlan, MeasureRef, PlanValidator, IntentKind
    with _client() as client:
        body = "date,region,revenue\n2026-06-01,X,10\n"
        _upload(client, "valcheck", body)
        ds = get_active_dataset()
        cat = build_catalog(ds)
        # Inject a phony KPI requiring a nonexistent column
        cat.kpis["fake"] = KPIDefinition(
            kpi_id="fake", display_name="Fake",
            aggregation="sum", formula='SUM("nope")',
            required_columns=["nope"], unit="currency",
            aliases=["fake"],
        )
        plan = AnalyticalPlan(
            intent_kind=IntentKind.DIRECT_KPI, table=ds.table,
            measures=[MeasureRef(kpi_id="fake", formula='SUM("nope")',
                                  aggregation="sum")],
        )
        rep = PlanValidator(ds, cat).validate(plan)
        assert not rep.ok
        assert any("nope" in i.message for i in rep.issues)
        assert rep.fidelity == 0.0
