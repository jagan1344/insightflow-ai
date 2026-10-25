"""Semantic layer: typed spec, semantic type checks, preservation checks, and
end-to-end behaviour on unfamiliar relational schemas (oracles: sqlite3)."""
import pathlib, sqlite3, sys
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_round4b import lib, ask, sql1, val  # noqa: E402,F401
from test_round5b import r5  # noqa: E402,F401
from insightflow.semantics import SemanticSpec, requested_shape, preserve, typecheck  # noqa: E402
from insightflow.semantics.spec import MetricSpec, Grounded, FilterSpec, TimeSpec, JoinSpec  # noqa: E402


def spec(**kw):
    base = dict(question="q", intent="direct_kpi", requested_shape="scalar", shape="scalar")
    base.update(kw)
    return SemanticSpec(**base)


def metric(agg="sum", col="amount", sem="money", origin="anchor"):
    return MetricSpec("m", "M", agg, "", [Grounded(col, "t", origin, "REAL", sem)] if col else [])


DS = NS(table="t", rel=None, kind="uploaded", columns={}, dates=[], date_choice=None, flag_columns=())


# ------------------------------------------------------------------ type checks
class TestTypeCheck:
    def rules(self, sp, q="q"):
        return {f.rule for f in typecheck(sp, q, DS) if f.severity == "violation"}

    def test_flag_is_not_an_amount(self):
        assert "flag_used_as_quantity" in self.rules(spec(metrics=[metric("sum", "refunded", "flag")]))

    def test_identifier_is_not_a_quantity(self):
        assert "identifier_used_as_quantity" in self.rules(spec(metrics=[metric("avg", "cust_id", "id")]))

    def test_ungrounded_reference_is_rejected(self):
        assert "unresolved_reference" in self.rules(spec(unresolved=["ungrounded_column:foo"]))

    def test_scalar_question_with_breakdown(self):
        assert "shape_scalar_expected" in self.rules(spec(requested_shape="scalar", shape="grouped"))

    def test_grouped_question_with_scalar(self):
        assert "shape_breakdown_expected" in self.rules(spec(requested_shape="grouped", shape="scalar"))

    def test_unspecified_shape_is_not_policed(self):
        assert not self.rules(spec(requested_shape="unspecified", shape="grouped"))

    def test_guessed_date_role(self):
        t = TimeSpec("d", "t", "2025-01", "2025-01", "guessed")
        assert "date_role_guessed" in self.rules(spec(time=t))
        assert not self.rules(spec(time=TimeSpec("d", "t", "2025-01", "2025-01", "named")))

    def test_unsafe_join_is_rejected_but_semi_join_is_fine(self):
        assert "unsafe_join" in self.rules(spec(joins=[JoinSpec("c", "a.x", False, False, False)]))
        assert not self.rules(spec(joins=[JoinSpec("c", "a.x", False, False, True)]))

    def test_requested_shapes(self):
        assert requested_shape("What is the total revenue?") == "scalar"
        assert requested_shape("Revenue by region") == "grouped"
        assert requested_shape("Top 3 products by revenue") == "ranking"
        assert requested_shape("Revenue trend by month") == "trend"
        assert requested_shape("Compare June versus May") == "comparison"
        assert requested_shape("Total paid by students from Ohio") == "scalar"


