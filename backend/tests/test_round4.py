"""Round 4: header/detail (retail) and hr schemas, plus relationship-inference
fixes found on them. Oracles are plain sqlite3."""
import json
import pathlib
import shutil
import sqlite3
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evaluation" / "v3"))
import fixtures as F0  # noqa: E402
import fixtures_v4 as F  # noqa: E402
from insightflow.knowledge.relational import RelationalSchema  # noqa: E402


@pytest.fixture()
def live4(tmp_path, monkeypatch):
    from insightflow.config import settings
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.dataset_registry import (
        DEMO_ID, bootstrap, register_relational, set_active)
    from insightflow.knowledge.schema_agent import refresh_schema
    old = settings.database_url
    F.DATA.mkdir(exist_ok=True)
    src = {"retail": F.build_d(tmp_path / "r.db"), "hr": F.build_e(tmp_path / "h.db")}
    cfg = tmp_path / "retail.metrics.json"
    cfg.write_text(json.dumps(F.D_METRICS))

    def activate(db, anchor):
        dst = tmp_path / f"{db}_{anchor}.db"
        shutil.copy(src[db], dst)
        settings.database_url = f"sqlite:///{dst}"
        if db == "retail":
            monkeypatch.setenv("INSIGHTFLOW_METRICS_FILE", str(cfg))
        else:
            monkeypatch.delenv("INSIGHTFLOW_METRICS_FILE", raising=False)
        reset_engine(); bootstrap()
        ds_id = register_relational(f"{db}@{anchor}", anchor)
        reset_engine(); refresh_schema(); set_active(ds_id)
        return dst
    yield activate
    settings.database_url = old
    reset_engine()
    try:
        set_active(DEMO_ID)
    except Exception:
        pass


def ask(q):
    from insightflow.orchestrator import Orchestrator
    return Orchestrator().ask(q)


def sql1(p, q):
    with sqlite3.connect(str(p)) as c:
        return c.execute(q).fetchall()


def val(r):
    return float(r.result.rows[0][-1]) if r.result.rows and r.result.rows[0][-1] is not None else None


def test_edges_exact_retail_and_hr(tmp_path):
    for builder, edges in ((F.build_d, F.D_EDGES), (F.build_e, F.E_EDGES)):
        s = RelationalSchema.discover(str(builder(tmp_path / "x.db")))
        assert {e.key() for e in s.edges} == edges


def test_primary_key_coincidence_is_not_a_foreign_key(tmp_path):
    """orders.order_id (PK 1..400) is contained in order_lines.line_id
    (PK 1..1000) and 'order' appears in 'order_lines', but order_lines.order_id
    is the real FK. The reverse edge must not be inferred."""
    s = RelationalSchema.discover(str(F.build_d(tmp_path / "x.db")))
    assert ("orders", "order_id", "order_lines", "line_id") not in {e.key() for e in s.edges}


def test_other_registered_anchor_tables_are_not_foreign(live4):
    # the demo registry row names a table 'orders'; retail has its own
    live4("retail", "order_lines")
    live4("retail", "orders")
    from insightflow.knowledge.dataset_registry import get_active_dataset
    ds = get_active_dataset()
    assert ds.rel is not None and "store_name" in ds.columns and "region" in ds.columns


