"""Development generalization tests on a fresh schema (gym visits) that is unrelated to the v5 questions.
Positive cases compare with independent sqlite3 SQL; metamorphic cases check invariances (renaming,
row order, unrelated tables, duplicated child rows); negative cases check that false synonyms, a
misleading flag name, ambiguity, anti-joins and rate wording never produce a confident wrong number.
These are development tests, not held-out evaluation."""
import os, pathlib, random, shutil, sqlite3, tempfile

import pytest

ANSWER = ("ANSWER", "WARN")

# two naming schemes for the same data: abbreviated (A) and spelled out (B)
SCHEMES = {
    "A": dict(members="members", mbr_id="mbr_id", mbr_nm="mbr_nm", tier="tier", home_ctry="home_ctry",
              classes="classes", cls_id="cls_id", cls_nm="cls_nm", cls_type="cls_type", max_cap="max_cap",
              trainers="class_trainers", trainer_nm="trainer_nm",
              visits="visits", visit_id="visit_id", visit_dt="visit_dt", checkout_dt="checkout_dt",
              spend_amt="spend_amt", mins_cnt="mins_cnt", is_guest="is_guest", kit_ok="kit_ok",
              pay_method="pay_method", is_amount_waived="is_amount_waived"),
    "B": dict(members="members", mbr_id="member_id", mbr_nm="member_name", tier="tier", home_ctry="home_country",
              classes="classes", cls_id="class_id", cls_nm="class_name", cls_type="class_type", max_cap="max_capacity",
              trainers="class_trainers", trainer_nm="trainer_name",
              visits="visits", visit_id="visit_id", visit_dt="visit_date", checkout_dt="checkout_date",
              spend_amt="spend_amount", mins_cnt="minutes_count", is_guest="is_guest", kit_ok="kit_ok",
              pay_method="pay_method", is_amount_waived="is_amount_waived"),
}


def build(path, scheme="A", shuffle=False, extra_table=False, dup_trainers=False, seed=7):
    n = SCHEMES[scheme]
    rng = random.Random(seed)
    con = sqlite3.connect(path)
    con.executescript(f"""
    CREATE TABLE {n['members']} ({n['mbr_id']} INTEGER PRIMARY KEY, {n['mbr_nm']} TEXT NOT NULL,
        {n['tier']} TEXT, {n['home_ctry']} TEXT NOT NULL);
    CREATE TABLE {n['classes']} ({n['cls_id']} INTEGER PRIMARY KEY, {n['cls_nm']} TEXT NOT NULL,
        {n['cls_type']} TEXT NOT NULL, {n['max_cap']} INTEGER NOT NULL);
    CREATE TABLE {n['trainers']} ({n['cls_id']} INTEGER NOT NULL REFERENCES {n['classes']}({n['cls_id']}),
        {n['trainer_nm']} TEXT NOT NULL);
    CREATE TABLE {n['visits']} ({n['visit_id']} INTEGER PRIMARY KEY,
        {n['mbr_id']} INTEGER NOT NULL REFERENCES {n['members']}({n['mbr_id']}),
        {n['cls_id']} INTEGER NOT NULL REFERENCES {n['classes']}({n['cls_id']}),
        {n['visit_dt']} TEXT NOT NULL, {n['checkout_dt']} TEXT, {n['spend_amt']} REAL NOT NULL,
        {n['mins_cnt']} INTEGER NOT NULL, {n['is_guest']} INTEGER NOT NULL, {n['kit_ok']} INTEGER NOT NULL,
        {n['pay_method']} TEXT, {n['is_amount_waived']} INTEGER NOT NULL);
    """)
    members = [(i, f"Member {i:02d}", rng.choice(["Gold", "Silver", None]), rng.choice(["US", "UK", "Canada"]))
               for i in range(1, 31)]
    classes = [(1, "Morning Yoga", "Yoga", 15), (2, "Power Spin", "Cycling", 25), (3, "Core Blast", "HIIT", 20),
               (4, "Evening Yoga", "Yoga", 30), (5, "Boxing Basics", "Combat", 12)]
    trainers = [(1, "Ana Ruiz"), (2, "Ben Ola"), (3, "Ana Ruiz"), (4, "Chen Li"), (5, "Ben Ola"), (3, "Chen Li")]
    if dup_trainers:
        trainers += [(1, "Ana Ruiz"), (3, "Ana Ruiz")]
    visits = []
    for v in range(1, 401):
        m = rng.randint(3, 12)
        visits.append((v, rng.randint(1, 30), rng.randint(1, 5), f"2025-{m:02d}-{rng.randint(1, 20):02d}",
                       None if rng.random() < 0.15 else f"2025-{min(12, m + rng.randint(0, 1)):02d}-{rng.randint(1, 28):02d}",
                       round(rng.uniform(5, 60), 2), rng.randint(20, 90), int(rng.random() < 0.2),
                       int(rng.random() > 0.1), rng.choice(["Card", "Cash", None]), int(rng.random() < 0.05)))
    for rows in (members, classes, trainers, visits):
        if shuffle:
            rng.shuffle(rows)
    con.executemany(f"INSERT INTO {n['members']} VALUES (?,?,?,?)", members)
    con.executemany(f"INSERT INTO {n['classes']} VALUES (?,?,?,?)", classes)
    con.executemany(f"INSERT INTO {n['trainers']} VALUES (?,?)", trainers)
    con.executemany(f"INSERT INTO {n['visits']} VALUES (?,?,?,?,?,?,?,?,?,?,?)", visits)
    if extra_table:
        con.executescript("CREATE TABLE lockers (locker_id INTEGER PRIMARY KEY, locker_amt REAL, zone TEXT);"
                          "INSERT INTO lockers VALUES (1, 5.0, 'North'), (2, 7.5, 'South');")
    con.commit(); con.close()


