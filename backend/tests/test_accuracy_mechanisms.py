"""Unit tests for the accuracy-improvement mechanisms (vocabulary normalisation, wording checks,
composites, comparator suffixes, short codes). Each check has a positive and a negative case."""
from types import SimpleNamespace as NS

import pytest

from insightflow.semantics.wording import check_wording
from insightflow.plan.planner import _suffix_op, _short_code_ok, _flag_inclusion_columns


def rules(q, sql, **kw):
    return {f.rule for f in check_wording(q, sql, **kw)}


class TestComparator:
    def test_or_more_needs_ge(self):
        assert "comparator_not_preserved" in rules("claims with a deductible of 1000 or more",
                                                     "SELECT 1 WHERE deductible = 1000")
        assert "comparator_not_preserved" not in rules("claims with a deductible of 1000 or more",
                                                         "SELECT 1 WHERE deductible >= 1000")

    def test_at_least_and_above(self):
        assert "comparator_not_preserved" in rules("at least 5 nights", "SELECT 1 WHERE n < 5")
        assert "comparator_not_preserved" not in rules("above 40", "SELECT 1 WHERE sq_m > 40")

    def test_suffix_parser(self):
        q = "rated 4.8 or higher"
        assert _suffix_op(q, q.index("4.8") + 3, "=") == ">="
        q = "10 or less"
        assert _suffix_op(q, 2, "=") == "<="
        q = "exactly 10 trips"
        assert _suffix_op(q, q.index("10") + 2, "=") == "="


class TestNegatedValue:
    DS = None

    def test_value_kept_despite_negation(self, monkeypatch):
        import insightflow.plan.planner as P
        monkeypatch.setattr(P, "_value_index", lambda ds: {"cash": [("pay_method", "Cash")]})
        ds = NS(kind="uploaded")
        assert "negated_value_kept" in rules("trips not paid in cash",
                                             "SELECT COUNT(*) FROM t WHERE pay_method = 'Cash'", ds=ds)
        assert "negated_value_kept" not in rules("trips not paid in cash",
                                                 "SELECT COUNT(*) FROM t WHERE (pay_method IS NULL OR pay_method NOT IN ('Cash'))", ds=ds)
        assert "negated_value_kept" not in rules("trips not paid in cash",
                                                 "SELECT COUNT(*) FROM t WHERE NOT EXISTS (SELECT 1 FROM x WHERE x.m = 'Cash')", ds=ds)
        assert "negated_value_kept" not in rules("trips paid in cash",
                                                 "SELECT COUNT(*) FROM t WHERE pay_method = 'Cash'", ds=ds)


class TestRateAndVague:
    def test_rate_needs_division(self):
        assert "rate_not_computed" in rules("What's our tip rate?", "SELECT SUM(tip_amt) FROM trips")
        assert "rate_not_computed" not in rules("What's our tip rate?",
                                                "SELECT 1.0 * SUM(tip_amt) / SUM(fare_amt) FROM trips")
        assert "rate_not_computed" not in rules("average rate per kwh", "SELECT AVG(rate_per_kwh) FROM t")

    def test_vague_metric(self):
        k = NS(aliases=["total amount", "amount"])
        cat = NS(get=lambda _id: k)
        plan = NS(measures=[NS(kpi_id="sum_amt")])
        assert "vague_metric" in rules("Which hotel is doing best?", "SELECT 1", plan=plan, catalog=cat)
        assert "vague_metric" not in rules("Which hotel is doing best by total amount?", "SELECT 1",
                                           plan=plan, catalog=cat)


class TestShortCodesAndInclusion:
    def test_short_code_case(self):
        c = [("country", "US")]
        q = "booked with us"
        assert not _short_code_ok(q, q.index("us"), q.index("us") + 2, c)
        q = "members from the US"
        assert _short_code_ok(q, q.index("US"), q.index("US") + 2, c)
        assert _short_code_ok("in texas", 3, 8, [("state", "Texas")])

    def test_inclusion_phrase(self):
        ds = NS(flag_columns=["is_cancelled", "is_guest"])
        assert _flag_inclusion_columns("total amount, cancelled ones included", ds) == ["is_cancelled"]
        assert _flag_inclusion_columns("total spend including guest visits", ds) == ["is_guest"]
        assert _flag_inclusion_columns("total amount for cancelled bookings", ds) == []


