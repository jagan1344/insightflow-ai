"""End-to-end generalization probe on an UNSEEN uploaded dataset.

Pipeline:
  1. Denormalize heldout.db into a single wide CSV (the format the
     project's upload API actually accepts).
  2. Register it as an uploaded dataset via the real dataset_registry.
  3. Set it active.
  4. Run 20 unseen questions through the actual Orchestrator.
  5. Compare each result to an INDEPENDENT sqlite3 oracle against the
     original heldout.db (NOT the orchestrator's own SQL).

Reports:
  evaluation/v2/heldout_e2e_results.json
  evaluation/v2/heldout_e2e_summary.md

The oracle queries use the ORIGINAL multi-table heldout.db directly;
the orchestrator sees a flat denormalized table — so any numerical
match proves both the SQL and the planner understood the question.
"""
from __future__ import annotations

import csv
import json
import os
import pathlib
import sqlite3
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
V2 = ROOT / "evaluation" / "v2"
HELDOUT_DB = BACKEND / "data" / "heldout.db"
DEMO_DB = BACKEND / "data" / "insightflow.db"

sys.path.insert(0, str(BACKEND))
# IMPORTANT: use the DEMO DB as the DATABASE_URL (that's where
# uploaded tables are stored by the dataset_registry).
os.environ.setdefault("DATABASE_URL", f"sqlite:///{DEMO_DB}")


def _denormalize_to_csv(csv_path):
    """Join heldout.db into a flat CSV so it can be uploaded as a
    single-table dataset. The orchestrator will see:
      sale_date, office_name, territory, line_name, division,
      customer_name, tier, quantity, gross_amount, shipping_cost
    """
    with sqlite3.connect(str(HELDOUT_DB)) as c:
        rows = c.execute("""
            SELECT s.sale_date,
                   o.office_name,
                   o.territory,
                   l.line_name,
                   l.division,
                   c.customer_name,
                   c.tier,
                   s.quantity,
                   s.gross_amount,
                   s.shipping_cost
            FROM sales s
            JOIN sales_offices o ON o.office_id = s.office_id
            JOIN product_lines l ON l.line_id = s.line_id
            JOIN customers_ho  c ON c.customer_id = s.customer_id
            ORDER BY s.sale_id
        """).fetchall()
        cols = [d[0] for d in c.execute(
            "SELECT * FROM sales LIMIT 0").description]
    header = ["sale_date", "office_name", "territory", "line_name",
              "division", "customer_name", "tier", "quantity",
              "gross_amount", "shipping_cost"]
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return len(rows)


# ----------------------------------------------------------------------
# Oracle — against the ORIGINAL multi-table heldout.db
# ----------------------------------------------------------------------

def o(sql):
    with sqlite3.connect(str(HELDOUT_DB)) as c:
        return c.execute(sql).fetchall()


def o_scalar(sql):
    r = o(sql)
    return None if not r else r[0][0]


def eq_scalar(sys_rows, exp, tol=1e-4):
    if not sys_rows:
        return False, None
    v = sys_rows[0][-1]
    if v is None and exp is None:
        return True, None
    if v is None or exp is None:
        return False, v
    try:
        a, b = float(v), float(exp)
    except (TypeError, ValueError):
        return v == exp, v
    denom = max(abs(a), abs(b), 1.0)
    return abs(a - b) / denom <= tol, v


def eq_rowset(sys_rows, exp_map, tol=1e-4):
    try:
        sm = {str(r[0]): float(r[-1]) for r in sys_rows}
        em = {str(k): float(v) for k, v in exp_map.items()}
    except (TypeError, ValueError, IndexError):
        return False, None
    if set(sm) != set(em):
        return False, sm
    for k in em:
        d = max(abs(sm[k]), abs(em[k]), 1.0)
        if abs(sm[k] - em[k]) / d > tol:
            return False, sm
    return True, sm


# ----------------------------------------------------------------------
# Held-out questions (unseen during detector development)
# ----------------------------------------------------------------------

