"""Failure classes first seen on the sealed schema-F run (G1), pinned with
independent sqlite3 oracles. The G1 record itself is never edited."""
import pathlib
import shutil
import sqlite3
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evaluation" / "v3"))
import fixtures_f as FF  # noqa: E402
import fixtures_v4 as F4  # noqa: E402


@pytest.fixture()
def lib(tmp_path):
    from insightflow.config import settings
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.dataset_registry import (
        DEMO_ID, bootstrap, register_relational, set_active)
    from insightflow.knowledge.schema_agent import refresh_schema
    old = settings.database_url
    src = {"library": FF.build_f(tmp_path / "l.db"), "hr": F4.build_e(tmp_path / "h.db")}

    def activate(db, anchor):
        dst = tmp_path / f"{db}_{anchor}.db"
        shutil.copy(src[db], dst)
        settings.database_url = f"sqlite:///{dst}"
        reset_engine(); bootstrap()
        i = register_relational(f"{db}@{anchor}", anchor)
        reset_engine(); refresh_schema(); set_active(i)
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


def test_value_with_ampersand_and_hyphen_is_not_unknown(lib):
    p = lib("library", "loans")
    r = ask("How many loans of books in Sci-Fi & Fantasy?")
    exp = sql1(p, "SELECT COUNT(*) FROM loans l JOIN books b ON b.book_id=l.book_id JOIN genres g ON g.genre_id=b.genre_id WHERE g.genre_name='Sci-Fi & Fantasy'")[0][0]
    assert val(r) == exp


def test_top_n_does_not_rank_the_null_group(lib):
    p = lib("library", "loans")
    r = ask("Top 3 genres by number of loans")
    exp = sql1(p, "SELECT g.genre_name, COUNT(*) x FROM loans l JOIN books b ON b.book_id=l.book_id JOIN genres g ON g.genre_id=b.genre_id GROUP BY 1 ORDER BY x DESC LIMIT 3")
    assert [(row[0], float(row[-1])) for row in r.result.rows] == [(a, float(b)) for a, b in exp]


def test_inflected_column_wording_finds_the_null_column(lib):
    p = lib("library", "loans")
    r = ask("How many loans have no return date?")
    assert val(r) == sql1(p, "SELECT COUNT(*) FROM loans WHERE returned_date IS NULL")[0][0]


def test_two_routes_to_a_dimension_that_disagree_are_asked(lib):
    p = lib("library", "loans")
    r = ask("How many loans by branch?")
    assert r.decision.action == "CLARIFY"
    assert "via" in r.explanation and "Which did you mean" in r.explanation


def test_two_routes_that_agree_are_not_asked(lib, tmp_path):
    p = lib("library", "loans")
    with sqlite3.connect(str(p)) as c:       # member home branch == loan branch
        c.execute("UPDATE members SET branch_id = 1")
        c.execute("UPDATE loans SET branch_id = 1")
    r = ask("How many loans by branch?")
    assert r.decision.action in ("ANSWER", "WARN")
    assert any(n.startswith("path_choice_immaterial") for n in r.notes)


def test_mentioned_parent_entity_is_not_a_missing_table(lib):
    p = lib("library", "loans")
    r = ask("How many distinct members borrowed books?")
    assert val(r) == sql1(p, "SELECT COUNT(DISTINCT member_id) FROM loans")[0][0]


def test_dropped_qualifier_words_are_not_ignored(lib):
    lib("library", "loans")
    r = ask("How many loans were returned late?")
    assert r.decision.action == "CLARIFY"


def test_participle_numeric_filter(lib):
    p = lib("library", "loans")
    r = ask("Total late fee for books priced over 20")
    assert abs(val(r) - sql1(p, "SELECT SUM(l.late_fee) FROM loans l JOIN books b ON b.book_id=l.book_id WHERE b.price>20")[0][0]) < 1e-6


def test_row_filter_after_had(lib):
    p = lib("library", "loans")
    r = ask("How many loans had a late fee over 5?")
    assert val(r) == sql1(p, "SELECT COUNT(*) FROM loans WHERE late_fee>5")[0][0]


@pytest.mark.parametrize("q,pred", [
    ("How many employees were hired after 2022?", "hire_date>='2023-01-01'"),
    ("How many employees were hired before 2023?", "hire_date<'2023-01-01'"),
    ("How many employees were hired since 2023?", "hire_date>='2023-01-01'"),
    ("How many employees were hired until 2022?", "hire_date<'2023-01-01'"),
    ("How many employees were hired between 2022 and 2023?", "hire_date>='2022-01-01' AND hire_date<'2024-01-01'"),
])
def test_year_bounds_are_not_whole_year_filters(lib, q, pred):
    p = lib("hr", "employees")
    r = ask(q)
    assert r.decision.action in ("ANSWER", "WARN")
    assert val(r) == sql1(p, f"SELECT COUNT(*) FROM employees WHERE {pred}")[0][0]


def test_inference_caveat_names_only_joins_actually_used(lib):
    lib("library", "loans")
    r = ask("Top 3 genres by number of loans")
    assert "book_authors" not in r.decision.reason and "book_authors" not in r.explanation


def test_average_per_entity_is_not_silently_a_per_row_list(lib):
    lib("library", "loans")
    r = ask("Average late fee per member")
    assert r.decision.action == "CLARIFY"
    assert "overall total" in r.explanation and "each" in r.explanation
    # "per loan" names the base row itself: still a single average
    p = lib("library", "loans")
    r2 = ask("Average late fee per loan")
    assert abs(val(r2) - sql1(p, "SELECT AVG(late_fee) FROM loans")[0][0]) < 1e-9
