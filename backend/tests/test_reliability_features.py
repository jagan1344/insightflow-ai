"""Verification, cost guard, governance, adaptive clarification and
schema-change resilience on the independent multi-table fixtures.
Expected values are computed with plain sqlite3, never by the system."""
import json
import pathlib
import shutil
import sqlite3
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evaluation" / "v3"))
import fixtures as F  # noqa: E402

FACT = {"clinic": "visits", "logistics": "shipments"}


@pytest.fixture()
def live(tmp_path):
    """-> activate(db_name) -> path of the live (mutable) copy."""
    from insightflow.config import settings
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.dataset_registry import (
        DEMO_ID, bootstrap, register_relational, set_active)
    from insightflow.knowledge.schema_agent import refresh_schema
    old = settings.database_url
    src = {"clinic": F.build_a(tmp_path / "c_src.db"),
           "logistics": F.build_b(tmp_path / "l_src.db")}

    def activate(db):
        dst = tmp_path / f"{db}_live.db"
        shutil.copy(src[db], dst)
        settings.database_url = f"sqlite:///{dst}"
        reset_engine(); bootstrap()
        ds_id = register_relational(db, FACT[db])
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


def sql1(path, q):
    with sqlite3.connect(str(path)) as c:
        return c.execute(q).fetchall()


def plan_sql(q):
    from insightflow.knowledge.dataset_registry import get_active_dataset
    from insightflow.knowledge.kpi_catalog import build_catalog
    from insightflow.plan.compiler import plan_and_compile
    ds = get_active_dataset(); cat = build_catalog(ds)
    plan, sql = plan_and_compile(q, ds, cat)
    return plan, sql, ds, cat


# ---------------------------------------------------------------- verification
class TestVerification:
    def _rows(self, path, sql):
        return sql1(path, sql)

    def test_breakdown_reconciles_passes_on_real_rows(self, live):
        from insightflow.verification.answer_verifier import verify
        path = live("clinic")
        plan, sql, ds, cat = plan_sql("Total fee by insurer")
        rep = verify(plan, sql, self._rows(path, sql), ds, cat, str(path))
        assert rep.ok
        assert any(f.name == "breakdown_reconciles" and f.severity == "pass"
                   for f in rep.findings)

    def test_dropped_group_is_a_violation(self, live):
        from insightflow.verification.answer_verifier import verify
        path = live("clinic")
        plan, sql, ds, cat = plan_sql("Total fee by insurer")
        rows = self._rows(path, sql)[:-1]            # lose one group
        rep = verify(plan, sql, rows, ds, cat, str(path))
        assert [f.name for f in rep.violations] == ["breakdown_reconciles"]

    def test_null_group_is_kept_so_totals_reconcile(self, live):
        path = live("clinic")
        r = ask("Total fee by insurer")
        total = sql1(path, "SELECT SUM(fee) FROM visits")[0][0]
        assert abs(sum(row[-1] for row in r.result.rows) - total) < 1e-6
        assert any(row[0] is None for row in r.result.rows)

    def test_avg_out_of_bounds_violation(self, live):
        from insightflow.verification.answer_verifier import verify
        path = live("clinic")
        plan, sql, ds, cat = plan_sql("What is the average copay?")
        rep = verify(plan, sql, [(10 ** 9,)], ds, cat, str(path))
        assert [f.name for f in rep.violations] == ["avg_within_bounds"]

    def test_semijoin_equivalence_detects_wrong_value(self, live):
        from insightflow.verification.answer_verifier import verify
        path = live("clinic")
        q = "Total fee for patients insured by Medicaid (State)"
        plan, sql, ds, cat = plan_sql(q)
        good = self._rows(path, sql)
        assert verify(plan, sql, good, ds, cat, str(path)).ok
        bad = [(good[0][0] * 1.7,)]
        assert [f.name for f in verify(plan, sql, bad, ds, cat, str(path)).violations] \
            == ["semijoin_equivalence"]

    def test_null_measure_diagnostic(self, live):
        from insightflow.verification.answer_verifier import verify
        path = live("clinic")
        plan, sql, ds, cat = plan_sql("What is the average copay?")
        rep = verify(plan, sql, self._rows(path, sql), ds, cat, str(path))
        assert any(f.name == "null_measure_share" for f in rep.diagnostics)

    def test_boundary_sensitivity_diagnostic(self, live):
        from insightflow.verification.answer_verifier import verify
        path = live("clinic")
        plan, sql, ds, cat = plan_sql("Total fee for visits in June 2025")
        for f in plan.filters:
            if f.kind == "time_range":
                f.lo, f.hi = "2025-06-10", "2025-06-11"
        from insightflow.plan.compiler import SQLCompiler
        sql = SQLCompiler(ds, cat).compile(plan)
        rep = verify(plan, sql, self._rows(path, sql), ds, cat, str(path))
        assert any(f.name == "boundary_sensitivity" for f in rep.diagnostics)

    def test_orchestrator_downgrades_on_violation(self, live, monkeypatch):
        path = live("clinic")
        import insightflow.verification.answer_verifier as av
        from insightflow.verification.answer_verifier import Finding, VerificationReport
        monkeypatch.setattr(av, "verify", lambda *a, **k: VerificationReport(
            [Finding("breakdown_reconciles", "violation", "forced")]))
        r = ask("Total fee for Cardiology doctors")
        assert r.decision.action == "CLARIFY" and r.confidence.score <= 0.30