class TestRetail:
    def test_header_date_via_noun(self, live4):
        p = live4("retail", "order_lines")
        r = ask("Gross sales for orders placed in June 2025")
        exp = sql1(p, "SELECT SUM(l.qty*l.unit_price) FROM order_lines l JOIN orders o ON o.order_id=l.order_id WHERE o.order_date>='2025-06-01' AND o.order_date<'2025-07-01'")[0][0]
        assert r.decision.action in ("ANSWER", "WARN") and abs(val(r) - exp) < 1e-6

    def test_two_header_dates_are_a_material_ambiguity(self, live4):
        p = live4("retail", "order_lines")
        r = ask("Gross sales in June 2025")
        assert r.decision.action == "CLARIFY"
        a = sql1(p, "SELECT SUM(l.qty*l.unit_price) FROM order_lines l JOIN orders o ON o.order_id=l.order_id WHERE o.order_date>='2025-06-01' AND o.order_date<'2025-07-01'")[0][0]
        assert f"{a:,.2f}" in r.explanation

    def test_specific_wording_picks_the_ship_date(self, live4):
        p = live4("retail", "order_lines")
        r = ask("Gross sales for orders shipped in July 2025")
        exp = sql1(p, "SELECT SUM(l.qty*l.unit_price) FROM order_lines l JOIN orders o ON o.order_id=l.order_id WHERE o.ship_date>='2025-07-01' AND o.ship_date<'2025-08-01'")[0][0]
        assert abs(val(r) - exp) < 1e-6

    def test_header_money_on_a_line_anchor_is_never_answered_plainly(self, live4):
        p = live4("retail", "order_lines")
        r = ask("What is the total shipping fee?")
        true_total = sql1(p, "SELECT SUM(shipping_fee) FROM orders")[0][0]
        assert r.decision.action in ("WARN", "CLARIFY")
        if r.result.rows:
            assert "counted once per" in r.explanation
            assert abs(val(r) - true_total) > 1      # the duplicated figure, flagged

    def test_header_money_on_the_header_anchor(self, live4):
        p = live4("retail", "orders")
        r = ask("What is the total shipping fee?")
        assert abs(val(r) - sql1(p, "SELECT SUM(shipping_fee) FROM orders")[0][0]) < 1e-6

    def test_entity_noun_does_not_add_a_count_measure(self, live4):
        p = live4("retail", "orders")
        r = ask("How many distinct customers placed orders?")
        assert len(r.result.rows[0]) == 1 and val(r) == sql1(p, "SELECT COUNT(DISTINCT customer_id) FROM orders")[0][0]

    def test_no_customer_is_a_null_count(self, live4):
        p = live4("retail", "orders")
        r = ask("How many orders had no customer?")
        assert val(r) == sql1(p, "SELECT COUNT(*) FROM orders WHERE customer_id IS NULL")[0][0]

    def test_anti_join_is_refused(self, live4):
        live4("retail", "order_lines")
        r = ask("Which stores had no sales?")
        assert r.decision.action == "CLARIFY" and "anti-join" in r.explanation

    def test_related_attribute_threshold_is_a_row_filter(self, live4):
        p = live4("retail", "order_lines")
        r = ask("Total quantity for products with list price above 50")
        exp = sql1(p, "SELECT SUM(l.qty) FROM order_lines l JOIN products p ON p.product_id=l.product_id WHERE p.list_price>50")[0][0]
        assert abs(val(r) - exp) < 1e-9

    def test_governed_metric_and_apostrophe_value(self, live4):
        p = live4("retail", "order_lines")
        r = ask("Net sales excluding Kids' Toys")
        exp = sql1(p, "SELECT SUM(l.qty*l.unit_price*(1-COALESCE(l.discount,0))) FROM order_lines l JOIN products pr ON pr.product_id=l.product_id LEFT JOIN categories c ON c.category_id=pr.category_id WHERE c.category_name IS NULL OR c.category_name<>\"Kids' Toys\"")[0][0]
        assert abs(val(r) - exp) < 1e-6

    def test_row_noun_phrase_is_not_a_table_reference(self, live4):
        p = live4("retail", "order_lines")
        r = ask("How many order lines were there?")
        assert val(r) == sql1(p, "SELECT COUNT(*) FROM order_lines")[0][0]


class TestHr:
    def test_self_reference_is_refused_not_guessed(self, live4):
        live4("hr", "employees")
        r = ask("How many employees report to Dana Reyes?")
        assert r.decision.action == "CLARIFY" and "hierarchy" in r.explanation

    def test_anchor_single_date_is_the_default(self, live4):
        p = live4("hr", "assignments")
        r = ask("Total hours in June 2025")
        exp = sql1(p, "SELECT SUM(hours) FROM assignments WHERE week_start>='2025-06-01' AND week_start<'2025-07-01'")[0][0]
        assert r.decision.action in ("ANSWER", "WARN") and abs(val(r) - exp) < 1e-6

    def test_related_date_when_named(self, live4):
        p = live4("hr", "assignments")
        r = ask("Total hours for employees hired in 2024")
        exp = sql1(p, "SELECT SUM(a.hours) FROM assignments a JOIN employees e ON e.emp_id=a.emp_id WHERE e.hire_date>='2024-01-01' AND e.hire_date<'2025-01-01'")[0][0]
        assert abs(val(r) - exp) < 1e-6

    def test_per_row_noun_is_not_a_grouping(self, live4):
        p = live4("hr", "assignments")
        r = ask("What is the average hours per assignment?")
        assert abs(val(r) - sql1(p, "SELECT AVG(hours) FROM assignments")[0][0]) < 1e-9

    def test_department_reachable_two_ways_shows_both_values(self, live4):
        p = live4("hr", "assignments")
        r = ask("Total hours by department")
        assert r.decision.action == "CLARIFY"

    def test_anchor_numeric_row_filter(self, live4):
        p = live4("hr", "employees")
        r = ask("Total salary for employees with bonus over 5000")
        assert abs(val(r) - sql1(p, "SELECT SUM(salary) FROM employees WHERE bonus>5000")[0][0]) < 1e-6
        assert len(r.result.rows[0]) == 1
