"""Regression tests for classes found on the round-6 sealed first run (K1).
Uses the committed round-6 fixtures (airline / saas / farm). Oracles: sqlite3."""
import pathlib, sys

import pytest

EV = pathlib.Path(__file__).resolve().parents[2] / "evaluation" / "v3"
sys.path.insert(0, str(EV))
import fixtures_r6 as FR      # noqa: E402
import baseline_current as B  # noqa: E402

pytestmark = pytest.mark.skipif(not EV.exists(), reason="evaluation fixtures absent")


def ask(db, q):
    from insightflow.orchestrator import Orchestrator
    B.register(db)
    return Orchestrator().ask(q)


@pytest.fixture(scope="module", autouse=True)
def _build():
    from insightflow.config import settings
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.dataset_registry import bootstrap, set_active, DEMO_ID
    url = settings.database_url
    FR.build_air(); FR.build_saas(); FR.build_farm()
    yield
    settings.database_url = url          # leave global state as other tests expect
    reset_engine(); bootstrap(); set_active(DEMO_ID)


import re

import run_eval as RE

A_, S_, F_, H_ = "airline@flights", "saas@invoices", "farm@readings", "farm@harvests"
OK = ("ANSWER", "WARN")


def ref(db, sql):
    return RE.ref(db, sql)


import final6_questions as FQ

SEALED = {q[1]: q for q in FQ.FINAL6}


def sealed_ref(qid):
    return ref(SEALED[qid][0], SEALED[qid][5])[0][0]


def scalar(r):
    return float(r.result.rows[0][0])


def refuses(r):
    return r.decision.action in ("CLARIFY", "ABSTAIN")


def keeps_non_cancelled(sql):
    """True iff the WHERE keeps is_cancelled = 0 (or an equivalent negation) and never
    keeps only is_cancelled = 1. Parsed per predicate, not by searching for '0'."""
    s = re.sub(r"[\"`\[\]]", "", sql.lower())
    s = re.sub(r"\b\w+\.(?=is_cancelled)", "", s)
    s = re.sub(r"\s+", " ", s)
    keeps0 = re.search(r"\bis_cancelled\s*(=|==|is)\s*0\b|\bis_cancelled\s*(!=|<>)\s*1\b"
                       r"|\bnot\s*\(?\s*(\w+\.)?is_cancelled\s*=\s*1", s)
    keeps1 = re.search(r"\bis_cancelled\s*(=|==|is)\s*1\b|\bis_cancelled\s*(!=|<>)\s*0\b", s)
    return bool(keeps0) and not keeps1


# ------------------------------------------------------------ Task 1: fail closed
def test_verifier_exception_fails_closed(monkeypatch):
    import insightflow.semantics as sem

    def boom(*a, **k):
        raise RuntimeError("internal verifier bug /secret/path")
    monkeypatch.setattr(sem, "verify_semantics", boom)
    r = ask(A_, "Total fare")                     # would normally be ANSWER
    assert r.decision.action == "CLARIFY"
    assert r.confidence.score <= 0.30
    assert r.explanation.lower().startswith("the answer could not be checked")
    assert r.explanation == (r.decision.reason[0].upper() + r.decision.reason[1:] + ".")
    assert "RuntimeError" not in r.explanation and "secret" not in r.explanation
    assert "Traceback" not in r.explanation
    assert r.chart == {"kind": "none"} and r.recommendation is None
    assert r.diagnostics["semantic_verifier_error"].startswith("RuntimeError")
    assert any(n.startswith("semantic_verifier_error=RuntimeError") for n in r.notes)
    assert "semantic_findings" not in r.diagnostics     # no fabricated report


def test_verifier_normal_path_unchanged():
    r = ask(A_, "Total fare")
    assert r.decision.action in OK
    assert "semantic_verifier_error" not in r.diagnostics


# ------------------------------------------------------------ Task 2: A17
def test_flag_exclusion_keeps_the_zero_rows():
    q = "Total fare excluding cancelled flights"
    expected = ref(A_, "SELECT SUM(fare_amt) FROM flights WHERE is_cancelled=0")[0][0]
    cancelled = ref(A_, "SELECT SUM(fare_amt) FROM flights WHERE is_cancelled=1")[0][0]
    assert abs(expected - cancelled) > 1            # the two readings are distinguishable
    r = ask(A_, q)
    if r.decision.action in OK:
        assert keeps_non_cancelled(r.sql), r.sql
        assert scalar(r) == pytest.approx(expected)
        assert scalar(r) != pytest.approx(cancelled)
    else:
        assert refuses(r) and r.confidence.score <= 0.30     # never a confident wrong number


@pytest.mark.parametrize("sql,ok", [
    ("SELECT SUM(fare_amt) FROM flights WHERE is_cancelled = 0", True),
    ("SELECT SUM(fare_amt) FROM flights WHERE is_cancelled <> 1", True),
    ("SELECT SUM(fare_amt) FROM flights WHERE is_cancelled = 1", False),
    ("SELECT SUM(fare_amt) FROM flights WHERE is_cancelled = 1 AND fare_amt > 0", False),
    ("SELECT SUM(fare_amt * 10) FROM flights WHERE is_cancelled = 1", False),
    ('SELECT SUM("flights"."fare_amt") FROM "flights" WHERE "flights"."is_cancelled" = 0', True),
    ('SELECT SUM("flights"."fare_amt") FROM "flights" WHERE "flights"."is_cancelled" = 1', False),
])
def test_predicate_checker_is_not_fooled_by_stray_zeros(sql, ok):
    assert keeps_non_cancelled(sql) is ok


