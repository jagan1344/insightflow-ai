"""Silent-error classes found on the first sealed Schema-C run, and the
wording audit / edge-case features added afterwards. Oracles are plain sqlite3."""
import sqlite3
import sys
import pathlib
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_reliability_features import live, ask, sql1  # noqa: E402,F401


def _plan(kind="breakdown", aggs=("sum",), kpis=("total_revenue",), top_n=None, filters=()):
    return NS(intent_kind=kind, top_n=top_n, filters=list(filters), relative_stat=None,
              measures=[NS(kpi_id=k, aggregation=a) for k, a in zip(kpis, aggs)])


class _Cat:
    def __init__(self, k):
        self.k = k

    def get(self, kid):
        return self.k.get(kid)


def _kpi(name, aliases, agg="sum"):
    return NS(kpi_id=name, display_name=name, aliases=aliases, aggregation=agg)


# ------------------------------------------------------------ audit unit tests
class TestAuditUnit:
    audit = staticmethod(__import__('insightflow.verification.intent_audit', fromlist=['audit']).audit)

    def test_scalar_question_answered_with_groups_is_flagged(self):
        # exact shape of Schema-C failures C05/C24
        f = self.audit("Total tuition paid by students from California",
                       'SELECT s, SUM(t) FROM e GROUP BY s', _plan(), None, 7)
        assert [x.name for x in f] == ["unrequested_grouping"]

    def test_group_cues_are_not_flagged(self):
        for q in ("Total tuition paid by home state", "Top 3 states by tuition",
                  "Total tuition per state", "Which state has the highest tuition"):
            assert not self.audit(q, "SELECT s, SUM(t) FROM e GROUP BY s",
                                  _plan(top_n=3), None, 3), q

    def test_average_question_without_avg(self):
        f = self.audit("What is the average fee", "SELECT SUM(fee) FROM v",
                       _plan("direct_kpi"), None, 1)
        assert f and f[0].name == "aggregation_cue"
        assert not self.audit("What is the average fee", "SELECT AVG(fee) FROM v",
                              _plan("direct_kpi", aggs=("avg",)), None, 1)

    def test_count_question_without_count(self):
        assert self.audit("How many visits were there", "SELECT SUM(fee) FROM v",
                          _plan("direct_kpi"), None, 1)
        assert not self.audit("How many units were sold", "SELECT SUM(qty) FROM o",
                              _plan("direct_kpi", kpis=("units",)),
                              _Cat({"units": _kpi("units", ["units sold", "units"])}), 1)

    def test_default_measure_is_flagged(self):
        cat = _Cat({"total_revenue": _kpi("Total Revenue", ["revenue", "sales"])})
        f = self.audit("Show it by region", "SELECT r, SUM(x) FROM t GROUP BY r",
                       _plan(), cat, 3)
        assert any(x.name == "measure_not_named" for x in f)

    def test_month_named_but_not_applied(self):
        f = self.audit("Total fee in June", "SELECT SUM(fee) FROM v",
                       _plan("direct_kpi"), None, 1)
        assert [x.name for x in f] == ["month_not_applied"]
        assert not self.audit("Total fee in June", "... >= '2025-06-01' ...",
                              _plan("direct_kpi"), None, 1)


# ------------------------------------------------- numbers / years / exclusions
class TestUnrepresentedNumbers:
    un = staticmethod(__import__('insightflow.reliability.mention_coverage', fromlist=['x']).unrepresented_numbers)

    def test_threshold_dropped(self):
        assert self.un("Total tuition for enrollments over 2000", "SELECT SUM(t) FROM e") == ["2000"]

    def test_threshold_applied(self):
        assert not self.un("Total tuition over 2000", "SELECT SUM(t) FROM e WHERE t > 2000")

    def test_exemptions(self):
        for q in ("Top 5 states by tuition", "Tuition in Q2", "tuition in 2025",
                  "growth above 10%", "last 7 days tuition", "the 3rd state"):
            assert not self.un(q, "SELECT 1"), q

    def test_digits_inside_value_masked(self):
        assert not self.un("Total for Customer-007", "SELECT 1", ["customer-007"])


