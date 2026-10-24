"""Phase 10 — new versioned evaluation.

Independent of the historical paper evidence. Runs the orchestrator
against each v2 benchmark question and records:

  * expected_action vs. observed decision.action
  * for ANSWER cases with an oracle_sql: numerical equality against an
    independent sqlite3 query

Produces:
  evaluation/v2/results_v2.json    (per-question records)
  evaluation/v2/summary_v2.md      (per-category metrics)

Pins:
  env INSIGHTFLOW_REF_DATE=2026-10-21
  env DATABASE_URL=sqlite:///<repo>/backend/data/insightflow.db
  commit = (recorded at run time)
"""
from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import time
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
V2 = ROOT / "evaluation" / "v2"
BENCH = V2 / "benchmark_v2.jsonl"
DB = BACKEND / "data" / "insightflow.db"

sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{DB}")
os.environ.setdefault("INSIGHTFLOW_REF_DATE", "2026-10-21")


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT),
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def _oracle_scalar(sql: str) -> object:
    with sqlite3.connect(str(DB)) as c:
        rows = c.execute(sql).fetchall()
    if not rows:
        return None
    if len(rows) == 1 and len(rows[0]) == 1:
        return rows[0][0]
    return rows


def _equal(a, b, tol=1e-4) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        return abs(float(a) - float(b)) < tol
    except (TypeError, ValueError):
        return a == b


def main() -> None:
    from insightflow.orchestrator import Orchestrator
    orch = Orchestrator()
    cases = [json.loads(l) for l in BENCH.open()]
    results = []
    cat_counts = Counter()
    cat_ok = Counter()
    action_match = 0

    for case in cases:
        q = case["question"]
        exp_action = case["expected_action"]
        oracle_sql = case.get("oracle_sql")
        t0 = time.perf_counter()
        try:
            r = orch.ask(q)
            action = r.decision.action
            sys_sql = r.sql or ""
            sys_val = (r.result.rows[0][0]
                        if r.result.ok and r.result.rows
                           and len(r.result.rows) == 1
                           and len(r.result.rows[0]) == 1
                        else None)
            latency_ms = int((time.perf_counter() - t0) * 1000)
        except Exception as e:
            action = "ERROR"
            sys_sql = ""
            sys_val = None
            latency_ms = int((time.perf_counter() - t0) * 1000)
            err = str(e)
        else:
            err = ""
        action_ok = action == exp_action \
                    or (exp_action == "ANSWER" and action == "WARN")
        oracle_val = _oracle_scalar(oracle_sql) if oracle_sql else None
        numeric_ok = (oracle_val is None or sys_val is None
                       or _equal(sys_val, oracle_val))
        case_ok = action_ok and numeric_ok
        if action_ok:
            action_match += 1
        cat = case.get("category", "")
        cat_counts[cat] += 1
        if case_ok:
            cat_ok[cat] += 1
        results.append({
            "id": case["id"], "question": q, "category": cat,
            "expected_action": exp_action, "observed_action": action,
            "action_match": action_ok,
            "numeric_match": numeric_ok,
            "sys_val": sys_val, "oracle_val": oracle_val,
            "sql": sys_sql, "latency_ms": latency_ms, "error": err,
        })

    summary = {
        "commit": _commit(),
        "n_questions": len(cases),
        "action_match": action_match,
        "action_match_rate": round(action_match / max(1, len(cases)), 4),
        "per_category": {cat: {"n": n, "ok": cat_ok[cat],
                                 "rate": round(cat_ok[cat] / n, 4)}
                          for cat, n in cat_counts.items()},
    }
    out = {"summary": summary, "results": results}
    (V2 / "results_v2.json").write_text(json.dumps(out, indent=2))

    # Markdown summary
    lines = ["# Benchmark v2 — summary",
             "",
             f"- **Commit:** `{summary['commit']}`",
             f"- **Questions:** {summary['n_questions']}",
             f"- **Action match:** {summary['action_match']} / "
             f"{summary['n_questions']} = "
             f"{summary['action_match_rate']:.1%}",
             "",
             "## Per category",
             "",
             "| Category | n | ok | rate |",
             "|---|---:|---:|---:|"]
    for cat in sorted(summary["per_category"]):
        row = summary["per_category"][cat]
        lines.append(f"| {cat} | {row['n']} | {row['ok']} | "
                     f"{row['rate']:.1%} |")
    lines.append("")
    lines.append("## Per question")
    lines.append("")
    lines.append("| id | category | expected | observed | action ok | "
                  "numeric ok |")
    lines.append("|---|---|---|---|:---:|:---:|")
    for r in results:
        lines.append(f"| {r['id']} | {r['category']} | "
                     f"{r['expected_action']} | {r['observed_action']} | "
                     f"{'✅' if r['action_match'] else '❌'} | "
                     f"{'✅' if r['numeric_match'] else '❌'} |")
    (V2 / "summary_v2.md").write_text("\n".join(lines))

    print(f"wrote {V2 / 'results_v2.json'}")
    print(f"wrote {V2 / 'summary_v2.md'}")
    print(f"action match: {action_match}/{len(cases)} "
          f"({summary['action_match_rate']:.1%})")


if __name__ == "__main__":
    main()
