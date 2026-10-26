"""Closure probes (non-destructive): typed engine and Orchestrator on isolated temporary copies of the dev databases.
usage (from backend/): PYTHONPATH=. python ../research_improvement/closure/probe_closure.py"""
import hashlib, os, pathlib, shutil, sqlite3, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research_improvement" / "architecture_recovery" / "devsets"))
import dev_schemas as D  # noqa: E402

tmp = pathlib.Path(tempfile.mkdtemp(prefix="closure_"))
D.DATA = tmp / "data"
paths = {k: str(v) for k, v in D.build_all("abbr").items()}
ANCHOR = {"bikes": "rentals", "school": "exam_results", "shop": "orders", "support": "tickets"}
digest = lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
before = {k: digest(p) for k, p in paths.items()}

from insightflow.engine.engine import answer, _execute          # noqa: E402
from insightflow.engine import schema_model as S                # noqa: E402
from insightflow.engine.compiler import Compiler, CompileError  # noqa: E402
from insightflow.engine.ir import Agg, Col, InSet, Measure, Query  # noqa: E402

results = []
def check(name, ok, detail=""):
    results.append((name, ok)); print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))

def ref(dom, sql):
    return sqlite3.connect(paths[dom]).execute(sql).fetchall()

def ask(dom, q):
    return answer(q, paths[dom], ANCHOR[dom])

# ---- SQL safety (typed engine)
r = ask("shop", "Total gross amount for D'Angelo & Sons'); DROP TABLE orders;--")
check("injection text in a question never executes DDL", r.status != "answer" or "DROP" not in r.sql.upper(), r.status)
m = S.get(paths["shop"], "orders")
sql, params = Compiler(m).compile(Query(measures=[Measure("n", Agg("count"))],
                                        filters=[InSet(Col("orders", "ship_mode"), ("x'); DELETE FROM orders;--",))]))
check("literals are bound parameters, not SQL text", "DELETE" not in sql and params == ["x'); DELETE FROM orders;--"])
try:
    Compiler(m).compile(Query(measures=[Measure("n", Agg("sum", Col("orders", 'gross_amt"; DROP TABLE orders; --')))]))
    check("unknown/quoted identifier rejected before SQL", False)
except (CompileError, KeyError) as e:
    check("unknown/quoted identifier rejected before SQL", True, type(e).__name__)
for bad in ("DELETE FROM orders", "SELECT 1; DROP TABLE orders", "UPDATE orders SET gross_amt = 0"):
    try:
        _execute(paths["shop"], bad, [], 5, 10)
        check(f"engine executor refuses: {bad}", False)
    except sqlite3.Error as e:
        check(f"engine executor refuses: {bad}", True, str(e)[:60])
check("only SELECT is ever compiled", all(x.status != "answer" or x.sql.lstrip().upper().startswith("SELECT")
      for x in [ask("shop", q) for q in ("Total gross amount by region", "How many orders were returned?", "Monthly gross amount")]))

# ---- critical behaviour (typed engine)
def eq(dom, q, sql):
    x = ask(dom, q); exp = ref(dom, sql)
    ok = x.status == "answer" and len(x.rows) == len(exp) and all(abs((a[-1] or 0) - (b[-1] or 0)) < 1e-6 for a, b in zip(sorted(x.rows, key=repr), sorted(exp, key=repr)))
    check(f"answer matches reference: {q}", ok, x.status + " " + x.message[:80])
eq("shop", "Total gross amount", "SELECT SUM(gross_amt) FROM orders")
eq("shop", "Average gross amount for Express orders", "SELECT AVG(gross_amt) FROM orders WHERE ship_mode='Express'")
eq("shop", "Total discount amount by region", "SELECT c.region, SUM(o.disc_amt) FROM orders o JOIN customers c ON c.cust_id=o.cust_id GROUP BY 1")
eq("shop", "Percentage of orders that are gifts", "SELECT 100.0*SUM(is_gift)/COUNT(*) FROM orders")
eq("shop", "Gross amount of orders that were never returned", "SELECT SUM(gross_amt) FROM orders o WHERE NOT EXISTS (SELECT 1 FROM returns r WHERE r.order_id=o.order_id)")
eq("shop", "Total gross amount excluding Express orders", "SELECT SUM(gross_amt) FROM orders WHERE ship_mode <> 'Express'")
eq("bikes", "How many rentals without any issue for electric bikes?", "SELECT COUNT(*) FROM rentals r JOIN bikes b ON b.bike_id=r.bike_id WHERE b.bike_type='electric' AND NOT EXISTS (SELECT 1 FROM rental_issues i WHERE i.rental_id=r.rental_id)")
x = ask("support", "Top 3 accounts by number of tickets")
exp = ref("support", "SELECT a.acct_nm, COUNT(*) FROM tickets t JOIN accounts a ON a.acct_id=t.acct_id GROUP BY t.acct_id ORDER BY 2 DESC LIMIT 3")
check("ranking: top-N sorted and limited", x.status == "answer" and [r[-1] for r in x.rows] == [r[-1] for r in exp], str(x.rows))
x = ask("shop", "Share of gross amount by ship mode")
check("shares sum to 100", x.status == "answer" and abs(sum(r[-1] for r in x.rows) - 100) < 1e-6)
for q in ("Total fare by station", "Tickets by agent"):
    check(f"role ambiguity asks: {q}", ask("bikes" if "fare" in q else "support", q).status == "clarify")
