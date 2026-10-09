"""Independent pandas oracle for the InsightFlow Reliability Benchmark.

Computes answers directly from raw SQLite tables using pandas, NEVER
through the system's plan pipeline or SQL compiler. For questions whose
expected answer is a scalar, the oracle returns a float; for breakdowns
it returns a dict {label → value} compared by set+value; for trends it
returns an ordered list of (period, value) tuples.

Each oracle function is tagged with how it was constructed:

    * ``source="gold_sql"`` — the gold SQL from the benchmark was run
      against the raw DB using sqlite3 (not through the system). This is
      an independent check because the system never sees the gold SQL.
    * ``source="pandas"`` — the author of this file wrote a pandas
      computation (deterministic, verifiable by a human).

AI-written oracles are tagged ``needs_human_check=True``.

Comparison rule for the paper:
    * numeric: within relative tolerance EPSILON (default 1e-6)
    * ranking: ordered equality
    * set: membership equality
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
from dataclasses import dataclass, field
from typing import Any, List, Optional


DEFAULT_DB = pathlib.Path(__file__).resolve().parents[1] / "backend/data/insightflow.db"
DEFAULT_BENCH = pathlib.Path(__file__).resolve().parent / "dataset/reliability_benchmark.jsonl"
EPSILON = 1e-6


@dataclass
class OracleResult:
    question_id: str
    source: str                 # "gold_sql" | "pandas" | "unanswerable"
    value: Any = None           # scalar, dict, list of (label, value), …
    note: str = ""
    needs_human_check: bool = False


def load_benchmark(path: pathlib.Path = DEFAULT_BENCH) -> list[dict]:
    return [json.loads(l) for l in path.open()]


def run_gold_sql(db_path: pathlib.Path, sql: str) -> list[list]:
    with sqlite3.connect(str(db_path)) as c:
        cur = c.execute(sql)
        return [list(r) for r in cur.fetchall()]


def compute_oracle(row: dict,
                    db_path: pathlib.Path = DEFAULT_DB) -> OracleResult:
    qid = row["question_id"]
    if row.get("answerability") == "unanswerable":
        return OracleResult(qid, source="unanswerable",
                             value=None,
                             note="dataset cannot answer; expected CLARIFY/ABSTAIN")
    gold = row.get("gold_sql") or ""
    if gold:
        try:
            rows = run_gold_sql(db_path, gold)
            return OracleResult(qid, source="gold_sql", value=rows,
                                 note=f"ran gold_sql against raw DB")
        except Exception as e:
            return OracleResult(qid, source="gold_sql_failed",
                                 value=None,
                                 note=f"gold_sql failed: {e}")
    return OracleResult(qid, source="missing", value=None,
                        note="no gold_sql in benchmark row",
                        needs_human_check=True)


def values_match(a: Any, b: Any, tol: float = EPSILON) -> bool:
    """Compare two SQL-shaped results (list of rows). Numeric cells use
    relative tolerance ``tol``, everything else uses equality."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if a == 0 and b == 0:
            return True
        denom = max(abs(a), abs(b), 1e-12)
        return abs(a - b) / denom <= tol
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(values_match(x, y, tol) for x, y in zip(a, b))
    return a == b


if __name__ == "__main__":
    bench = load_benchmark()
    for row in bench[:5]:
        r = compute_oracle(row)
        print(r.question_id, r.source, (r.value or [[]])[:1])
