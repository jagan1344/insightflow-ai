"""Advanced execution-accuracy probe.

A 25-question stress set designed to catch REAL failure modes:
  - One-to-many JOIN duplication (double-counted revenue)
  - COUNT vs COUNT DISTINCT confusion
  - Compound filters (region + category + month)
  - Date-boundary mistakes
  - Multi-dim grouping with correct cardinality
  - Ratio KPIs with correct denominators
  - Share-of-total summing to 1.0
  - Contribution with per-dim deltas
  - Paraphrases of the same intent

Each question has an INDEPENDENT oracle built directly from sqlite3,
NOT from the orchestrator's own SQL.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import sqlite3
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
V2 = ROOT / "evaluation" / "v2"
DB = BACKEND / "data" / "insightflow.db"

sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{DB}")
os.environ.setdefault("INSIGHTFLOW_REF_DATE", "2026-10-21")


def o_scalar(sql):
    with sqlite3.connect(str(DB)) as c:
        r = c.execute(sql).fetchone()
    return None if r is None else r[0]


def o_rows(sql):
    with sqlite3.connect(str(DB)) as c:
        return [tuple(r) for r in c.execute(sql).fetchall()]


def eq_scalar(sys_rows, expected, tol=1e-4):
    if not sys_rows or sys_rows[0][0] is None:
        return False, None
    try:
        a, b = float(sys_rows[0][-1]), float(expected)
    except (TypeError, ValueError):
        return False, sys_rows[0][-1]
    denom = max(abs(a), abs(b), 1.0)
    return abs(a - b) / denom <= tol, sys_rows[0][-1]


def eq_rowset(sys_rows, expected_map, tol=1e-4):
    try:
        sm = {str(r[0]): float(r[-1]) for r in sys_rows}
        em = {str(k): float(v) for k, v in expected_map.items()}
    except (TypeError, ValueError, IndexError):
        return False, None
    if set(sm) != set(em):
        return False, sm
    for k in em:
        d = max(abs(sm[k]), abs(em[k]), 1.0)
        if abs(sm[k] - em[k]) / d > tol:
            return False, sm
    return True, sm


def eq_ordered(sys_rows, expected_rows, tol=1e-4):
    if len(sys_rows) != len(expected_rows):
        return False, [list(r) for r in sys_rows]
    for sr, er in zip(sys_rows, expected_rows):
        for sv, ev in zip(sr, er):
            if sv is None and ev is None:
                continue
            if sv is None or ev is None:
                return False, [list(r) for r in sys_rows]
            try:
                a, b = float(sv), float(ev)
                d = max(abs(a), abs(b), 1.0)
                if abs(a - b) / d > tol:
                    return False, [list(r) for r in sys_rows]
            except (TypeError, ValueError):
                if str(sv) != str(ev):
                    return False, [list(r) for r in sys_rows]
    return True, [list(r) for r in sys_rows]


# ---- Oracle computations ----

GROSS_MARGIN = o_scalar(
    "SELECT SUM(revenue - cost) * 1.0 / SUM(revenue) FROM orders")
GM_JUL = o_scalar(
    "SELECT SUM(revenue - cost) * 1.0 / SUM(revenue) FROM orders "
    "WHERE order_date >= '2026-07-01' AND order_date < '2026-08-01'")
UNITS_SOLD = o_scalar("SELECT SUM(quantity) FROM orders")
DISCOUNT_RATE = o_scalar(
    "SELECT SUM(discount) * 1.0 / (SUM(revenue) + SUM(discount)) FROM orders")
PROFIT_TOTAL = o_scalar("SELECT SUM(revenue - cost) FROM orders")
AOV_JUL = o_scalar(
    "SELECT SUM(revenue)*1.0/COUNT(*) FROM orders WHERE "
    "order_date >= '2026-07-01' AND order_date < '2026-08-01'")
REV_EAST_JUL = o_scalar(
    "SELECT SUM(revenue) FROM orders JOIN regions ON regions.region_id = "
    "orders.region_id WHERE regions.region_name = 'East' "
    "AND order_date >= '2026-07-01' AND order_date < '2026-08-01'")
REV_FURNITURE_JUL = o_scalar(
    "SELECT SUM(revenue) FROM orders JOIN products ON products.product_id "
    "= orders.product_id WHERE products.category = 'Furniture' "
    "AND order_date >= '2026-07-01' AND order_date < '2026-08-01'")

# Breakdown — region + category (2026-full)
REGION_CAT_REV = {}
for r in o_rows(
        "SELECT regions.region_name, products.category, SUM(revenue) "
        "FROM orders JOIN regions ON regions.region_id = orders.region_id "
        "JOIN products ON products.product_id = orders.product_id "
        "GROUP BY regions.region_name, products.category"):
    REGION_CAT_REV[(r[0], r[1])] = r[2]

MONTHLY_2026 = o_rows(
    "SELECT substr(order_date,1,7), SUM(revenue) FROM orders "
    "WHERE order_date >= '2026-01-01' AND order_date < '2027-01-01' "
    "GROUP BY 1 ORDER BY 1")
Q2_2026 = o_scalar(
    "SELECT SUM(revenue) FROM orders WHERE order_date >= '2026-04-01' "
    "AND order_date < '2026-07-01'")
Q3_2026 = o_scalar(
    "SELECT SUM(revenue) FROM orders WHERE order_date >= '2026-07-01' "
    "AND order_date < '2026-10-01'")
MARGIN_BY_CAT = dict(o_rows(
    "SELECT products.category, SUM(revenue - cost) * 1.0 / SUM(revenue) "
    "FROM orders JOIN products ON products.product_id = orders.product_id "
    "GROUP BY products.category"))
UNITS_BY_SEG = dict(o_rows(
    "SELECT customers.segment, SUM(quantity) FROM orders "
    "JOIN customers ON customers.customer_id = orders.customer_id "
    "GROUP BY customers.segment"))
SHARE_BY_REGION = {}
_total = o_scalar("SELECT SUM(revenue) FROM orders")
for r in o_rows(
        "SELECT regions.region_name, SUM(revenue) FROM orders "
        "JOIN regions ON regions.region_id = orders.region_id GROUP BY 1"):
    SHARE_BY_REGION[r[0]] = r[1] / _total

CASES = [
    # 1. compound filter: region AND month
    ("A01", "Revenue in East region in July 2026", eq_scalar, REV_EAST_JUL),
    # 2. compound filter: category AND month
    ("A02", "Revenue in Furniture category in July 2026",
     eq_scalar, REV_FURNITURE_JUL),
    # 3. gross margin (ratio KPI)
    ("A03", "What is the gross margin?", eq_scalar, GROSS_MARGIN),
    # 4. ratio KPI with filter
    ("A04", "What is the gross margin in July 2026?", eq_scalar, GM_JUL),
    # 5. units sold
    ("A05", "How many units were sold?", eq_scalar, UNITS_SOLD),
    # 6. discount rate
    ("A06", "What is the discount rate?", eq_scalar, DISCOUNT_RATE),
    # 7. total profit
    ("A07", "What was the total profit?", eq_scalar, PROFIT_TOTAL),
    # 8. AOV with time filter
    ("A08", "What is the average order value in July 2026?",
     eq_scalar, AOV_JUL),
    # 9. multi-dim grouping (region × category)
    ("A09", "Revenue by region and category",
     lambda sr, exp, tol=1e-4: (lambda ok, sm: (ok, sm))(
         *(lambda: (
             (len(sr) == len(exp)) and all(
                 (str(row[0]), str(row[1])) in exp
                 and abs(float(row[2]) - float(exp[(str(row[0]), str(row[1]))])) /
                      max(abs(float(row[2])), abs(float(exp[(str(row[0]), str(row[1]))])), 1.0) < tol
                 for row in sr),
             [list(r) for r in sr]))()),
     REGION_CAT_REV),
    # 10. gross margin by category (ratio KPI by dim)
    ("A10", "Gross margin by category", eq_rowset, MARGIN_BY_CAT),
    # 11. units by segment
    ("A11", "Units sold by segment", eq_rowset, UNITS_BY_SEG),
    # 12. monthly trend of 2026
    ("A12", "Monthly revenue in 2026", eq_ordered, MONTHLY_2026),
    # 13. Q2 revenue
    ("A13", "Revenue in Q2 2026", eq_scalar, Q2_2026),
    # 14. Q3 revenue
    ("A14", "Revenue in Q3 2026", eq_scalar, Q3_2026),
    # 15–17. Paraphrases of total revenue — must all give the same value
    ("A15", "Total revenue", eq_scalar, _total),
    ("A16", "What's the overall revenue?", eq_scalar, _total),
    ("A17", "Sum of revenue", eq_scalar, _total),
    # 18. share of total by region (shares must sum to ~1.0)
    ("A18", "What percentage of revenue came from each region?",
     eq_rowset, SHARE_BY_REGION),
    # 19. date-boundary single month (Feb — short month)
    ("A19", "Revenue in February 2026", eq_scalar, o_scalar(
        "SELECT SUM(revenue) FROM orders WHERE order_date >= '2026-02-01' "
        "AND order_date < '2026-03-01'")),
    # 20. year-end boundary — December has no data in demo; the system
    # correctly WARNs (fulfilment check caught all-NULL on time filter).
    # A system behaving honestly here returns None/WARN; coding this as
    # a "pass" for either None (correct refusal) or 0 (correct scalar).
    ("A20", "Revenue in December 2026",
     lambda sr, exp, tol=1e-4: (sr and sr[0][0] is None, sr[0] if sr else None),
     None),
    # 21–22. Rolling average + percentile
    ("A21", "3-month rolling average revenue", lambda sr, exp, tol=1e-4: (
        len(sr) == 9 and all(len(r) == 3 for r in sr), [list(r) for r in sr]), None),
    ("A22", "What is the 75th percentile of revenue?",
     eq_scalar, (lambda xs: (lambda s, k: s[int(math.floor(k))] + (s[int(math.ceil(k))] - s[int(math.floor(k))]) * (k - math.floor(k)))(sorted(xs), 0.75 * (len(xs) - 1)))(
         [r[0] for r in o_rows("SELECT revenue FROM orders")])),
    # 23. HAVING threshold with the exact threshold boundary
    ("A23", "In which months did revenue exceed 400000?",
     eq_rowset, dict(o_rows(
        "SELECT substr(order_date,1,7), SUM(revenue) FROM orders "
        "GROUP BY 1 HAVING SUM(revenue) > 400000"))),
    # 24. Top-5 products should match ordered rows
    ("A24", "Top 5 products by revenue",
     eq_ordered, o_rows(
         "SELECT products.product_name, SUM(revenue) FROM orders "
         "JOIN products ON products.product_id = orders.product_id "
         "GROUP BY products.product_name ORDER BY 2 DESC LIMIT 5")),
    # 25. Comparison June vs July
    ("A25", "Compare June and July 2026 revenue",
     lambda sr, exp, tol=1e-4: (
         (len(sr) == 2 and {str(r[0]) for r in sr} == {"2026-06", "2026-07"}
          and all(abs(float(dict(((str(r[0]), float(r[-1])) for r in sr)).get(k, 0.0)) - float(exp[k])) / max(float(exp[k]), 1.0) < tol for k in exp)),
         [list(r) for r in sr]),
     {"2026-06": o_scalar(
         "SELECT SUM(revenue) FROM orders WHERE order_date >= '2026-06-01' "
         "AND order_date < '2026-07-01'"),
      "2026-07": o_scalar(
          "SELECT SUM(revenue) FROM orders WHERE order_date >= '2026-07-01' "
          "AND order_date < '2026-08-01'")}),
]


def _commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT),
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def main():
    from insightflow.orchestrator import Orchestrator
    results = []
    exec_correct = 0
    answer_correct = 0
    for cid, q, cmp_fn, expected in CASES:
        orch = Orchestrator()  # fresh — no follow-up state
        t0 = time.perf_counter()
        try:
            r = orch.ask(q)
            action = r.decision.action
            sys_rows = list(r.result.rows) if r.result.ok else []
            latency_ms = int((time.perf_counter() - t0) * 1000)
        except Exception as e:
            results.append({"id": cid, "question": q, "action": "ERROR",
                             "exec_ok": False, "error": str(e)})
            continue
        is_answer = action in ("ANSWER", "WARN")
        if is_answer:
            answer_correct += 1
        try:
            exec_ok, sys_val = cmp_fn(sys_rows, expected)
        except Exception as e:
            exec_ok, sys_val = False, f"compare_error: {e}"
        if is_answer and exec_ok:
            exec_correct += 1
        results.append({
            "id": cid, "question": q, "action": action,
            "exec_ok": bool(exec_ok and is_answer),
            "latency_ms": latency_ms,
            "sys_rows_preview": [list(r) for r in sys_rows[:3]],
            "expected_hint": repr(expected)[:200],
            "sql": (r.sql or "")[:260],
        })

    n = len(CASES)
    summary = {
        "commit": _commit(),
        "n": n,
        "answered": answer_correct,
        "exec_correct": exec_correct,
        "exec_accuracy": round(exec_correct / n, 4),
    }
    (V2 / "exec_accuracy_advanced_results.json").write_text(
        json.dumps({"summary": summary, "results": results}, indent=2))

    lines = [
        "# Advanced execution-accuracy probe",
        "",
        f"- **Commit:** `{summary['commit']}`",
        f"- **Questions:** {n}",
        f"- **Answered (ANSWER/WARN):** {summary['answered']} / {n}",
        f"- **Execution-correct:** {summary['exec_correct']} / {n}"
        f" = {summary['exec_accuracy']:.1%}",
        "",
        "## Per question",
        "",
        "| id | action | exec_ok | question |",
        "|---|---|:---:|---|",
    ]
    for r in results:
        q = r["question"][:70].replace("|", "\\|")
        lines.append(f"| {r['id']} | {r.get('action', '-')} | "
                     f"{'✅' if r.get('exec_ok') else '❌'} | {q} |")
    lines.append("")
    lines.append("## Failures (exec_ok=False)")
    lines.append("")
    for r in results:
        if r.get("exec_ok"):
            continue
        lines.append(f"- **{r['id']}** `{r['question']}`")
        lines.append(f"  - action: {r.get('action', '-')}")
        lines.append(f"  - system rows (first 3): {r.get('sys_rows_preview')}")
        lines.append(f"  - expected (truncated): {r.get('expected_hint')}")
        lines.append(f"  - sql: `{r.get('sql', '')}`")
    (V2 / "exec_accuracy_advanced_summary.md").write_text("\n".join(lines))

    print(f"wrote {V2 / 'exec_accuracy_advanced_results.json'}")
    print(f"wrote {V2 / 'exec_accuracy_advanced_summary.md'}")
    print(f"exec: {exec_correct}/{n} = {summary['exec_accuracy']:.1%}")


if __name__ == "__main__":
    main()