# ------------------------------------------------------------- end to end
def _num(r):
    return float(r.result.rows[0][-1]) if r.result.rows and r.result.rows[0][-1] is not None else None


class TestRelatedMeasuresAndFilters:
    def test_measure_on_related_table(self, live):
        p = live("university")
        r = ask("Total credits enrolled")
        exp = sql1(p, "SELECT SUM(c.credits) FROM enrollments e JOIN courses c ON c.course_id=e.course_id")[0][0]
        assert r.decision.action in ("ANSWER", "WARN") and abs(_num(r) - exp) < 1e-9

    def test_related_measure_grouped_by_other_related_dimension(self, live):
        p = live("university")
        r = ask("Total credits by home state")
        exp = dict(sql1(p, "SELECT s.home_state, SUM(c.credits) FROM enrollments e JOIN courses c ON c.course_id=e.course_id JOIN students s ON s.student_id=e.student_id GROUP BY 1"))
        assert r.decision.action in ("ANSWER", "WARN")
        assert {x[0]: x[-1] for x in r.result.rows} == exp

    @pytest.mark.parametrize("q,pred", [
        ("Total tuition paid for 4 credit courses", "c.credits = 4"),
        ("Total tuition paid for courses with more than 3 credits", "c.credits > 3"),
        ("Total tuition paid for courses with at most 3 credits", "c.credits <= 3"),
    ])
    def test_numeric_filter_on_related_attribute(self, live, q, pred):
        p = live("university")
        r = ask(q)
        exp = sql1(p, f"SELECT SUM(e.tuition_paid) FROM enrollments e JOIN courses c ON c.course_id=e.course_id WHERE {pred}")[0][0]
        assert r.decision.action in ("ANSWER", "WARN") and abs(_num(r) - exp) < 1e-6

    def test_unsupported_numeric_threshold_is_not_ignored(self, live):
        live("university")
        r = ask("Total tuition paid for enrollments over 2000")
        assert r.decision.action not in ("ANSWER", "WARN")


class TestExclusions:
    def test_exclude_value(self, live):
        p = live("university")
        r = ask("Total tuition paid excluding California students")
        exp = sql1(p, "SELECT SUM(e.tuition_paid) FROM enrollments e JOIN students s ON s.student_id=e.student_id WHERE s.home_state IS NULL OR s.home_state <> 'California'")[0][0]
        assert r.decision.action in ("ANSWER", "WARN") and abs(_num(r) - exp) < 1e-6

    def test_exclude_list_keeps_grouping(self, live):
        p = live("university")
        r = ask("Total tuition paid by home state except Texas")
        exp = dict(sql1(p, "SELECT s.home_state, SUM(e.tuition_paid) FROM enrollments e JOIN students s ON s.student_id=e.student_id WHERE s.home_state <> 'Texas' GROUP BY 1"))
        assert {x[0]: x[-1] for x in r.result.rows} == pytest.approx(exp)

    def test_exclude_two_values(self, live):
        p = live("university")
        r = ask("Total tuition paid excluding Texas and Ohio")
        exp = sql1(p, "SELECT SUM(e.tuition_paid) FROM enrollments e JOIN students s ON s.student_id=e.student_id WHERE s.home_state NOT IN ('Texas','Ohio')")[0][0]
        assert abs(_num(r) - exp) < 1e-6

    def test_conflicting_conditions_clarified(self, live):
        live("university")
        r = ask("Total tuition paid for California students excluding California")
        assert r.decision.action == "CLARIFY"
        assert "included and excluded" in r.explanation

    def test_exclude_fanout_uses_not_exists(self, live):
        p = live("clinic")
        r = ask("Total fee excluding visits with an Imaging procedure")
        exp = sql1(p, "SELECT SUM(fee) FROM visits WHERE NOT EXISTS (SELECT 1 FROM visit_procedures vp JOIN procedures pr ON pr.procedure_id=vp.procedure_id WHERE vp.visit_id=visits.visit_id AND pr.category='Imaging')")[0][0]
        assert r.decision.action in ("ANSWER", "WARN") and abs(_num(r) - exp) < 1e-6

    def test_exclusion_of_a_measure_is_still_refused(self, live):
        live("clinic")
        assert ask("What was the total fee not including copay?").decision.action == "CLARIFY"