# ------------------------------------------------------------------ cost guard
class TestCostGuard:
    def test_cartesian_blocked(self, live):
        from insightflow.execution.cost_guard import analyze
        path = live("clinic")
        assert analyze(str(path), "SELECT COUNT(*) FROM visits, doctors").blocked
        assert analyze(str(path), "SELECT COUNT(*) FROM visits JOIN doctors").blocked
        assert analyze(str(path), "SELECT COUNT(*) FROM visits v CROSS JOIN doctors d").blocked

    def test_normal_join_allowed(self, live):
        from insightflow.execution.cost_guard import analyze
        path = live("clinic")
        sql = ("SELECT COUNT(*) FROM visits v JOIN doctors d "
               "ON d.doctor_id=v.doctor_id")
        assert not analyze(str(path), sql).blocked

    def test_scan_budget_blocks_runaway(self, live):
        from insightflow.execution.cost_guard import analyze
        path = live("clinic")
        sql = "SELECT COUNT(*) FROM visits a, visits b WHERE a.fee < b.fee"
        rep = analyze(str(path), sql, max_scan_cost=100_000)
        assert rep.blocked and "estimated" in rep.reasons[0]

    def test_time_budget_cancels(self, live):
        from insightflow.config import settings
        from insightflow.execution.executor import run_sql
        live("clinic")
        old = settings.query_timeout_s
        settings.query_timeout_s = 0.2
        try:
            r = run_sql("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 "
                        "FROM c WHERE x<2000000000) SELECT COUNT(*) FROM c")
        finally:
            settings.query_timeout_s = old
        assert not r.ok and "time budget" in r.error

    def test_connection_is_read_only(self, live):
        from insightflow.execution.executor import run_sql
        path = live("clinic")
        r = run_sql("CREATE TABLE zz(x INTEGER)")
        assert not r.ok
        assert not sql1(path, "SELECT 1 FROM sqlite_master WHERE name='zz'")
        # and normal reads still work afterwards (pragma restored)
        assert run_sql("SELECT COUNT(*) FROM visits").ok


