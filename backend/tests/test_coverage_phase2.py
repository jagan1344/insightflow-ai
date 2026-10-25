"""Phase-2 coverage fixes on the round-6 fixtures (developed against these
cases, so not evidence of generalization). Every expected value comes from an
independent sqlite3 query; an ANSWER/WARN with a wrong value fails."""
import pathlib, sys

import pytest

EV = pathlib.Path(__file__).resolve().parents[2] / "evaluation" / "v3"
sys.path.insert(0, str(EV))
import fixtures_r6 as FR      # noqa: E402
import baseline_current as B  # noqa: E402
import run_eval as RE         # noqa: E402

pytestmark = pytest.mark.skipif(not EV.exists(), reason="evaluation fixtures absent")
A_, F_ = "airline@flights", "farm@readings"
OK = ("ANSWER", "WARN")
_RF = "FROM readings r JOIN fields f ON f.field_id = r.field_id"


@pytest.fixture(scope="module", autouse=True)
def _build():
    from insightflow.config import settings
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.dataset_registry import bootstrap, set_active, DEMO_ID
    url = settings.database_url
    FR.build_air(); FR.build_saas(); FR.build_farm()
    yield
    settings.database_url = url
    reset_engine(); bootstrap(); set_active(DEMO_ID)


def ask(db, q):
    from insightflow.orchestrator import Orchestrator
    B.register(db)
    return Orchestrator().ask(q)


def ref(db, sql):
    return RE.ref(db, sql)


def answered_value(r):
    assert r.decision.action in OK, (r.decision.action, r.decision.reason)
    assert r.result.ok and len(r.result.rows) == 1
    return r.result.rows[0][0]


def refused(r):
    return r.decision.action in ("CLARIFY", "ABSTAIN")


# ---------------------------------------------------------------- R15 / R16
@pytest.mark.parametrize("q,cond", [
    ("Average moisture for fields larger than 100 acres", "f.acres > 100"),
    ("Average moisture for fields with more than 100 acres", "f.acres > 100"),
    ("Average moisture for fields smaller than 100 acres", "f.acres < 100"),
    ("Average moisture for fields bigger than 150 acres", "f.acres > 150"),
])
def test_related_numeric_threshold(q, cond):
    exp = ref(F_, f"SELECT AVG(r.moisture) {_RF} WHERE {cond}")[0][0]
    wrong = ref(F_, f"SELECT AVG(r.moisture) {_RF} WHERE f.acres = {cond.split()[-1]}")[0][0]
    v = answered_value(ask(F_, q))
    assert v == pytest.approx(exp)
    assert wrong is None or v != pytest.approx(wrong)


def test_unknown_comparative_is_not_read_as_equality():
    r = ask(F_, "Average moisture for fields taller than 100 acres")
    assert refused(r)
    assert "acres = 100" not in (r.sql or "").replace('"', "")


def test_comparative_word_needs_the_filter():
    from types import SimpleNamespace as NS
    from insightflow.reliability.mention_coverage import words_consumed_by_plan
    from insightflow.plan.plan import FilterExpr
    q = "Average moisture for fields larger than 100 acres"
    assert "larger" in words_consumed_by_plan(q, NS(filters=[FilterExpr(kind="cmp", column="acres", value=100, op=">")]))
    assert "larger" not in words_consumed_by_plan(q, NS(filters=[FilterExpr(kind="cmp", column="acres", value=100, op="=")]))
    assert "larger" not in words_consumed_by_plan(q, NS(filters=[]))


# ---------------------------------------------------------------- R05
@pytest.mark.parametrize("q,sql", [
    ("How many readings had a faulty sensor?", "SELECT COUNT(*) FROM readings WHERE sensor_ok = 0"),
    ("How many readings had a broken sensor?", "SELECT COUNT(*) FROM readings WHERE sensor_ok = 0"),
    ("How many readings had an ok sensor?", "SELECT COUNT(*) FROM readings WHERE sensor_ok = 1"),
    ("Average moisture for readings with a faulty sensor", "SELECT AVG(moisture) FROM readings WHERE sensor_ok = 0"),
])
def test_polarity_flag(q, sql):
    assert answered_value(ask(F_, q)) == pytest.approx(ref(F_, sql)[0][0])


def test_faulty_never_selects_the_ok_rows():
    ok_rows = ref(F_, "SELECT COUNT(*) FROM readings WHERE sensor_ok = 1")[0][0]
    r = ask(F_, "How many readings had a faulty sensor?")
    assert not (r.decision.action in OK and r.result.rows[0][0] == ok_rows)


