"""Regenerate `expected_result` for every row in the reliability benchmark
by re-executing its `gold_sql` against the pinned demo database.

Pinning: the demo DB is seeded with `random.Random(42)` in
`backend/data/seed.py`. Re-run `python backend/data/seed.py` before
invoking this script to guarantee the live DB matches the pinned state.

Outputs:
    evaluation/dataset/reliability_benchmark_v2.jsonl
        — the same rows with `expected_result.row_count`, `.total_revenue`,
        `.units_sold`, and `.sample_rows` filled from a fresh execution
    paper_evidence/benchmark_regen.md
        — per-row before/after table, counts of changed rows

The original benchmark is preserved verbatim as
`evaluation/dataset/reliability_benchmark_v1.jsonl.archive`. The
regeneration never touches the `natural_language_question`, `gold_sql`,
`answerability`, labels, or any field other than `expected_result`.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sqlite3
import sys
from typing import Any, Dict, List

ROOT = pathlib.Path(__file__).resolve().parents[1]
BENCH = ROOT / "evaluation/dataset/reliability_benchmark.jsonl"
ARCHIVE = ROOT / "evaluation/dataset/reliability_benchmark_v1.jsonl.archive"
V2 = ROOT / "evaluation/dataset/reliability_benchmark_v2.jsonl"
DB = ROOT / "backend/data/insightflow.db"
REPORT = ROOT / "paper_evidence/benchmark_regen.md"


def run_gold(sql: str) -> List[List[Any]]:
    with sqlite3.connect(str(DB)) as c:
        return [list(r) for r in c.execute(sql).fetchall()]


def regenerate_expected(row: dict) -> Dict[str, Any]:
    """Compute a fresh `expected_result` for the row from its gold_sql.

    Shape of `expected_result`:
      - scalar-ish answerable rows: {"value": <float>, "columns": [...]}
      - breakdown rows:            {"row_count": N, "sample_rows": [...]}
      - counting rows:             {"value": <int>}
      - comparison rows:           {"row_count": 2, "periods": [...]}
      - non-answerable rows:       {} (empty)
    """
    if row.get("answerability") != "answerable":
        return {}
    sql = row.get("gold_sql") or ""
    if not sql:
        return {}
    try:
        rows = run_gold(sql)
    except Exception as e:
        return {"error": f"gold_sql failed: {e}"}
    if not rows:
        return {"row_count": 0}
    first = rows[0]
    if len(rows) == 1 and len(first) == 1:
        return {"value": first[0]}
    return {"row_count": len(rows),
            "columns": len(first),
            "sample_rows": rows[:5]}


def main() -> None:
    if not BENCH.exists():
        print(f"missing benchmark: {BENCH}", file=sys.stderr); return
    if not DB.exists():
        print(f"missing DB: {DB} — run backend/data/seed.py first",
              file=sys.stderr); return
    # Preserve v1 as an archive if we haven't already
    if not ARCHIVE.exists():
        shutil.copyfile(BENCH, ARCHIVE)
        print(f"archived v1 to {ARCHIVE}")

    rows = [json.loads(l) for l in BENCH.open()]
    changed_qids: List[tuple] = []
    with V2.open("w") as out_f:
        for r in rows:
            old = r.get("expected_result") or {}
            new = regenerate_expected(r)
            if old != new:
                changed_qids.append((r["question_id"], old, new))
            r["expected_result"] = new
            out_f.write(json.dumps(r) + "\n")
    print(f"wrote {V2}")

    # Diff report
    lines = ["# Benchmark `expected_result` regeneration",
             "",
             f"**Source:** `evaluation/dataset/reliability_benchmark.jsonl`"
             f" (archived verbatim as "
             f"`reliability_benchmark_v1.jsonl.archive`)",
             f"**Output:** `evaluation/dataset/reliability_benchmark_v2.jsonl`",
             "",
             f"**Database:** `backend/data/insightflow.db` (seeded with"
             f" `random.Random(42)` in `backend/data/seed.py`).",
             "",
             f"**Fields changed:** only `expected_result`. All other"
             f" fields — `natural_language_question`, `gold_sql`,"
             f" `answerability`, labels, signal gold values — are"
             f" preserved verbatim.",
             "",
             f"**Rows total:** {len(rows)}",
             f"**Rows whose `expected_result` changed:** "
             f"{len(changed_qids)}",
             "",
             "## Changed rows",
             "",
             "| QID | Old `expected_result` | New `expected_result` |",
             "|---|---|---|"]
    for qid, old, new in changed_qids:
        o = json.dumps(old)[:120]
        n = json.dumps(new)[:120]
        lines.append(f"| {qid} | `{o}` | `{n}` |")
    lines.append("")
    lines.append("## How to adopt v2")
    lines.append("")
    lines.append("1. Review the diff above.")
    lines.append("2. If every change looks correct against the pinned seed:")
    lines.append("")
    lines.append("    ```sh")
    lines.append("    mv evaluation/dataset/reliability_benchmark.jsonl \\")
    lines.append("       evaluation/dataset/reliability_benchmark_v1.jsonl")
    lines.append("    mv evaluation/dataset/reliability_benchmark_v2.jsonl \\")
    lines.append("       evaluation/dataset/reliability_benchmark.jsonl")
    lines.append("    ```")
    lines.append("")
    lines.append("3. Rerun `evaluation/run_paper_eval.py` and")
    lines.append("   `evaluation/compute_paper_metrics.py` — the")
    lines.append("   semantic-accuracy numbers do not depend on")
    lines.append("   `expected_result` (the oracle re-executes `gold_sql`)")
    lines.append("   but any UI or human reader that trusts")
    lines.append("   `expected_result` now has fresh values.")
    REPORT.write_text("\n".join(lines))
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
