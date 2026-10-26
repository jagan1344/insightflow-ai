"""Unit and behaviour tests for the typed-IR engine (insightflow.engine). Uses the development schemas from
research_improvement/architecture_recovery/devsets, built into a temporary directory."""
import pathlib
import sqlite3
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research_improvement" / "architecture_recovery" / "devsets"))

import dev_schemas as D  # noqa: E402

from insightflow.engine import schema_model as S  # noqa: E402
from insightflow.engine.compiler import CompileError, Compiler  # noqa: E402
from insightflow.engine.engine import answer  # noqa: E402
from insightflow.engine.ir import Agg, Arith, Cmp, Col, Exists, InSet, Lit, Measure, Query  # noqa: E402
from insightflow.engine.verify import verify  # noqa: E402

ANCHOR = {"bikes": "rentals", "school": "exam_results", "shop": "orders", "support": "tickets"}


@pytest.fixture(scope="module")
def dbs(tmp_path_factory):
    d = tmp_path_factory.mktemp("enginedb")
    old = D.DATA
    D.DATA = d
    try:
        out = {s: {k: str(v) for k, v in D.build_all(s).items()} for s in ("abbr", "full")}
    finally:
        D.DATA = old
    return out


def model(dbs, dom, scheme="abbr"):
    return S.get(dbs[scheme][dom], ANCHOR[dom])


def ask(dbs, dom, q, scheme="abbr"):
    return answer(q, dbs[scheme][dom], ANCHOR[dom])


def ref(dbs, dom, sql, scheme="abbr"):
    con = sqlite3.connect(dbs[scheme][dom])
    try:
        return [tuple(r) for r in con.execute(sql).fetchall()]
    finally:
        con.close()


# ---------------------------------------------------------------- schema model
def test_established_and_inferred_are_separate(dbs):
    m = model(dbs, "support")
    d = m.describe()
    declared = {e["edge"] for e in d["edges"] if e["declared"]}
    inferred = {e["edge"] for e in d["edges"] if not e["declared"]}
    assert "tickets.acct_id -> accounts.acct_id" in declared
    assert any(x.startswith("tickets.resolved_by_agent_id -> agents.agent_id") for x in inferred)
    assert "inferred" in d and "established" in d


def test_fk_inferred_from_vowelless_abbreviation(dbs):
    m = model(dbs, "bikes")
    roles = {p.role for p in m.paths["stations"]}
    assert roles == {"start_stn_id", "end_stn_id"}


def test_no_fk_without_name_evidence(dbs):
    # grader_id / proctor_id hold teacher ids but nothing in the names says so: never joined
    m = model(dbs, "school")
    assert "teachers" not in m.paths


def test_column_kinds(dbs):
    m = model(dbs, "shop")
    assert m.col("orders", "is_gift").kind == "boolean"
    assert m.col("orders", "order_dt").kind == "date"
    assert m.col("orders", "gross_amt").kind == "measure" and m.col("orders", "gross_amt").money
    assert m.col("orders", "ship_mode").kind == "category"


# ---------------------------------------------------------------- compiler safety
def test_literals_are_parameters(dbs):
    m = model(dbs, "shop")
    q = Query(measures=[Measure("n", Agg("count"))], filters=[InSet(Col("orders", "ship_mode"), ("x'); DROP TABLE orders;--",))])
    sql, params = Compiler(m).compile(q)
    assert "DROP" not in sql and params == ["x'); DROP TABLE orders;--"]


def test_bad_identifier_rejected(dbs):
    m = model(dbs, "shop")
    q = Query(measures=[Measure("n", Agg("sum", Col("orders", 'gross_amt" FROM x --')))])
    with pytest.raises((CompileError, KeyError)):
        Compiler(m).compile(q)


def test_division_is_guarded(dbs):
    m = model(dbs, "shop")
    q = Query(measures=[Measure("r", Arith("/", Agg("sum", Col("orders", "disc_amt")), Agg("sum", Col("orders", "gross_amt"))))])
    sql, _ = Compiler(m).compile(q)
    assert "NULLIF" in sql


def test_one_to_many_only_inside_exists(dbs):
    m = model(dbs, "shop")
    p = m.paths["returns"][0]
    q = Query(measures=[Measure("n", Agg("count"))], filters=[Exists(p, InSet(Col("returns", "reason"), ("damaged",)))])
    sql, _ = Compiler(m).compile(q)
    assert "EXISTS" in sql and "JOIN" not in sql.split("WHERE")[0].replace("LEFT JOIN", "")


# ---------------------------------------------------------------- verifier
def test_verifier_rejects_sum_of_category(dbs):
    m = model(dbs, "shop")
    q = Query(measures=[Measure("x", Agg("sum", Col("orders", "ship_mode")))])
    assert verify(q, m)


def test_verifier_rejects_fanout_column_outside_exists(dbs):
    m = model(dbs, "shop")
    p = m.paths["order_lines"][0]
    q = Query(measures=[Measure("x", Agg("sum", Col("order_lines", "qty", p)))])
    assert any("one-to-many" in v for v in verify(q, m))


def test_verifier_rejects_ordered_comparison_on_category(dbs):
    m = model(dbs, "shop")
    q = Query(measures=[Measure("n", Agg("count"))], filters=[Cmp(Col("orders", "ship_mode"), ">", Lit(3))])
    assert verify(q, m)