# ------------------------------------------------------------ Task 3: V07
def test_per_measure_ratio_is_not_two_sums():
    r = ask(H_, "Total yield tons per acre")
    ys = ref(H_, "SELECT SUM(yield_tons) FROM harvests")[0][0]
    ac = ref(H_, "SELECT SUM(f.acres) FROM harvests h JOIN fields f ON f.field_id=h.field_id")[0][0]
    if r.decision.action in OK:      # acceptable only as a genuine ratio, never two separate sums
        flat = [float(v) for row in r.result.rows for v in row if isinstance(v, (int, float))]
        assert "/" in r.sql, r.sql
        assert not (any(abs(v - ys) < 1e-6 for v in flat) and any(abs(v - ac) < 1e-6 for v in flat))
        assert len(flat) == 1 and flat[0] in (
            pytest.approx(ys / ac), pytest.approx(ref(H_, "SELECT AVG(h.yield_tons/f.acres) FROM harvests h "
                                                         "JOIN fields f ON f.field_id=h.field_id")[0][0]))
    else:
        assert refuses(r) and r.confidence.score <= 0.30


def test_current_implementation_clarifies_unsupported_ratio():
    # no ratio formula is implemented on purpose (acre grain / units unverified)
    r = ask(H_, "Total yield tons per acre")
    assert refuses(r)
    assert "ratio" in r.explanation.lower()


def test_ratio_typecheck_flags_two_sums():
    from types import SimpleNamespace as NS
    from insightflow.semantics import SemanticSpec, typecheck
    from insightflow.semantics.spec import MetricSpec, Grounded
    m = MetricSpec("m", "M", "sum", "", [Grounded("yield_tons", "t", "anchor", "REAL", "quantity")])
    sp = SemanticSpec(question="q", intent="direct_kpi", requested_shape="scalar", shape="scalar", metrics=[m])
    ds = NS(table="t", rel=None, kind="uploaded", dates=[], date_choice=None, flag_columns=(),
            columns={"acres": NS(role="measure"), "yield_tons": NS(role="measure")})
    rules = {f.rule for f in typecheck(sp, "total yield tons per acre", ds) if f.severity == "violation"}
    assert "ratio_unsupported" in rules
    m2 = MetricSpec("m", "M", "ratio", "", [Grounded("yield_tons", "t", "anchor", "REAL", "quantity")])
    sp.metrics = [m2]
    assert "ratio_unsupported" not in {f.rule for f in typecheck(sp, "total yield tons per acre", ds)}


# ------------------------------------------------------------ Task 4: related classes
def test_negated_value_filter_keeps_other_groups():
    r = ask(S_, SEALED["S18"][3])
    assert r.decision.action in OK or refuses(r)
    if r.decision.action in OK:
        assert scalar(r) == pytest.approx(sealed_ref("S18"))


def test_flag_count_not_money():
    r = ask(A_, "How many flights were cancelled?")
    assert r.decision.action in OK and scalar(r) == ref(A_, "SELECT COUNT(*) FROM flights WHERE is_cancelled=1")[0][0]


def test_entity_count_is_distinct():
    r = ask(S_, SEALED["S19"][3])
    assert r.decision.action in OK
    assert scalar(r) == sealed_ref("S19")
    assert scalar(r) < ref(S_, "SELECT COUNT(*) FROM invoices")[0][0]    # not a transaction count


def test_scalar_vs_grouped_shape():
    assert len(ask(A_, "Total fare").result.rows) == 1
    g = ask(A_, "Total fare by alliance")
    assert len(g.result.rows) == 3                      # includes the NULL group


def test_null_group_not_dropped():
    r = ask(A_, "Total fare by alliance")
    assert sum(float(x[1]) for x in r.result.rows) == pytest.approx(
        ref(A_, "SELECT SUM(fare_amt) FROM flights")[0][0])


def test_fanout_filter_does_not_double_count():
    r = ask(S_, "Total usd for accounts with Open tickets")
    if r.decision.action in OK:
        assert scalar(r) == pytest.approx(sealed_ref('S09'))
    else:
        assert refuses(r)


def test_fanout_grouping_is_not_answered():
    assert refuses(ask(S_, "Total usd by priority"))


def test_ambiguous_date_role_not_guessed():
    assert refuses(ask(S_, "Total usd in June 2025"))
    r = ask(S_, "Total usd for invoices paid in June 2025")
    assert r.decision.action in OK and scalar(r) == pytest.approx(97071.02)


def test_numeric_threshold_on_related_table():
    r = ask(F_, "Average moisture for fields larger than 100 acres")
    if r.decision.action in OK:                          # known coverage gap: currently clarifies
        assert scalar(r) == pytest.approx(sealed_ref('R15'))
    else:
        assert refuses(r)


def test_related_table_flag():
    r = ask(S_, "Total usd for trial subscriptions")
    if r.decision.action in OK:
        assert scalar(r) == pytest.approx(sealed_ref('S08'))
    else:
        assert refuses(r)


def test_unknown_value_not_silently_dropped():
    r = ask(A_, "Total fare for Lufthansa")
    assert refuses(r)


def test_not_been_paid_is_a_null_date_test():
    r = ask(S_, "How many invoices have not been paid?")
    if r.decision.action in OK:
        assert scalar(r) == 115 and "IS NULL" in r.sql.upper()
    else:
        assert refuses(r)


def test_negated_flag_count():
    r = ask(A_, "How many flights were not delayed?")
    assert r.decision.action in OK
    assert scalar(r) == FR_count(A_, "SELECT COUNT(*) FROM flights WHERE is_delayed=0")


def FR_count(db, sql):
    return ref(db, sql)[0][0]