# ------------------------------------------------------------------ governance
class TestGovernance:
    def test_expression_validation(self):
        from insightflow.governance.metrics import validate_expression as v
        cols = ["fee", "copay"]
        assert v("SUM(fee - copay)", cols)[0] == 'SUM("fee" - "copay")'
        for bad in ("SUM(fee); DROP TABLE visits", "SUM(load_extension(fee))",
                    "SUM(nope)", "(SELECT 1)", "SUM(fee) -- x"):
            assert v(bad, cols)[0] is None, bad

    def _cfg(self, tmp_path, monkeypatch, tables):
        p = tmp_path / "metrics.json"
        p.write_text(json.dumps({"tables": tables}))
        monkeypatch.setenv("INSIGHTFLOW_METRICS_FILE", str(p))

    def test_configured_metric_matches_reference(self, live, tmp_path, monkeypatch):
        self._cfg(tmp_path, monkeypatch, {"visits": {"metrics": [
            {"id": "net_fee", "name": "Net Fee", "expression": "SUM(fee - copay)",
             "synonyms": ["net revenue"], "unit": "currency"}]}})
        path = live("clinic")
        r = ask("What is the net fee?")
        exp = sql1(path, "SELECT SUM(fee - copay) FROM visits")[0][0]
        assert r.decision.action in ("ANSWER", "WARN")
        assert abs(float(r.result.rows[0][-1]) - exp) < 1e-6

    def test_conflicting_synonym_is_clarified(self, live, tmp_path, monkeypatch):
        self._cfg(tmp_path, monkeypatch, {"visits": {"metrics": [
            {"id": "gross_fee", "name": "Gross Fee", "expression": "SUM(fee)",
             "synonyms": ["revenue"]},
            {"id": "net_fee", "name": "Net Fee", "expression": "SUM(fee - copay)",
             "synonyms": ["revenue"]}]}})
        live("clinic")
        r = ask("What is the revenue?")
        assert r.decision.action == "CLARIFY"
        assert "revenue" in r.explanation and "defined more than one way" in r.explanation
        # naming one of them explicitly resolves it
        assert ask("What is the net fee?").decision.action in ("ANSWER", "WARN")

    def test_unsafe_definition_rejected(self, live, tmp_path, monkeypatch):
        self._cfg(tmp_path, monkeypatch, {"visits": {"metrics": [
            {"id": "evil", "name": "Evil", "expression": "SUM(fee); DROP TABLE visits",
             "synonyms": ["evil"]}]}})
        path = live("clinic")
        r = ask("What is the evil?")
        assert r.decision.action != "ANSWER"
        assert sql1(path, "SELECT COUNT(*) FROM visits")[0][0] == 600

    def test_date_convention_removes_needless_question(self, live, tmp_path, monkeypatch):
        self._cfg(tmp_path, monkeypatch, {"visits": {"date_default": "visit_date"}})
        path = live("clinic")
        r = ask("Total fee in June 2025")
        exp = sql1(path, "SELECT SUM(fee) FROM visits WHERE visit_date>='2025-06-01' "
                         "AND visit_date<'2025-07-01'")[0][0]
        assert r.decision.action in ("ANSWER", "WARN")
        assert abs(float(r.result.rows[0][-1]) - exp) < 1e-6


# ------------------------------------------------------ adaptive clarification
class TestAdaptiveClarification:
    def test_material_ambiguity_lists_each_reading_with_its_value(self, live):
        path = live("clinic")
        r = ask("Total fee in June 2025")
        a = sql1(path, "SELECT SUM(fee) FROM visits WHERE visit_date>='2025-06-01' AND visit_date<'2025-07-01'")[0][0]
        b = sql1(path, "SELECT SUM(fee) FROM visits WHERE discharge_date>='2025-06-01' AND discharge_date<'2025-07-01'")[0][0]
        assert r.decision.action == "CLARIFY"
        assert f"{a:,.2f}" in r.explanation and f"{b:,.2f}" in r.explanation

    def test_immaterial_ambiguity_is_answered_without_asking(self, live):
        path = live("clinic")
        with sqlite3.connect(str(path)) as c:
            c.execute("UPDATE visits SET discharge_date = visit_date")
        r = ask("Total fee in June 2025")
        exp = sql1(path, "SELECT SUM(fee) FROM visits WHERE visit_date>='2025-06-01' AND visit_date<'2025-07-01'")[0][0]
        assert r.decision.action in ("ANSWER", "WARN")
        assert abs(float(r.result.rows[0][-1]) - exp) < 1e-6
        assert any(n.startswith("ambiguity_immaterial") for n in r.notes)

    def test_unknown_value_offers_close_matches(self, live):
        live("clinic")
        r = ask("Total fee for patients insured by Medicaid")
        assert r.decision.action in ("CLARIFY", "ANSWER", "WARN")
        r2 = ask("Total fee for patients insured by Aetnaa")
        assert r2.decision.action == "CLARIFY" and "Aetna" in r2.explanation

    def test_valid_context_not_lost_on_clarification(self, live):
        live("clinic")
        r = ask("Total fee for Cardiology doctors in June 2025")
        # the Cardiology filter must be preserved inside each candidate reading
        assert "Cardiology" in r.explanation or r.decision.action in ("ANSWER", "WARN")