# ---------------------------------------------------------------- behaviour
CASES = [
    ("shop", "How many orders have not shipped?", "SELECT COUNT(*) FROM orders WHERE ship_dt IS NULL"),
    ("shop", "How many orders were returned?",
     "SELECT COUNT(*) FROM orders o WHERE EXISTS (SELECT 1 FROM returns r WHERE r.order_id=o.order_id)"),
    ("shop", "Gross amount of orders that were never returned",
     "SELECT SUM(gross_amt) FROM orders o WHERE NOT EXISTS (SELECT 1 FROM returns r WHERE r.order_id=o.order_id)"),
    ("bikes", "Total of duration times per minute rate", "SELECT SUM(dur_min*per_min_rate) FROM rentals"),
    ("bikes", "How many rentals did not use a helmet?", "SELECT COUNT(*) FROM rentals WHERE helmet_used=0"),
    ("support", "How many tickets were never reopened?", "SELECT COUNT(*) FROM tickets WHERE reopen_cnt=0"),
    ("support", "How many tickets missed the SLA?", "SELECT COUNT(*) FROM tickets WHERE sla_met=0"),
    ("support", "Number of tickets opened by Ava Moss",
     "SELECT COUNT(*) FROM tickets t JOIN agents a ON a.agent_id=t.opened_by_agent_id WHERE a.agent_nm='Ava Moss'"),
    ("school", "Average score for exams without any accommodation",
     "SELECT AVG(score_pct) FROM exam_results e WHERE NOT EXISTS (SELECT 1 FROM accommodations a WHERE a.result_id=e.result_id)"),
]


@pytest.mark.parametrize("dom,q,sql", CASES)
def test_answers_match_reference(dbs, dom, q, sql):
    r = ask(dbs, dom, q)
    assert r.status == "answer", r.message
    got, exp = r.rows, ref(dbs, dom, sql)
    assert len(got) == len(exp) == 1 and abs((got[0][-1] or 0) - (exp[0][-1] or 0)) < 1e-6


@pytest.mark.parametrize("dom,q", [
    ("bikes", "Total fare by station"),               # start or end station
    ("support", "Tickets by agent"),                  # opened by or resolved by
    ("shop", "Monthly gross amount"),                 # order date or ship date
    ("shop", "Total revenue"),                        # not a schema word
    ("bikes", "Total fare in the last 7 days"),       # relative date
    ("school", "Average score by grader"),            # id without a lookup
    ("school", "Average credit hours"),               # lookup attribute, weighting unclear
    ("bikes", "Monthly rentals in 2025"),             # 'monthly' is also a stored plan value
])
def test_asks_instead_of_guessing(dbs, dom, q):
    assert ask(dbs, dom, q).status in ("clarify", "unsupported")


def test_dangling_negation_is_never_dropped(dbs):
    r = ask(dbs, "shop", "Total gross amount not for the dog")
    assert r.status != "answer"


def test_trace_is_inspectable(dbs):
    r = ask(dbs, "shop", "Total gross amount for gift orders")
    t = r.trace()
    assert r.status == "answer" and "?" not in r.display_sql
    assert any("is_gift" in e["grounded_to"] for e in t["evidence"])
    assert "not a calibrated probability" in t["reliability"]["note"]


@pytest.mark.parametrize("dom,q", [
    ("shop", "Total discount amount by region"), ("support", "Average csat score by channel"),
    ("bikes", "How many rentals had no issues?"), ("school", "Number of exams by grade level"),
])
def test_renaming_does_not_change_answers(dbs, dom, q):
    a, b = ask(dbs, dom, q, "abbr"), ask(dbs, dom, q, "full")
    if dom == "support":       # csat exists only in the abbreviated scheme
        assert a.status == "answer"
        return
    assert a.status == b.status == "answer" and sorted(map(str, a.rows)) == sorted(map(str, b.rows))


def test_database_opened_read_only(dbs):
    r = ask(dbs, "shop", "How many orders were placed?")
    assert r.status == "answer"
    con = sqlite3.connect(f"file:{dbs['abbr']['shop']}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        con.execute("DELETE FROM orders")
    con.close()


# ---------------------------------------------------------------- readings of an ambiguity
def test_ambiguity_that_does_not_change_the_result_is_answered(tmp_path):
    p = tmp_path / "ev.db"
    con = sqlite3.connect(p)
    con.executescript("CREATE TABLE events (event_id INTEGER PRIMARY KEY, created_dt TEXT NOT NULL, updated_dt TEXT NOT NULL, amt REAL NOT NULL);")
    con.executemany("INSERT INTO events VALUES (?,?,?,?)", [(i, f"2025-0{1 + i % 5}-01", f"2025-0{1 + i % 5}-15", i * 1.5) for i in range(1, 40)])
    con.commit(); con.close()
    r = answer("Total amount in 2025", str(p), "events")
    assert r.status == "answer"
    assert any("all give the same result" in a for a in r.query.assumptions)


def test_ambiguity_that_changes_the_result_shows_each_reading(dbs):
    r = ask(dbs, "bikes", "Total fare in 2025")
    assert r.status == "clarify"
    a = ref(dbs, "bikes", "SELECT SUM(fare_amt) FROM rentals WHERE start_ts >= '2025-01-01' AND start_ts < '2026-01-01'")[0][0]
    b = ref(dbs, "bikes", "SELECT SUM(fare_amt) FROM rentals WHERE end_ts >= '2025-01-01' AND end_ts < '2026-01-01'")[0][0]
    assert a != b and f"{a:,.2f}" in r.message and f"{b:,.2f}" in r.message
