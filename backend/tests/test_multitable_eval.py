"""Multi-table end-to-end regression on unseen relational fixtures.
Ground truth = independent sqlite3 reference SQL in evaluation/v3."""
import pathlib
import shutil
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evaluation" / "v3"))
import fixtures as F  # noqa: E402
import run_eval as R  # noqa: E402
from dev_questions import DEV  # noqa: E402

FACT = {"clinic": "visits", "logistics": "shipments"}


@pytest.fixture(scope="module")
def systems(tmp_path_factory):
    from insightflow.config import settings
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.dataset_registry import (
        DEMO_ID, bootstrap, register_relational, set_active)
    old = settings.database_url
    tmp = tmp_path_factory.mktemp("mt")
    paths = {"clinic": F.build_a(tmp / "clinic_src.db"),
             "logistics": F.build_b(tmp / "logistics_src.db")}
    yield paths, settings, reset_engine, bootstrap, register_relational, set_active
    settings.database_url = old
    reset_engine()
    try:
        set_active(DEMO_ID)
    except Exception:
        pass


def _activate(systems, db, tmp):
    paths, settings, reset_engine, bootstrap, register_relational, set_active = systems
    dst = tmp / f"{db}_live.db"
    shutil.copy(paths[db], dst)
    settings.database_url = f"sqlite:///{dst}"
    reset_engine(); bootstrap()
    ds_id = register_relational(db, FACT[db])
    reset_engine()
    from insightflow.knowledge.schema_agent import refresh_schema
    refresh_schema(); set_active(ds_id)
    return dst


@pytest.fixture(scope="module")
def outcomes(systems, tmp_path_factory):
    from insightflow.orchestrator import Orchestrator
    tmp = tmp_path_factory.mktemp("live")
    out = {}
    cur = None
    for db, qid, fam, q, kind, sql in DEV:
        if db != cur:
            _activate(systems, db, tmp); cur = db
        r = Orchestrator().ask(q)
        action = r.decision.action
        answered = action in ("ANSWER", "WARN")
        rows = list(r.result.rows) if (r.result and r.result.ok) else []
        if kind == "clarify":
            out[qid] = ("clarify_ok" if action in ("CLARIFY", "ABSTAIN")
                        else "silent_wrong")
        elif answered:
            exp = R.ref(db, sql)
            ok, _ = R.score(kind, rows, exp)
            out[qid] = "correct" if ok else "silent_wrong"
        else:
            out[qid] = "abstained"
    return out


def test_no_silent_wrong_answers(outcomes):
    assert [k for k, v in outcomes.items() if v == "silent_wrong"] == []


def test_all_required_clarifications(outcomes):
    cl = [d[1] for d in DEV if d[4] == "clarify"]
    assert all(outcomes[q] == "clarify_ok" for q in cl), outcomes


@pytest.mark.parametrize("qid", ["A03", "A04", "A05", "A07", "A09", "A10",
                                 "A11", "A13", "B03", "B05", "B06", "B09",
                                 "B10", "B13"])
def test_multitable_answer_matches_reference(outcomes, qid):
    assert outcomes[qid] == "correct"
