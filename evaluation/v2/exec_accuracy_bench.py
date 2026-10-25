"""Execution-accuracy benchmark.

Measures whether the orchestrator's RESULT numerically matches an
independent oracle. Action-match is not enough — the user's spec
explicitly rejects "SQL executes" as sufficient.

Each case declares:
  - a canonical oracle computed via stdlib `sqlite3` (or `statistics`
    on raw column data) against the SAME demo DB the orchestrator
    queries
  - the extraction strategy for the system's result (scalar, sorted
    list, row-set)
  - a numerical tolerance (default 1e-4 relative)

Outputs:
  evaluation/v2/exec_accuracy_results.json
  evaluation/v2/exec_accuracy_summary.md
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import sqlite3
import statistics as _st
import subprocess
import sys
import time
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
V2 = ROOT / "evaluation" / "v2"
DB = BACKEND / "data" / "insightflow.db"

sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{DB}")
os.environ.setdefault("INSIGHTFLOW_REF_DATE", "2026-10-21")


# ----------------------------------------------------------------------
# Oracle helpers (independent of orchestrator)
# ----------------------------------------------------------------------

def _conn():
    return sqlite3.connect(str(DB))


def o_scalar(sql: str):
    with _conn() as c:
        row = c.execute(sql).fetchone()
    return None if row is None else row[0]


def o_column(sql: str):
    with _conn() as c:
        return [r[0] for r in c.execute(sql).fetchall()]


def o_rows(sql: str):
    with _conn() as c:
        return [tuple(r) for r in c.execute(sql).fetchall()]


def _pctile(xs, p):
    xs = sorted(xs)
    k = (p / 100.0) * (len(xs) - 1)
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return xs[lo] if lo == hi else xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


# ----------------------------------------------------------------------
# Comparison strategies
# ----------------------------------------------------------------------

def eq_scalar(sys_rows, expected, tol=1e-4):
    """System produced one row with one column; compare that scalar."""
    if not sys_rows or not sys_rows[0]:
        return False, None
    sys_val = sys_rows[0][0]
    if sys_val is None and expected is None:
        return True, None
    if sys_val is None or expected is None:
        return False, sys_val
    try:
        a, b = float(sys_val), float(expected)
    except (TypeError, ValueError):
        return sys_val == expected, sys_val
    denom = max(abs(a), abs(b), 1.0)
    return abs(a - b) / denom <= tol, sys_val


def eq_last_col_scalar(sys_rows, expected, tol=1e-4):
    """System produced one row; compare its LAST column."""
    if not sys_rows:
        return False, None
    sys_val = sys_rows[0][-1]
    return eq_scalar([[sys_val]], expected, tol)


def eq_rowset_last_col(sys_rows, expected_pairs, tol=1e-4):
    """System rows are (dim, metric). Compare as a dict key→value."""
    try:
        sys_pairs = {str(r[0]): float(r[-1]) for r in sys_rows}
        exp_pairs = {str(k): float(v) for k, v in expected_pairs.items()}
    except (TypeError, ValueError, IndexError):
        return False, None
    if sys_pairs.keys() != exp_pairs.keys():
        return False, sys_pairs
    for k in exp_pairs:
        denom = max(abs(sys_pairs[k]), abs(exp_pairs[k]), 1.0)
        if abs(sys_pairs[k] - exp_pairs[k]) / denom > tol:
            return False, sys_pairs
    return True, sys_pairs


def eq_ordered_rows(sys_rows, expected_rows, tol=1e-4):
    """Ordered rows, cell-wise comparison with tolerance."""
    if len(sys_rows) != len(expected_rows):
        return False, [list(r) for r in sys_rows]
    for sr, er in zip(sys_rows, expected_rows):
        if len(sr) != len(er):
            return False, [list(r) for r in sys_rows]
        for sv, ev in zip(sr, er):
            if sv is None and ev is None:
                continue
            if sv is None or ev is None:
                return False, [list(r) for r in sys_rows]
            try:
                a, b = float(sv), float(ev)
                denom = max(abs(a), abs(b), 1.0)
                if abs(a - b) / denom > tol:
                    return False, [list(r) for r in sys_rows]
            except (TypeError, ValueError):
                if str(sv) != str(ev):
                    return False, [list(r) for r in sys_rows]
    return True, [list(r) for r in sys_rows]


def refusal_only(sys_rows, expected):
    """Non-answerable: the only "correct" is CLARIFY/ABSTAIN (no result).
    `expected` ignored."""
    # This is checked at the action level before extraction; here always True.
    return True, None


# ----------------------------------------------------------------------
# Cases — each has an ORACLE computed from an independent SQL
# ----------------------------------------------------------------------

def build_cases():
    rev_sum = o_scalar("SELECT SUM(revenue) FROM orders")
    order_count = o_scalar("SELECT COUNT(*) FROM orders")
    aov = o_scalar("SELECT SUM(revenue)*1.0/COUNT(*) FROM orders")
    jul_rev = o_scalar(
        "SELECT SUM(revenue) FROM orders WHERE order_date >= '2026-07-01' "
        "AND order_date < '2026-08-01'")
    jun_rev = o_scalar(
        "SELECT SUM(revenue) FROM orders WHERE order_date >= '2026-06-01' "
        "AND order_date < '2026-07-01'")
    sep_rev = o_scalar(
        "SELECT SUM(revenue) FROM orders WHERE order_date >= '2026-09-01' "
        "AND order_date < '2026-10-01'")
    last_30 = o_scalar(
        "SELECT SUM(revenue) FROM orders WHERE order_date >= '2026-09-22' "
        "AND order_date < '2026-10-22'")
    region_rev = dict(o_rows(
        "SELECT regions.region_name, SUM(revenue) FROM orders "
        "JOIN regions ON regions.region_id = orders.region_id "
        "GROUP BY regions.region_name"))
    category_rev = dict(o_rows(
        "SELECT products.category, SUM(revenue) FROM orders "
        "JOIN products ON products.product_id = orders.product_id "
        "GROUP BY products.category"))
    jan_to_sep_rows = o_rows(
        "SELECT substr(order_date, 1, 7), SUM(revenue) FROM orders "
        "WHERE order_date >= '2026-01-01' AND order_date < '2026-10-01' "
        "GROUP BY substr(order_date, 1, 7) ORDER BY 1")
    top5_prod_rows = o_rows(
        "SELECT products.product_name, SUM(revenue) FROM orders "
        "JOIN products ON products.product_id = orders.product_id "
        "GROUP BY products.product_name ORDER BY 2 DESC LIMIT 5")
    all_rev_col = o_column("SELECT revenue FROM orders")
    all_qty_col = o_column("SELECT quantity FROM orders")
    distinct_customers = o_scalar(
        "SELECT COUNT(DISTINCT customer_name) FROM customers")
    distinct_products = o_scalar(
        "SELECT COUNT(DISTINCT product_name) FROM products")
    max_rev = o_scalar("SELECT MAX(revenue) FROM orders")
    min_rev = o_scalar("SELECT MIN(revenue) FROM orders")

    # Threshold months — set of (month, revenue) pairs where > 400k
    thr_months = dict(o_rows(
        "SELECT substr(order_date,1,7), SUM(revenue) FROM orders "
        "GROUP BY 1 HAVING SUM(revenue) > 400000"))

    cases = [
        # ---- Scalars ----
        ("S01", "What is the total revenue?", "ANSWER", eq_scalar, rev_sum),
        ("S02", "How many orders were placed?", "ANSWER", eq_scalar, order_count),
        ("S03", "What is the average order value?", "ANSWER", eq_scalar, aov),
        ("S04", "What was revenue in July 2026?", "ANSWER", eq_scalar, jul_rev),
        ("S05", "What was revenue in June 2026?", "ANSWER", eq_scalar, jun_rev),
        ("S06", "What was revenue in September 2026?", "ANSWER", eq_scalar, sep_rev),
        ("S07", "Revenue in the last 30 days", "ANSWER", eq_scalar, last_30),
        ("S08", "What was revenue last month?", "ANSWER", eq_scalar, sep_rev),
        ("S09", "How many distinct customers do we have?", "ANSWER",
         eq_scalar, distinct_customers),
        ("S10", "How many distinct products are there?", "ANSWER",
         eq_scalar, distinct_products),
        ("S11", "What is the maximum revenue?", "ANSWER", eq_scalar, max_rev),
        ("S12", "What is the minimum revenue?", "ANSWER", eq_scalar, min_rev),
        # ---- Stats ----
        ("ST1", "What is the median order revenue?", "ANSWER",
         eq_scalar, _st.median(all_rev_col)),
        ("ST2", "What is the 90th percentile of revenue?", "ANSWER",
         eq_scalar, _pctile(all_rev_col, 90)),
        ("ST3", "What is the standard deviation of revenue?", "ANSWER",
         eq_scalar, _st.stdev(all_rev_col)),
        ("ST4", "What is the variance of revenue?", "ANSWER",
         eq_scalar, _st.variance(all_rev_col)),
        ("ST5", "What is the median order quantity?", "ANSWER",
         eq_scalar, _st.median(all_qty_col)),
        # ---- Breakdowns ----
        ("B01", "Revenue by region", "ANSWER", eq_rowset_last_col, region_rev),
        ("B02", "Revenue by category", "ANSWER", eq_rowset_last_col, category_rev),
        # ---- Trend / ordered rows ----
        ("T01", "Show monthly revenue from January through September 2026.",
         "ANSWER", eq_ordered_rows, jan_to_sep_rows),
        # ---- Ranking ----
        ("R01", "Top 5 products by revenue", "ANSWER",
         eq_ordered_rows, top5_prod_rows),
        # ---- HAVING ----
        ("H01", "In which months did revenue exceed 400000?", "ANSWER",
         eq_rowset_last_col, thr_months),
        # ---- Refusals ----
        ("X01", "What will next month's revenue be?", "CLARIFY",
         refusal_only, None),
        ("X02", "Delete all orders.", "ABSTAIN", refusal_only, None),
        ("X03", "What is the meaning of life?", "CLARIFY",
         refusal_only, None),
        ("X04", "How is my business doing?", "CLARIFY",
         refusal_only, None),
        ("X05", "Find duplicate orders", "CLARIFY", refusal_only, None),
    ]
    return cases


def _commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT),
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    from insightflow.orchestrator import Orchestrator
    orch = Orchestrator()  # fresh — no follow-up state
    cases = build_cases()
    results = []
    exec_correct = 0
    action_correct = 0
    for cid, q, exp_action, cmp_fn, expected in cases:
        orch = __import__("insightflow.orchestrator",
                          fromlist=["Orchestrator"]).Orchestrator()
        t0 = time.perf_counter()
        try:
            r = orch.ask(q)
            action = r.decision.action
            sys_rows = list(r.result.rows) if r.result.ok else []
            latency_ms = int((time.perf_counter() - t0) * 1000)
        except Exception as e:
            results.append({
                "id": cid, "question": q, "expected_action": exp_action,
                "observed_action": "ERROR", "action_match": False,
                "exec_match": False, "error": str(e),
                "latency_ms": int((time.perf_counter() - t0) * 1000),
            })
            continue
        action_ok = action == exp_action \
                    or (exp_action == "ANSWER" and action == "WARN")
        if cmp_fn is refusal_only:
            exec_ok = action_ok  # refusals pass iff action matched
            sys_val = None
        else:
            exec_ok, sys_val = cmp_fn(sys_rows, expected)
            if not action_ok:
                exec_ok = False  # wrong action can't be exec-correct
        if action_ok:
            action_correct += 1
        if exec_ok:
            exec_correct += 1
        results.append({
            "id": cid, "question": q,
            "expected_action": exp_action, "observed_action": action,
            "action_match": action_ok,
            "exec_match": exec_ok,
            "sys_val": sys_val, "expected": expected,
            "sql": (r.sql or "")[:300],
            "latency_ms": latency_ms,
        })

    n = len(cases)
    summary = {
        "commit": _commit(),
        "n": n,
        "action_correct": action_correct,
        "action_accuracy": round(action_correct / n, 4),
        "exec_correct": exec_correct,
        "exec_accuracy": round(exec_correct / n, 4),
    }
    out = {"summary": summary, "results": results}
    (V2 / "exec_accuracy_results.json").write_text(json.dumps(out, indent=2))

    lines = ["# Execution-accuracy benchmark",
             "",
             f"- **Commit:** `{summary['commit']}`",
             f"- **Questions:** {n}",
             f"- **Action accuracy:** {summary['action_correct']} / {n}"
             f" = {summary['action_accuracy']:.1%}",
             f"- **Execution accuracy:** {summary['exec_correct']} / {n}"
             f" = {summary['exec_accuracy']:.1%}",
             "",
             "**Execution accuracy** means the system's numerical result",
             "equals the independent oracle (stdlib sqlite3 or statistics)",
             "within a 1e-4 relative tolerance.",
             "",
             "| id | question | expected | observed | action ok | exec ok |",
             "|---|---|---|---|:---:|:---:|"]
    for r in results:
        q = r["question"][:60].replace("|", "\\|")
        lines.append(f"| {r['id']} | {q} | {r['expected_action']} | "
                     f"{r['observed_action']} | "
                     f"{'✅' if r['action_match'] else '❌'} | "
                     f"{'✅' if r['exec_match'] else '❌'} |")
    lines.append("")
    lines.append("## Failed (exec_match=False)")
    lines.append("")
    for r in results:
        if r.get("exec_match"):
            continue
        lines.append(f"- **{r['id']}** `{r['question']}`")
        lines.append(f"  - action: expected {r['expected_action']} / "
                     f"observed {r['observed_action']}")
        lines.append(f"  - expected scalar/shape: {r.get('expected')!r}")
        lines.append(f"  - system value: {r.get('sys_val')!r}")
        lines.append(f"  - sql: `{r.get('sql', '')[:200]}`")
    (V2 / "exec_accuracy_summary.md").write_text("\n".join(lines))

    print(f"wrote {V2 / 'exec_accuracy_results.json'}")
    print(f"wrote {V2 / 'exec_accuracy_summary.md'}")
    print(f"action: {action_correct}/{n} = {summary['action_accuracy']:.1%}")
    print(f"exec:   {exec_correct}/{n} = {summary['exec_accuracy']:.1%}")


if __name__ == "__main__":
    main()
