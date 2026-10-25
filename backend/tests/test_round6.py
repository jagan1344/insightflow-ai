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


def test_flag_exclusion_keeps_the_zero_rows():
    r = ask("airline@flights", "Total fare excluding cancelled flights")
    assert r.decision.action in ("ANSWER", "WARN")
    assert "is_cancelled" in r.sql and "0" in r.sql


def test_per_measure_ratio_is_not_two_sums():
    r = ask("farm@harvests", "Total yield tons per acre")
    assert r.decision.action in ("CLARIFY", "ABSTAIN")


def test_not_been_paid_is_a_null_date_test():
    r = ask("saas@invoices", "How many invoices have not been paid?")
    assert r.decision.action in ("ANSWER", "WARN")
    assert "IS NULL" in r.sql.upper()


def test_negated_flag_count():
    r = ask("airline@flights", "How many flights were not delayed?")
    assert r.decision.action in ("ANSWER", "WARN")
    assert r.result.rows[0][0] == FR_count("airline@flights", "SELECT COUNT(*) FROM flights WHERE is_delayed=0")


def FR_count(db, sql):
    import run_eval as R
    return R.ref(db, sql)[0][0]
