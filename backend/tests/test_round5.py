"""Round 5: the five Schema-F first-run silent errors (G1) and their relatives.
Independent sqlite3 oracles; the sealed G1 record is never edited."""
import pathlib, sqlite3, sys
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_round4b import lib, ask, sql1, val  # noqa: E402,F401


# ---- the five G1 errors -----------------------------------------------------
def test_F08_branch_by_two_routes_is_asked_with_both_values(lib):
    p = lib("library", "loans")
    r = ask("How many loans by branch?")
    assert r.decision.action == "CLARIFY"
    assert "Central Library: 160" in r.explanation and "Central Library: 122" in r.explanation


def test_F09_filter_through_two_routes_is_asked(lib):
    p = lib("library", "loans")
    r = ask("Total late fee for Springfield")
    a = sql1(p, "SELECT SUM(l.late_fee) FROM loans l JOIN branches b ON b.branch_id=l.branch_id WHERE b.city='Springfield'")[0][0]
    b = sql1(p, "SELECT SUM(l.late_fee) FROM loans l JOIN members m ON m.member_id=l.member_id JOIN branches b ON b.branch_id=m.branch_id WHERE b.city='Springfield'")[0][0]
    assert a != b and r.decision.action == "CLARIFY"
    assert f"{a:,.2f}" in r.explanation and f"{b:,.2f}" in r.explanation


def test_F17_equal_under_every_reading_is_answered(lib):
    p = lib("library", "loans")
    r = ask("How many distinct books were borrowed in 2025?")
    assert r.decision.action in ("ANSWER", "WARN") and val(r) == 9
    assert any(n.startswith("ambiguity_immaterial") for n in r.notes)


def test_F24_top_n_never_ranks_the_null_group(lib):
    p = lib("library", "loans")
    r = ask("Top 3 genres by number of loans")
    assert None not in [row[0] for row in r.result.rows]


def test_F32_returned_late_is_not_a_plain_count(lib):
    lib("library", "loans")
    assert ask("How many loans were returned late?").decision.action == "CLARIFY"


# ---- relatives: dropped qualifiers -----------------------------------------
@pytest.mark.parametrize("q", ["How many loans were overdue?",
                               "How many loans are still outstanding?"])
def test_unmapped_adjective_is_asked_not_ignored(lib, q):
    lib("library", "loans")
    r = ask(q)
    assert r.decision.action == "CLARIFY" and "maps to this data" in r.explanation


def test_unmapped_participle_is_flagged_not_silent(lib):
    p = lib("library", "loans")
    r = ask("How many loans were renewed?")
    assert r.decision.action == "WARN" and "renewed" in r.decision.reason


def test_verbs_that_just_describe_rows_do_not_trigger(lib):
    p = lib("library", "loans")
    r = ask("How many loans were made in March 2025?")
    assert r.decision.action == "ANSWER"
    assert val(r) == sql1(p, "SELECT COUNT(*) FROM loans WHERE loan_date>='2025-03-01' AND loan_date<'2025-04-01'")[0][0]


# ---- relatives: dates -------------------------------------------------------
@pytest.mark.parametrize("q,pred", [
    ("How many loans in the first half of 2025?", "loan_date>='2025-01-01' AND loan_date<'2025-07-01'"),
    ("How many loans in the second half of 2025?", "loan_date>='2025-07-01' AND loan_date<'2026-01-01'"),
    ("How many loans in H2 2025?", "loan_date>='2025-07-01' AND loan_date<'2026-01-01'"),
    ("How many loans in the third quarter of 2025?", "loan_date>='2025-07-01' AND loan_date<'2025-10-01'"),
    ("How many loans were made on 2025-03-15?", "loan_date>='2025-03-15' AND loan_date<'2025-03-16'"),
])
def test_half_quarter_and_exact_day(lib, q, pred):
    p = lib("library", "loans")
    r = ask(q)
    assert r.decision.action in ("ANSWER", "WARN")
    assert val(r) == sql1(p, f"SELECT COUNT(*) FROM loans WHERE {pred}")[0][0]


@pytest.mark.parametrize("q,pred", [
    ("How many orders were shipped?", "ship_date IS NOT NULL"),
    ("How many orders have not shipped yet?", "ship_date IS NULL"),
])
def test_date_participle_means_has_or_lacks_a_date(tmp_path, q, pred):
    import json, shutil
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "evaluation" / "v3"))
    import fixtures_v4 as F4
    from insightflow.config import settings
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.dataset_registry import (DEMO_ID, bootstrap, register_relational, set_active)
    from insightflow.knowledge.schema_agent import refresh_schema
    old = settings.database_url
    try:
        src = F4.build_d(tmp_path / "r.db")
        settings.database_url = f"sqlite:///{src}"
        reset_engine(); bootstrap()
        set_active(register_relational("retail@orders", "orders")); reset_engine(); refresh_schema()
        r = ask(q)
        assert val(r) == sql1(src, f"SELECT COUNT(*) FROM orders WHERE {pred}")[0][0]
    finally:
        settings.database_url = old; reset_engine()
        try: set_active(DEMO_ID)
        except Exception: pass


# ---- relatives: wrong aggregate / ignored cues -----------------------------
def test_percentage_question_is_not_answered_with_a_sum(lib):
    lib("library", "loans")
    assert ask("What percent of loans had a late fee?").decision.action == "CLARIFY"


def test_top_n_inside_an_aggregate_is_not_ignored(lib):
    lib("hr", "employees")
    assert ask("What is the average salary of the top 5 highest paid employees?").decision.action == "CLARIFY"


def test_and_not_is_an_exclusion(lib):
    p = lib("library", "loans")
    r = ask("Total late fee for Gold tier members and not Silver")
    exp = sql1(p, "SELECT SUM(l.late_fee) FROM loans l JOIN members m ON m.member_id=l.member_id WHERE m.tier='Gold' AND (m.tier IS NULL OR m.tier NOT IN ('Silver'))")[0][0]
    assert abs(val(r) - exp) < 1e-6


def test_count_with_adjective_binds_the_base_rows(lib):
    p = lib("hr", "employees")
    r = ask("How many active employees are in Engineering?")
    assert val(r) == sql1(p, "SELECT COUNT(*) FROM employees e JOIN departments d ON d.dept_id=e.dept_id WHERE d.dept_name='Engineering' AND e.status='Active'")[0][0]