def build_cases():
    # Oracle values from the ORIGINAL heldout.db
    total_rev = o_scalar("SELECT SUM(gross_amount) FROM sales")
    east_coast_rev = o_scalar(
        "SELECT SUM(s.gross_amount) FROM sales s "
        "JOIN sales_offices o ON o.office_id = s.office_id "
        "WHERE o.office_name = 'East Coast'")
    rnd_hw_rev = o_scalar(
        "SELECT SUM(s.gross_amount) FROM sales s "
        "JOIN product_lines l ON l.line_id = s.line_id "
        "WHERE l.line_name = 'R&D Hardware'")
    mens_apparel_rev = o_scalar(
        "SELECT SUM(s.gross_amount) FROM sales s "
        "JOIN product_lines l ON l.line_id = s.line_id "
        "WHERE l.line_name = \"Men's Apparel\"")
    north_america_rev = o_scalar(
        "SELECT SUM(s.gross_amount) FROM sales s "
        "JOIN sales_offices o ON o.office_id = s.office_id "
        "WHERE o.territory = 'North America'")
    antarctica_rev = o_scalar(
        "SELECT SUM(s.gross_amount) FROM sales s "
        "JOIN sales_offices o ON o.office_id = s.office_id "
        "WHERE o.office_name = 'Antarctica Research Station'")
    null_shipping_count = o_scalar(
        "SELECT COUNT(*) FROM sales WHERE shipping_cost IS NULL")
    null_tier_count = o_scalar(
        "SELECT COUNT(*) FROM customers_ho WHERE tier IS NULL")
    platinum_rev = o_scalar(
        "SELECT SUM(s.gross_amount) FROM sales s "
        "JOIN customers_ho c ON c.customer_id = s.customer_id "
        "WHERE c.tier = 'Platinum'")
    office_rev = dict(o(
        "SELECT o.office_name, SUM(s.gross_amount) FROM sales s "
        "JOIN sales_offices o ON o.office_id = s.office_id "
        "GROUP BY o.office_name"))
    # Antarctica Research Station HAS a row? No — it has 0 sales so
    # won't appear in a plain GROUP BY. Record what the orchestrator
    # should produce.

    cases = [
        # (id, question, cmp_fn, expected)
        ("H01", "What is the total revenue?",             eq_scalar, total_rev),
        ("H02", "How many sales were there?",             eq_scalar,
         o_scalar("SELECT COUNT(*) FROM sales")),
        ("H03", "What is the total quantity?",            eq_scalar,
         o_scalar("SELECT SUM(quantity) FROM sales")),
        ("H04", "What is the average gross amount?",      eq_scalar,
         o_scalar("SELECT AVG(gross_amount) FROM sales")),
        ("H05", "What is the maximum gross amount?",      eq_scalar,
         o_scalar("SELECT MAX(gross_amount) FROM sales")),
        ("H06", "What is the minimum gross amount?",      eq_scalar,
         o_scalar("SELECT MIN(gross_amount) FROM sales")),
        # Value filters (new)
        ("H07", "Revenue in East Coast office",           eq_scalar,
         east_coast_rev),
        ("H08", "Revenue in R&D Hardware line",           eq_scalar,
         rnd_hw_rev),
        ("H09", "Revenue in Men's Apparel line",          eq_scalar,
         mens_apparel_rev),
        ("H10", "Revenue in North America territory",     eq_scalar,
         north_america_rev),
        ("H11", "Revenue for Platinum tier customers",    eq_scalar,
         platinum_rev),
        # Zero-fact-row value: must NOT silently return all-office total
        ("H12", "Revenue in Antarctica Research Station office",
         eq_scalar, "ABSTAIN"),  # flat upload cannot distinguish zero-fact from unknown
        # Null-aware
        ("H13", "How many sales have missing shipping cost?",
         eq_scalar, null_shipping_count),
        ("H14", "How many customers have missing tier?",
         eq_scalar, null_tier_count),
        # Distinct count
        ("H15", "How many distinct customers do we have?",
         eq_scalar, o_scalar(
             "SELECT COUNT(DISTINCT customer_name) FROM customers_ho")),
        # Breakdown
        ("H16", "Revenue by office_name",                 eq_rowset, office_rev),
        # ---- second wave: unknown values, compound filters, combos ----
        ("H17", "Revenue in Mars office", eq_scalar, "ABSTAIN"),
        ("H18", "Revenue in East office", eq_scalar, "ABSTAIN"),
        ("H19", "Revenue for Diamond tier customers", eq_scalar, "ABSTAIN"),
        ("H20", "Revenue in South Pole office", eq_scalar, "ABSTAIN"),
        ("H21", "Revenue in East Coast office in Men's Apparel line",
         eq_scalar, o_scalar(
             "SELECT SUM(s.gross_amount) FROM sales s "
             "JOIN sales_offices o ON o.office_id=s.office_id "
             "JOIN product_lines l ON l.line_id=s.line_id "
             "WHERE o.office_name='East Coast' AND l.line_name=\"Men's Apparel\"")),
        ("H22", "Revenue in East Coast office in R&D division for "
                "Platinum tier customers", eq_scalar, o_scalar(
             "SELECT SUM(s.gross_amount) FROM sales s "
             "JOIN sales_offices o ON o.office_id=s.office_id "
             "JOIN product_lines l ON l.line_id=s.line_id "
             "JOIN customers_ho c ON c.customer_id=s.customer_id "
             "WHERE o.office_name='East Coast' AND l.division='R&D' "
             "AND c.tier='Platinum'")),
        ("H23", "Revenue in Women's Apparel line", eq_scalar, o_scalar(
             "SELECT SUM(s.gross_amount) FROM sales s "
             "JOIN product_lines l ON l.line_id=s.line_id "
             "WHERE l.line_name=\"Women's Apparel\"")),
        ("H24", "Revenue by line_name for APAC HQ office", eq_rowset,
         dict(o("SELECT l.line_name, SUM(s.gross_amount) FROM sales s "
                "JOIN sales_offices o ON o.office_id=s.office_id "
                "JOIN product_lines l ON l.line_id=s.line_id "
                "WHERE o.office_name='APAC HQ' GROUP BY l.line_name"))),
        ("H25", "Revenue in North America territory in March 2026",
         eq_scalar, o_scalar(
             "SELECT SUM(s.gross_amount) FROM sales s "
             "JOIN sales_offices o ON o.office_id=s.office_id "
             "WHERE o.territory='North America' "
             "AND s.sale_date>='2026-03-01' AND s.sale_date<'2026-04-01'")),
        ("H26", "Revenue in the Enterprise division", eq_scalar, o_scalar(
             "SELECT SUM(s.gross_amount) FROM sales s "
             "JOIN product_lines l ON l.line_id=s.line_id "
             "WHERE l.division='Enterprise'")),
        ("H27", "How many sales in EMEA Hub office?", eq_scalar, o_scalar(
             "SELECT COUNT(*) FROM sales s "
             "JOIN sales_offices o ON o.office_id=s.office_id "
             "WHERE o.office_name='EMEA Hub'")),
        ("H28", "Average gross amount in Accessories line", eq_scalar,
         o_scalar("SELECT AVG(s.gross_amount) FROM sales s "
                  "JOIN product_lines l ON l.line_id=s.line_id "
                  "WHERE l.line_name='Accessories'")),
    ]
    return cases