@pytest.mark.parametrize("q,exp_value", [
    ("How many readings were taken without a faulty sensor?", 1),
    ("How many readings had a sensor?", None),
])
def test_polarity_flag_negation_and_noun_alone(q, exp_value):
    from insightflow.plan.planner import _find_flag_filters
    from insightflow.knowledge.dataset_registry import get_active_dataset
    B.register(F_)
    fs = [f for f in _find_flag_filters(q, get_active_dataset()) if f.column == "sensor_ok"]
    if exp_value is None:
        assert fs == []                       # the subject noun alone does not choose a value
    else:
        assert [f.value for f in fs] == [exp_value]
    r = ask(F_, q)
    if r.decision.action in OK:
        sql = "SELECT COUNT(*) FROM readings" + ("" if exp_value is None else f" WHERE sensor_ok = {exp_value}")
        assert r.result.rows[0][0] == ref(F_, sql)[0][0]


# ---------------------------------------------------------------- A12
@pytest.mark.parametrize("q,sql", [
    ("Total passengers", "SELECT SUM(pax_cnt) FROM flights"),
    ("Average passengers", "SELECT AVG(pax_cnt) FROM flights"),
    ("Total passengers for cancelled flights", "SELECT SUM(pax_cnt) FROM flights WHERE is_cancelled = 1"),
])
def test_abbreviated_measure(q, sql):
    assert answered_value(ask(A_, q)) == pytest.approx(ref(A_, sql)[0][0])


def test_how_many_measure_noun_is_not_a_row_count():
    rows = ref(A_, "SELECT COUNT(*) FROM flights")[0][0]
    r = ask(A_, "How many passengers were there?")
    if r.decision.action in OK:
        assert r.result.rows[0][0] == ref(A_, "SELECT SUM(pax_cnt) FROM flights")[0][0]
    else:
        assert refused(r) and r.confidence.score <= 0.30
    assert not (r.decision.action in OK and r.result.rows[0][0] == rows)
    assert "semantic_verifier_error" not in r.diagnostics


def test_how_many_anchor_rows_still_counts_rows():
    assert answered_value(ask(A_, "How many flights were there?")) == ref(A_, "SELECT COUNT(*) FROM flights")[0][0]


# ---------------------------------------------------------------- A13
@pytest.mark.parametrize("q,sql", [
    ("Average fare per flight", "SELECT AVG(fare_amt) FROM flights"),
    ("What is the average fare per flight?", "SELECT AVG(fare_amt) FROM flights"),
    ("Mean fare per flight for cancelled flights", "SELECT AVG(fare_amt) FROM flights WHERE is_cancelled = 1"),
])
def test_average_per_base_row(q, sql):
    assert answered_value(ask(A_, q)) == pytest.approx(ref(A_, sql)[0][0])


def test_average_per_other_entity_is_not_collapsed():
    from insightflow.semantics import requested_shape
    from insightflow.knowledge.dataset_registry import get_active_dataset
    B.register(A_)
    ds = get_active_dataset()
    assert requested_shape("Average fare per flight", ds) != "grouped"
    assert requested_shape("Average fare per carrier", ds) == "grouped"
    r = ask(A_, "Average fare per carrier")
    assert not (r.decision.action in OK and len(r.result.rows) == 1)


# ---------------------------------------------------------------- A11
@pytest.mark.parametrize("q,col", [
    ("Total fare by origin airport", "orig_cd"),
    ("Total fare by destination airport", "dest_cd"),
])
def test_role_playing_inferred_fk(q, col):
    exp = sorted(ref(A_, f"SELECT a.apt_nm, SUM(f.fare_amt) FROM flights f JOIN airports a "
                         f"ON a.apt_cd = f.{col} GROUP BY 1"))
    r = ask(A_, q)
    assert r.decision.action in OK
    got = sorted((str(a), float(b)) for a, b in r.result.rows)
    assert [g[0] for g in got] == [e[0] for e in exp]
    assert all(g[1] == pytest.approx(e[1]) for g, e in zip(got, exp))
    assert "inferred" in r.decision.reason          # the undeclared relationship is disclosed


def test_role_is_not_guessed():
    assert refused(ask(A_, "Total fare by airport"))