@pytest.fixture(scope="module")
def gym():
    from insightflow.config import settings
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.dataset_registry import bootstrap, set_active, DEMO_ID, register_relational
    from insightflow.knowledge.schema_agent import refresh_schema
    url = settings.database_url
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gymdev_"))

    def use(scheme="A", **kw):
        tag = scheme + "".join(f"_{k}" for k, v in sorted(kw.items()) if v)
        p = tmp / f"gym_{tag}.db"
        if not p.exists():
            build(p, scheme, **kw)
        settings.database_url = f"sqlite:///{p}"
        os.environ.pop("INSIGHTFLOW_METRICS_FILE", None)
        reset_engine(); bootstrap()
        ds_id = register_relational(f"gym{tag}@visits", "visits")
        reset_engine(); refresh_schema(); set_active(ds_id)
        return p, SCHEMES[scheme]
    yield use
    settings.database_url = url
    reset_engine(); bootstrap(); set_active(DEMO_ID)
    shutil.rmtree(tmp, ignore_errors=True)


def ask(q):
    from insightflow.orchestrator import Orchestrator
    return Orchestrator().ask(q)


def ref(p, sql):
    with sqlite3.connect(p) as c:
        return c.execute(sql).fetchall()


def val(r):
    assert r.decision.action in ANSWER, (r.decision.action, r.decision.reason, r.sql)
    assert len(r.result.rows) == 1 and len(r.result.rows[0]) == 1, r.result.rows
    return r.result.rows[0][0]


def refused(r):
    return r.decision.action in ("CLARIFY", "ABSTAIN")


# question -> reference SQL template over the scheme's names
POSITIVE = [
    ("What is the total spend?", "SELECT SUM({spend_amt}) FROM visits"),
    ("How many visits were there?", "SELECT COUNT(*) FROM visits"),
    ("What is the average spend per visit?", "SELECT AVG({spend_amt}) FROM visits"),
    ("How many minutes in total did visits last?", "SELECT SUM({mins_cnt}) FROM visits"),
    ("Total spend excluding guest visits", "SELECT SUM({spend_amt}) FROM visits WHERE {is_guest} = 0"),
    ("How many visits had faulty kit?", "SELECT COUNT(*) FROM visits WHERE {kit_ok} = 0"),
    ("How many visits have no checkout date recorded?", "SELECT COUNT(*) FROM visits WHERE {checkout_dt} IS NULL"),
    ("How many different members visited?", "SELECT COUNT(DISTINCT {mbr_id}) FROM visits"),
    ("Total spend for classes with a max capacity of 20 or more",
     "SELECT SUM(v.{spend_amt}) FROM visits v JOIN classes c ON c.{cls_id} = v.{cls_id} WHERE c.{max_cap} >= 20"),
    ("Total spend for Yoga classes",
     "SELECT SUM(v.{spend_amt}) FROM visits v JOIN classes c ON c.{cls_id} = v.{cls_id} WHERE c.{cls_type} = 'Yoga'"),
    ("Total spend for classes taught by Ana Ruiz",
     "SELECT SUM(v.{spend_amt}) FROM visits v WHERE EXISTS (SELECT 1 FROM class_trainers t "
     "WHERE t.{cls_id} = v.{cls_id} AND t.{trainer_nm} = 'Ana Ruiz')"),
    ("What percentage of visits were guest visits?",
     "SELECT 100.0 * SUM({is_guest}) / COUNT(*) FROM visits"),
    ("What share of total spend came from Yoga classes?",
     "SELECT 100.0 * SUM(CASE WHEN c.{cls_type} = 'Yoga' THEN v.{spend_amt} ELSE 0 END) / SUM(v.{spend_amt}) "
     "FROM visits v JOIN classes c ON c.{cls_id} = v.{cls_id}"),
    ("Total spend, guest visits included", "SELECT SUM({spend_amt}) FROM visits"),
    ("Total spend for members from the US",
     "SELECT SUM(v.{spend_amt}) FROM visits v JOIN members m ON m.{mbr_id} = v.{mbr_id} WHERE m.{home_ctry} = 'US'"),
]