# ----------------------------------------------------------------------
# Register the uploaded dataset
# ----------------------------------------------------------------------

def _register_dataset(csv_path):
    """Use the API's existing CSV ingest to register the held-out
    denormalized table."""
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.schema_agent import refresh_schema
    from insightflow.knowledge.dataset_registry import (
        register_uploaded, set_active, _slug, bootstrap,
    )
    from sqlalchemy import create_engine, text

    reset_engine()
    bootstrap()
    table = "dataset_heldout_" + _slug("heldout_e2e")
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    num_cols = {"quantity": "INTEGER", "gross_amount": "REAL",
                "shipping_cost": "REAL"}
    with open(csv_path, newline="") as f:
        rd = csv.DictReader(f)
        header = rd.fieldnames
        rows = []
        for r in rd:
            row = {}
            for k in header:
                v = r[k]
                if v == "":
                    row[k] = None
                elif k in num_cols:
                    row[k] = int(v) if num_cols[k] == "INTEGER" else float(v)
                else:
                    row[k] = v
            rows.append(row)
    coldefs = ", ".join(f'"{k}" {num_cols.get(k, "TEXT")}' for k in header)
    ins = (f'INSERT INTO "{table}" (' + ", ".join(f'"{k}"' for k in header)
           + ") VALUES (" + ", ".join(f":{k}" for k in header) + ")")
    with engine.begin() as c:
        c.execute(text(f'DROP TABLE IF EXISTS "{table}"'))
        c.execute(text(f'CREATE TABLE "{table}" ({coldefs})'))
        c.execute(text(ins), rows)
    ds_id = register_uploaded("heldout_e2e", table)
    reset_engine()
    refresh_schema()
    set_active(ds_id)
    return ds_id


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    csv_path = V2 / "heldout_denormalized.csv"
    n_rows = _denormalize_to_csv(csv_path)
    print(f"wrote {csv_path} ({n_rows} rows)")

    ds_id = _register_dataset(csv_path)
    print(f"registered dataset_id={ds_id}")

    from insightflow.orchestrator import Orchestrator
    cases = build_cases()
    results = []
    exec_ok = 0
    answered = 0
    abstained_ok = 0
    for cid, q, cmp_fn, expected in cases:
        orch = Orchestrator()
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
            answered += 1
        if expected == "ABSTAIN":
            ok = action in ("CLARIFY", "ABSTAIN")
            sys_val = action
            if ok:
                abstained_ok += 1
            results.append({
                "id": cid, "question": q, "action": action,
                "exec_ok": bool(ok), "kind": "abstain_expected",
                "sys_val": sys_val, "expected": "CLARIFY/ABSTAIN",
                "sql": (r.sql or "")[:260], "latency_ms": latency_ms,
                "decision_reason": r.decision.reason[:140]})
            continue
        try:
            ok, sys_val = cmp_fn(sys_rows, expected)
        except Exception as e:
            ok, sys_val = False, f"compare_error: {e}"
        if is_answer and ok:
            exec_ok += 1
        results.append({
            "id": cid, "question": q, "action": action,
            "exec_ok": bool(ok and is_answer),
            "sys_val": sys_val, "expected": expected,
            "sql": (r.sql or "")[:260],
            "latency_ms": latency_ms,
            "decision_reason": r.decision.reason[:140],
        })

    n = len(cases)
    n_abstain = sum(1 for c in cases if c[3] == "ABSTAIN")
    n_answerable = n - n_abstain
    summary = {
        "n_answerable": n_answerable, "n_abstain_expected": n_abstain,
        "n": n,
        "answered": answered,
        "exec_correct": exec_ok,
        "abstain_correct": abstained_ok,
        "exec_accuracy": round(exec_ok / max(n_answerable, 1), 4),
    }
    (V2 / "heldout_e2e_results.json").write_text(
        json.dumps({"summary": summary, "results": results}, indent=2))

    lines = ["# Held-out generalization — E2E execution accuracy",
             "",
             f"- **Dataset:** denormalized heldout.db with multi-word, "
             f"special-character, overlapping-name and zero-fact-row values",
             f"- **n_questions:** {n}",
             f"- **Answered (ANSWER/WARN):** {summary['answered']} / {n}",
             f"- **Execution-correct (answerable questions):** {summary['exec_correct']} / {n_answerable} "
             f"= {summary['exec_accuracy']:.1%}",
             f"- **Correct abstentions (expected CLARIFY/ABSTAIN):** "
             f"{summary['abstain_correct']} / {n_abstain}",
             "",
             "| id | action | exec_ok | question |",
             "|---|---|:---:|---|"]
    for r in results:
        q = r["question"][:70].replace("|", "\\|")
        lines.append(f"| {r['id']} | {r.get('action')} | "
                     f"{'✅' if r.get('exec_ok') else '❌'} | {q} |")
    lines.append("")
    lines.append("## Failures (exec_ok=False)")
    lines.append("")
    for r in results:
        if r.get("exec_ok"):
            continue
        lines.append(f"- **{r['id']}** `{r['question']}`")
        lines.append(f"  - action: {r.get('action')}, reason: "
                     f"{r.get('decision_reason', '')}")
        lines.append(f"  - sys value: {r.get('sys_val')}")
        lines.append(f"  - expected: {r.get('expected')}")
        lines.append(f"  - sql: `{r.get('sql', '')}`")
    (V2 / "heldout_e2e_summary.md").write_text("\n".join(lines))

    print(f"wrote {V2 / 'heldout_e2e_results.json'}")
    print(f"wrote {V2 / 'heldout_e2e_summary.md'}")
    print(f"exec: {exec_ok}/{n} = {summary['exec_accuracy']:.1%}")


if __name__ == "__main__":
    main()