class TestDatesAndYears:
    def test_month_without_year_uses_the_datas_year(self, live):
        p = live("university")
        r = ask("Total tuition paid for enrollments completed in May")
        exp = sql1(p, "SELECT SUM(tuition_paid) FROM enrollments WHERE completed_on>='2025-05-01' AND completed_on<'2025-06-01'")[0][0]
        assert r.decision.action in ("ANSWER", "WARN") and abs(_num(r) - exp) < 1e-6

    def test_month_without_year_is_asked_when_data_spans_years(self, live):
        p = live("university")
        with sqlite3.connect(str(p)) as c:
            c.execute("INSERT INTO enrollments VALUES (9001,1,1,'2024-05-10','2024-05-20',100.0,3.0)")
        r = ask("Total tuition paid for enrollments completed in May")
        assert r.decision.action == "CLARIFY" and "2024" in r.explanation and "2025" in r.explanation

    def test_leap_day_and_time_of_day_boundaries(self, live):
        p = live("university")
        with sqlite3.connect(str(p)) as c:
            c.executemany("INSERT INTO enrollments VALUES (?,?,?,?,?,?,?)", [
                (9101, 1, 1, "2024-02-29 23:59:59", "2024-03-05", 100.0, None),   # in Feb (leap day)
                (9102, 1, 1, "2024-02-29", "2024-03-05", 10.0, None),             # in Feb
                (9103, 1, 1, "2024-03-01 00:00:00", "2024-03-05", 1000.0, None),  # March
                (9104, 1, 1, "2024-01-31 23:59:59", "2024-03-05", 10000.0, None), # January
            ])
        r = ask("Total tuition paid for enrollments enrolled in February 2024")
        assert r.decision.action in ("ANSWER", "WARN") and abs(_num(r) - 110.0) < 1e-9

    def test_two_date_columns_still_ask(self, live):
        live("university")
        assert ask("Total tuition paid in March 2025").decision.action == "CLARIFY"


class TestUnsupportedClassesNeverGuess:
    def test_anti_join_question(self, live):
        p = live("university")
        r = ask("Which departments had no enrollments?")
        assert r.decision.action not in ("ANSWER", "WARN") or \
            [x[0] for x in r.result.rows] == ["Classics"]

    def test_counting_a_non_base_entity(self, live):
        p = live("university")
        r = ask("How many students are there?")
        total_students = sql1(p, "SELECT COUNT(*) FROM students")[0][0]
        assert r.decision.action not in ("ANSWER", "WARN") or _num(r) == total_students


class TestFollowUps:
    def test_filter_context_survives_a_grouping_followup(self, live):
        from insightflow.orchestrator import Orchestrator
        p = live("university")
        o = Orchestrator()
        a = o.ask("Total tuition paid for courses taught by Prof. Ngozi Eze-Bello")
        assert a.decision.action in ("ANSWER", "WARN")
        b = o.ask("Now by home state")
        exp = dict(sql1(p, "SELECT s.home_state, SUM(e.tuition_paid) FROM enrollments e JOIN students s ON s.student_id=e.student_id WHERE EXISTS (SELECT 1 FROM teaching t JOIN instructors i ON i.instr_id=t.instr_id WHERE t.course_id=e.course_id AND i.instr_name='Prof. Ngozi Eze-Bello') GROUP BY 1"))
        assert b.decision.action in ("ANSWER", "WARN")
        assert {x[0]: x[-1] for x in b.result.rows} == pytest.approx(exp)