class TestComposite:
    @pytest.fixture
    def ds(self, monkeypatch):
        import insightflow.plan.planner as P
        monkeypatch.setattr(P, "_is_anchor_noun", lambda n, ds: n.rstrip("s") in ("booking", "trip"))
        return NS(kind="uploaded", table="bookings")

    def test_percentage_of_rows(self, ds):
        from insightflow.composite import detect
        c = detect("What percentage of bookings were cancelled?", ds)
        assert c.kind == "pct_rows" and c.a == "How many bookings were cancelled?"
        assert c.b == "How many bookings were there?"

    def test_share_of_total(self, ds):
        from insightflow.composite import detect
        c = detect("What share of total booking amount came from Captain's Inn?", ds)
        assert c.kind == "share" and "for Captain's Inn" in c.a and c.b == "What is the total booking amount?"

    def test_explicit_ratio_only(self, ds):
        from insightflow.composite import detect
        c = detect("Across completed trips, what is the fare per km (total fare divided by total dist)?", ds)
        assert c.kind == "ratio" and c.a.endswith("for completed trips?")
        assert detect("What is the fare per km?", ds) is None          # 'per' alone: definition not stated

    def test_difference_needs_stated_order(self, ds):
        from insightflow.composite import detect
        c = detect("How much did total amount change from Q1 2025 to Q2 2025?", ds)
        assert c.kind == "difference" and "q2 2025" in c.a.lower() and "q1 2025" in c.b.lower()
        assert detect("Compare total amount in Q1 2025 and Q2 2025", ds) is None   # order not stated

    def test_demo_never_composite(self):
        from insightflow.composite import detect
        assert detect("What percentage of orders were returned?", NS(kind="demo")) is None


class TestVocabulary:
    def test_rules_on_a_toy_schema(self, monkeypatch):
        import insightflow.plan.planner as P
        from insightflow.knowledge.vocabulary import normalise
        monkeypatch.setattr(P, "_value_index", lambda ds: {"ota": [("channel", "OTA")], "fr": [("country", "FR")]})
        cols = {"bk_id": "INTEGER", "amt": "REAL", "nts_cnt": "INTEGER", "checkin_dt": "TEXT", "channel": "TEXT"}
        ds = NS(kind="uploaded", table="bookings", rel=None,
                columns={c: NS(sql_type=t) for c, t in cols.items()})
        q, rw = normalise("How many room nights from online travel agencies for rooms booked on check-in "
                          "day, deductible of 1,000?", ds)
        assert "nts" in q and "OTA" in q and "checkin" in q and "1000" in q
        assert "FR" not in q                                   # 'for rooms' is not the code FR
        kinds = {r.rule for r in rw}
        assert {"unit", "acronym", "compound", "number"} <= kinds
        assert any(r.interpretive for r in rw if r.rule == "acronym")

    def test_no_rewrite_on_demo(self):
        from insightflow.knowledge.vocabulary import normalise
        assert normalise("What is the revenue?", NS(kind="demo")) == ("What is the revenue?", [])


class TestPassiveAgent:
    def test_agent_needs_a_restricting_clause(self):
        from insightflow.plan.planner import _is_passive_agent
        assert _is_passive_agent("total fare from trips driven ", "drivers rated 4.8 or higher")
        assert not _is_passive_agent("total tuition paid ", "home state")          # grouping
        assert not _is_passive_agent("total units planned ", "plant")             # grouping
        assert not _is_passive_agent("total claim amt handled ", "each adjuster")  # grouping
        assert not _is_passive_agent("revenue grouped ", "region with ties")      # grouping verb