# ---------------------------------------------------------------- preservation
class TestPreserve:
    def rules(self, sp, sql, cols, rows, expl="x\n\nTotal is 10.", ds=DS):
        return {f.rule for f in preserve(sp, sql, cols, rows, expl, ds)}

    def test_wrong_aggregate(self):
        sp = spec(metrics=[metric("avg", "amount")])
        assert "measure_not_preserved" in self.rules(sp, 'SELECT SUM("amount") FROM t', ["a"], [(10,)])

    def test_count_vs_count_distinct(self):
        sp = spec(metrics=[metric("count_distinct", "cust")])
        assert "measure_not_preserved" in self.rules(sp, "SELECT COUNT(*) FROM t", ["a"], [(10,)])
        assert not self.rules(sp, 'SELECT COUNT(DISTINCT "cust") FROM t', ["a"], [(10,)])

    def test_missing_value_filter(self):
        sp = spec(metrics=[metric()], filters=[FilterSpec("value", "region", "t", values=["East"])])
        assert "filter_not_preserved" in self.rules(sp, 'SELECT SUM("amount") FROM t', ["a"], [(10,)])
        assert not self.rules(sp, "SELECT SUM(\"amount\") FROM t WHERE \"region\" = 'East'", ["a"], [(10,)])

    def test_exclusion_must_stay_negated(self):
        sp = spec(metrics=[metric()], filters=[FilterSpec("exclusion", "region", "t", "exclude", "not in", ["East"])])
        assert "exclusion_not_preserved" in self.rules(sp, "SELECT SUM(\"amount\") FROM t WHERE \"region\" IN ('East')", ["a"], [(10,)])

    def test_null_state_polarity(self):
        sp = spec(metrics=[metric()], filters=[FilterSpec("null_state", "shipped", "t", "exclude", "null", [])])
        assert "filter_not_preserved" in self.rules(sp, 'SELECT SUM("amount") FROM t WHERE "shipped" IS NOT NULL', ["a"], [(1,)])

    def test_time_bounds_month_level(self):
        sp = spec(metrics=[metric()], time=TimeSpec("d", "t", "2025-03", "2025-03", "unique"))
        ok = "SELECT SUM(\"amount\") FROM t WHERE d >= '2025-03-01' AND d < '2025-04-01'"
        assert not self.rules(sp, ok, ["a"], [(1,)], "x\n\nTotal is 1.")
        assert "time_not_preserved" in self.rules(sp, 'SELECT SUM("amount") FROM t', ["a"], [(1,)])

    def test_grouping_and_ranking(self):
        sp = spec(requested_shape="ranking", shape="ranking", intent="top_n", limit=3,
                  metrics=[metric()], dims=[Grounded("region", "t", "anchor", "TEXT", "category")])
        sql = 'SELECT "region", SUM("amount") FROM t'
        r = self.rules(sp, sql, ["r", "a"], [("E", 1)])
        assert {"grouping_not_preserved", "ranking_not_preserved"} <= r

    def test_unexpected_extra_column(self):
        sp = spec(metrics=[metric()])
        assert "unexpected_columns" in self.rules(sp, 'SELECT SUM("amount"), COUNT(*) FROM t', ["a", "b"], [(10, 3)])

    def test_scalar_returning_many_rows(self):
        sp = spec(metrics=[metric()])
        assert "shape_violation" in self.rules(sp, 'SELECT SUM("amount") FROM t', ["a"], [(1,), (2,)])

    def test_answer_text_must_match_the_result(self):
        sp = spec(metrics=[metric()])
        assert "answer_not_faithful" in self.rules(sp, 'SELECT SUM("amount") FROM t', ["a"], [(10,)],
                                                   "hdr\n\nTotal Amount is 99.")
        assert not self.rules(sp, 'SELECT SUM("amount") FROM t', ["a"], [(1234.5,)],
                              "hdr\n\nTotal Amount is 1,234.50.")


# -------------------------------------------------------------- end to end
def test_spec_is_attached_and_grounded(lib):
    lib("library", "loans")
    r = ask("Total late fee by genre")
    sp = r.diagnostics["semantic_spec"]
    assert sp["shape"] == "grouped" and sp["requested_shape"] == "grouped"
    assert sp["metrics"][0]["columns"][0]["origin"] == "anchor"
    assert sp["dims"][0]["origin"] == "related" and sp["dims"][0]["table"] == "genres"
    assert any(j["table"] == "genres" and j["safe"] for j in sp["joins"])
    assert not [f for f in r.diagnostics["semantic_findings"] if f["severity"] == "violation"]