@pytest.mark.parametrize("q,sql", POSITIVE, ids=[p[0][:40] for p in POSITIVE])
@pytest.mark.parametrize("scheme", ["A", "B"])
def test_positive_matches_reference(gym, scheme, q, sql):
    p, n = gym(scheme)
    exp = ref(p, sql.format(**n))[0][0]
    r = ask(q)
    if r.decision.action in ANSWER:
        assert val(r) == pytest.approx(exp, rel=1e-9), r.sql
    else:
        pytest.fail(f"[{scheme}] refused an answerable question: {r.decision.reason}")


@pytest.mark.parametrize("q", [p[0] for p in POSITIVE])
def test_metamorphic_invariances(gym, q):
    """Renaming (A vs B), row order, an unrelated table and duplicated trainer rows leave every answer
    unchanged (or the question is refused in every variant)."""
    outs = []
    for kw in (dict(scheme="A"), dict(scheme="B"), dict(scheme="A", shuffle=True),
               dict(scheme="A", extra_table=True), dict(scheme="A", dup_trainers=True)):
        gym(**kw)
        r = ask(q)
        outs.append(round(float(val(r)), 9) if r.decision.action in ANSWER else "refused")
    assert len(set(outs)) == 1, outs


def test_sum_vs_count_changes_aggregation(gym):
    p, n = gym("A")
    s, c = val(ask("What is the total spend?")), val(ask("How many visits were there?"))
    assert s == pytest.approx(ref(p, f"SELECT SUM({n['spend_amt']}) FROM visits")[0][0])
    assert c == ref(p, "SELECT COUNT(*) FROM visits")[0][0] and s != c


def test_misleading_flag_is_never_summed(gym):
    p, n = gym("A")
    r = ask("What is the total amount?")
    if r.decision.action in ANSWER:
        assert "is_amount_waived" not in r.sql.lower()
        assert val(r) != pytest.approx(ref(p, "SELECT SUM(is_amount_waived) FROM visits")[0][0])


def test_member_count_is_not_a_visit_count(gym):
    p, n = gym("A")
    r = ask("How many different members visited?")
    assert val(r) == ref(p, f"SELECT COUNT(DISTINCT {n['mbr_id']}) FROM visits")[0][0]
    assert val(r) != ref(p, "SELECT COUNT(*) FROM visits")[0][0]


@pytest.mark.parametrize("q", [
    "Total spend in March 2025",                  # two date columns give different answers
    "Which members have no visits?",              # anti-join: unsupported
    "What is the guest rate?",                    # rate wording without a stated formula
    "Which class is doing best?",                 # no measure named
    "Total spend by trainer",                     # grouping over a one-to-many table would double count
])
def test_ambiguous_or_unsupported_is_refused(gym, q):
    gym("A")
    assert refused(ask(q))


def test_negated_value_never_keeps_the_value(gym):
    p, n = gym("A")
    r = ask("Total spend for visits not paid by card")
    if r.decision.action in ANSWER:
        exp = ref(p, f"SELECT SUM({n['spend_amt']}) FROM visits WHERE {n['pay_method']} IS NOT 'Card'")[0][0]
        assert val(r) == pytest.approx(exp)
    assert "= 'Card'" not in (r.sql or "") or "NOT" in (r.sql or "") or refused(r)


def test_short_code_needs_capitals(gym):
    p, n = gym("A")
    r = ask("How many visits did members make with us?")
    assert "'US'" not in (r.sql or "")