# ---------------------------------------------------------- schema-change drift
class TestSchemaChange:
    def test_added_column_is_used_and_reported(self, live):
        path = live("clinic")
        assert ask("Total fee for Cardiology doctors").decision.action in ("ANSWER", "WARN")
        with sqlite3.connect(str(path)) as c:
            c.execute("ALTER TABLE visits ADD COLUMN severity TEXT")
            c.execute("UPDATE visits SET severity = CASE WHEN visit_id % 3 = 0 THEN 'Critical' ELSE 'Routine' END")
        r = ask("Total fee for Critical severity")
        exp = sql1(path, "SELECT SUM(fee) FROM visits WHERE severity='Critical'")[0][0]
        assert r.decision.action in ("ANSWER", "WARN")
        assert abs(float(r.result.rows[0][-1]) - exp) < 1e-6
        assert any("column added: visits.severity" in n for n in r.notes)

    def test_renamed_measure_never_serves_stale_sql(self, live):
        path = live("clinic")
        assert ask("What is the total fee?").decision.action in ("ANSWER", "WARN")
        with sqlite3.connect(str(path)) as c:
            c.execute("ALTER TABLE visits RENAME COLUMN fee TO fee_amount")
        r = ask("What is the total fee?")
        exp = sql1(path, "SELECT SUM(fee_amount) FROM visits")[0][0]
        if r.decision.action in ("ANSWER", "WARN"):
            assert abs(float(r.result.rows[0][-1]) - exp) < 1e-6
        assert not (r.sql and '"fee"' in r.sql.replace("fee_amount", ""))

    def test_dropped_dimension_table_is_not_answered_from_memory(self, live):
        path = live("clinic")
        assert ask("Total fee by insurer").decision.action in ("ANSWER", "WARN")
        with sqlite3.connect(str(path)) as c:
            c.execute("DROP TABLE insurers")
        r = ask("Total fee by insurer")
        assert r.decision.action != "ANSWER"

    def test_dropped_anchor_table(self, live):
        path = live("clinic")
        with sqlite3.connect(str(path)) as c:
            c.executescript("DROP TABLE visit_procedures; DROP TABLE visits;")
        r = ask("What is the total fee?")
        assert r.decision.action == "CLARIFY" and "no longer exists" in r.explanation

    def test_new_relationship_is_discovered(self, live):
        path = live("logistics")
        assert ask("What is the total freight cost?").decision.action in ("ANSWER", "WARN")
        with sqlite3.connect(str(path)) as c:
            c.executescript("""
              CREATE TABLE warehouses (warehouse_key INTEGER PRIMARY KEY, warehouse_label TEXT NOT NULL);
              INSERT INTO warehouses VALUES (1,'North Depot'),(2,'South Depot'),(3,'Idle Depot');
              ALTER TABLE shipments ADD COLUMN warehouse_ref INTEGER;
              UPDATE shipments SET warehouse_ref = 1 + (shp_no % 2);
            """)
        r = ask("Total freight cost by warehouse")
        exp = dict(sql1(path, "SELECT w.warehouse_label, SUM(s.freight_usd) FROM shipments s "
                              "JOIN warehouses w ON w.warehouse_key=s.warehouse_ref GROUP BY 1"))
        assert r.decision.action in ("ANSWER", "WARN")
        got = {row[0]: row[-1] for row in r.result.rows}
        assert set(got) == set(exp) and all(abs(got[k] - exp[k]) < 1e-6 for k in exp)
        assert any("relationship added" in n or "table added" in n for n in r.notes)