def test_exists_filter_is_recorded_as_semi_join(lib):
    lib("library", "loans")
    r = ask("How many loans of books by Ursula K. Le Guin?")
    sp = r.diagnostics["semantic_spec"]
    assert any(j["semi"] for j in sp["joins"]) and r.decision.action in ("ANSWER", "WARN")


def test_binary_flag_is_a_filter_never_money(r5):
    p = r5("events", "tickets")
    r = ask("What is the total refunded amount?")
    assert "SUM(\"tickets\".\"refunded\")" not in (r.sql or "") and "sum(refunded)" not in (r.sql or "").lower()
    r2 = ask("How many tickets were refunded?")
    assert val(r2) == sql1(p, "SELECT COUNT(*) FROM tickets WHERE refunded=1")[0][0]


def test_customer_count_is_never_a_transaction_count(r5):
    r5("bank", "transactions")
    r = ask("How many customers made a transaction?")
    assert r.decision.action != "ANSWER" or val(r) != 800


def test_scalar_and_grouped_questions_keep_their_shape(r5):
    r5("bank", "transactions")
    a = ask("What is the total amount?")
    b = ask("Total amount by account type")
    assert len(a.result.rows) == 1 and len(b.result.rows) == 3


def test_ambiguous_status_word(r5):
    r5("events", "tickets")
    assert ask("Total price for events held in March 2025").decision.action == "CLARIFY"
    assert ask("Total price for Held events").decision.action in ("ANSWER", "WARN")


def test_two_join_paths_are_compared(lib):
    lib("library", "loans")
    assert ask("How many loans by branch?").decision.action == "CLARIFY"


def test_related_measure_has_an_explicit_assumption(lib):
    lib("hr", "assignments")  # hours is anchor; employees.salary is related
    r = ask("What is the total salary?")
    sp = r.diagnostics["semantic_spec"] if r.diagnostics.get("semantic_spec") else None
    if r.decision.action in ("ANSWER", "WARN") and sp:
        assert any("related-table measure" in a for a in sp["assumptions"]) or \
            any("counted once per" in r.explanation for _ in [0])


def test_date_role_is_never_guessed(r5):
    r5("factory", "work_orders")
    assert ask("Total units planned in June 2025").decision.action == "CLARIFY"


@pytest.mark.parametrize("q", ["Total amount by transaction type", "Average amount by transaction type"])
def test_abbreviated_column_found_by_full_words(r5, q):
    p = r5("bank", "transactions")
    r = ask(q)
    fn = "SUM" if q.startswith("Total") else "AVG"
    exp = dict(sql1(p, f"SELECT txn_type, {fn}(amount) FROM transactions GROUP BY 1"))
    assert r.decision.action in ("ANSWER", "WARN")
    assert {row[0]: row[-1] for row in r.result.rows} == pytest.approx(exp)


def test_nulls_empty_exclusion_unknown(r5):
    p = r5("bank", "transactions")
    assert val(ask("How many transactions have no channel?")) == sql1(p, "SELECT COUNT(*) FROM transactions WHERE channel IS NULL")[0][0]
    e = ask("Total amount for the Closed Branch")
    assert e.decision.action in ("ANSWER", "WARN") and (val(e) in (None, 0))
    assert abs(val(ask("Total amount excluding Fee transactions")) - sql1(p, "SELECT SUM(amount) FROM transactions WHERE txn_type<>'Fee'")[0][0]) < 1e-6
    assert ask("Total amount for the Atlantis Branch").decision.action == "CLARIFY"


def test_unsupported_and_out_of_scope(r5):
    r5("bank", "transactions")
    for q in ("Forecast next quarter's deposits", "Which branches had no customers?", "Delete all transactions"):
        assert ask(q).decision.action in ("CLARIFY", "ABSTAIN"), q