x = ask("bikes", "Total fare in 2025")
check("conflicting readings: asks and shows each value", x.status == "clarify" and "different results" in x.message, x.message[:90])
for q, dom in (("Total revenue", "shop"), ("Which customers are at risk of churn?", "shop"), ("Total fare in the last 7 days", "bikes"),
               ("Predict next month's rentals", "bikes"), ("Total gross amount not for the dog", "shop")):
    x = ask(dom, q); check(f"not answered: {q}", x.status in ("clarify", "unsupported"), x.status + ": " + x.message[:70])
x = ask("shop", "Total gross amount for Express orders in 2019")
check("empty result is reported, not hidden", x.status in ("answer", "clarify") and (x.status != "answer" or x.reliability.get("empty_result")), f"{x.status} {x.rows}")
x = ask("shop", "Average refund amount")
check("lookup/child attribute not silently aggregated", x.status != "answer", x.message[:80])
x = answer("Total gross amount", str(tmp / "missing.db"), "orders")
check("missing database file -> error status, no answer", x.status == "error", x.message[:70])
x = answer("Total gross amount", paths["shop"], "no_such_table")
check("unknown anchor table -> no answer", x.status != "answer", f"{x.status}: {x.message[:60]}")

# ---- Orchestrator decision and destructive handling (typed default) on an isolated registered copy
from insightflow.config import settings                               # noqa: E402
from insightflow.execution.executor import reset_engine               # noqa: E402
from insightflow.knowledge.dataset_registry import bootstrap, register_relational, set_active  # noqa: E402
from insightflow.knowledge.schema_agent import refresh_schema         # noqa: E402
from insightflow.orchestrator import Orchestrator                     # noqa: E402
os.environ.pop("INSIGHTFLOW_ENGINE", None)
dst = tmp / "shop_reg.db"; shutil.copy(paths["shop"], dst)
settings.database_url = f"sqlite:///{dst}"
reset_engine(); bootstrap(); ds = register_relational("shop", "orders"); reset_engine(); refresh_schema(); set_active(ds)
before_reg = digest(dst)
o = Orchestrator()
def act(q): r = o.ask(q); return r.decision.action, r
a, r = act("Total gross amount"); check("ANSWER for a fully grounded question", a == "ANSWER", r.decision.reason[:60])
a, r = act("Gross amount by region"); check("WARN when no aggregation word is given (sum is an assumption)", a == "WARN", r.decision.reason[:70])
a, r = act("Total gross amount for Express orders in 2019"); check("WARN when the result is empty", a == "WARN" and "empty" in r.decision.reason, r.decision.reason[:70])
a, r = act("Tickets by agent"); check("CLARIFY for an ungrounded/ambiguous question", a == "CLARIFY", r.decision.reason[:60])
a, r = act("Monthly gross amount"); check("CLARIFY when readings conflict (no answer)", a == "CLARIFY" and not r.result.rows, r.decision.reason[:80])
for q in ("Delete all orders", "drop table orders", "Update the gross amount of every order to zero"):
    a, r = act(q); check(f"destructive request refused, no SQL: {q}", a in ("ABSTAIN", "CLARIFY") and not r.sql, a)
a, r = act("Total gross amount"); check("typed path used for registered SQLite dataset", (r.diagnostics or {}).get("engine") == "typed")
check("registered database unchanged after all requests", digest(dst) == before_reg)
check("source databases unchanged", all(digest(p) == before[k] for k, p in paths.items()))
print(f"\n{sum(ok for _, ok in results)}/{len(results)} probes passed")