def test_suffix_inference_rules():
    import sqlite3
    from insightflow.knowledge.relational import _suffix_candidates, RelationalSchema
    con = sqlite3.connect(":memory:")
    con.executescript("""
      CREATE TABLE ports (prt_cd TEXT PRIMARY KEY, nm TEXT);
      CREATE TABLE codes (alt_cd TEXT PRIMARY KEY);
      CREATE TABLE trips (t_id INTEGER PRIMARY KEY, from_cd TEXT, few_cd TEXT, n_id INTEGER, x_cd TEXT);
      CREATE TABLE groups_ (grp_id INTEGER PRIMARY KEY);
      INSERT INTO ports VALUES ('A','a'),('B','b'),('C','c'),('D','d');
      INSERT INTO codes VALUES ('Q'),('R'),('S');
      INSERT INTO groups_ VALUES (1),(2),(3),(4);
      INSERT INTO trips VALUES (1,'A','A',1,'Z'),(2,'B','B',2,'Q'),(3,'C','A',3,'R'),(4,'D','B',4,'S');
    """)
    schema = RelationalSchema._discover(con, set())
    tabs = schema.tables
    t = tabs["trips"].columns
    assert ("trips", "from_cd", "ports", "prt_cd", "inferred") in {
        (e.child_table, e.child_col, e.parent_table, e.parent_col, e.status) for e in schema.edges}
    assert _suffix_candidates(con, tabs, "trips", "from_cd", t["from_cd"]) == [("ports", "prt_cd")]
    assert _suffix_candidates(con, tabs, "trips", "few_cd", t["few_cd"]) == []    # < 3 distinct values
    assert _suffix_candidates(con, tabs, "trips", "n_id", t["n_id"]) == []        # integer keys never qualify
    assert _suffix_candidates(con, tabs, "trips", "x_cd", t["x_cd"]) == []        # 'Z' not contained


# ---------------------------------------------------------------- ablation switches (research only)
def test_ablation_is_off_by_default(monkeypatch):
    from insightflow.config import ablated, ABLATION_COMPONENTS
    monkeypatch.delenv("INSIGHTFLOW_ABLATE", raising=False)
    assert not any(ablated(c) for c in ABLATION_COMPONENTS)
    assert refused(ask("farm@harvests", "Total yield tons per acre"))


def test_semantic_ablation_switch_takes_effect(monkeypatch):
    # with the semantic layer off, the V07 ratio question is no longer stopped by it
    monkeypatch.setenv("INSIGHTFLOW_ABLATE", "semantic")
    r = ask("farm@harvests", "Total yield tons per acre")
    assert "semantic_findings" not in r.diagnostics
    monkeypatch.setenv("INSIGHTFLOW_ABLATE", "confidence_gate")
    from insightflow.reliability.decision import decide
    from insightflow.reliability.confidence import Confidence
    d = decide(Confidence(score=0.1, signals={}), sql_ok=True, exec_ok=True, ambiguous=False)
    assert d.action == "ANSWER"
    monkeypatch.delenv("INSIGHTFLOW_ABLATE")
    assert decide(Confidence(score=0.1, signals={}), sql_ok=True, exec_ok=True, ambiguous=False).action == "ABSTAIN"


# ---------------------------------------------------------------- inclusive comparatives, value-qualified fan-out filter
@pytest.mark.parametrize("q,cond", [
    ("Average moisture for fields with at least 120 acres", "f.acres >= 120"),
    ("Average moisture for fields with at most 120 acres", "f.acres <= 120"),
])
def test_inclusive_threshold(q, cond):
    assert answered_value(ask(F_, q)) == pytest.approx(ref(F_, f"SELECT AVG(r.moisture) {_RF} WHERE {cond}")[0][0])


def test_value_qualified_fanout_filter_is_a_semi_join():
    S_ = "saas@invoices"
    si = "FROM invoices i JOIN subscriptions s ON s.sub_id = i.sub_id"
    exp = ref(S_, f"SELECT SUM(i.total_usd) {si} WHERE EXISTS (SELECT 1 FROM support_tickets t "
                  f"WHERE t.acct_id = s.acct_id AND t.priority = 'High')")[0][0]
    joined = ref(S_, f"SELECT SUM(i.total_usd) {si} JOIN support_tickets t ON t.acct_id = s.acct_id "
                     f"WHERE t.priority = 'High'")[0][0]
    assert exp != pytest.approx(joined)                 # a plain join would double count
    assert answered_value(ask(S_, "Total usd for accounts with High priority tickets")) == pytest.approx(exp)
    assert refused(ask(S_, "Total usd by priority"))    # grouping over the fan-out is still refused
