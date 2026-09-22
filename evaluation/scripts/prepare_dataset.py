"""Build the InsightFlow Reliability Benchmark (evaluation-only).

Ground-truth policy — every field is either:
  (a) hand-authored and labelled with `gold_source: "manual"` (question,
      expected_decision, answerability, difficulty, question_type), OR
  (b) computed by executing gold SQL against the seeded demo DB and labelled
      `gold_source: "executed_gold_sql"` (expected_result, sql_validity=1,
      schema_match=1 provided SQL parses & tables/columns exist).

No numeric business answer is invented. If a question is out-of-scope /
ambiguous / diagnostic, `gold_sql` is null and `expected_result` is null —
that is itself the ground truth (there is no correct SQL to write).

Run:
    python evaluation/scripts/prepare_dataset.py

Writes:
    evaluation/dataset/reliability_benchmark.jsonl
    evaluation/dataset/reliability_benchmark.csv
    evaluation/dataset/README.md
"""
from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional


HERE = Path(__file__).resolve().parent
EVAL_DIR = HERE.parent
BACKEND = EVAL_DIR.parent / "backend"
DATASET_DIR = EVAL_DIR / "dataset"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import text  # noqa: E402
from insightflow.execution.executor import get_engine, reset_engine  # noqa: E402
from insightflow.knowledge.schema_agent import refresh_schema  # noqa: E402


# ---------------------------------------------------------------------------
# Dataclass matching the fields the spec asks for.
# ---------------------------------------------------------------------------

@dataclass
class Item:
    question_id: str
    natural_language_question: str
    database: str
    gold_sql: Optional[str]
    expected_result: Optional[Any]        # scalar / list / None
    kpi: Optional[str]
    dimension: Optional[str]
    difficulty: str                        # simple | moderate | challenging
    question_type: str                     # match / count / aggregation / breakdown / ranking / diagnostic / ambiguous / oos
    answerability: str                     # answerable | ambiguous | out_of_scope
    required_evidence: str
    expected_decision: str                 # ANSWER | WARN | CLARIFY | ABSTAIN
    # InsightFlow-specific ground truth (only where justified)
    sql_validity: Optional[float]
    schema_match: Optional[float]
    kpi_match: Optional[float]
    context_consistency: Optional[float]
    data_completeness: Optional[float]
    evidence_strength: Optional[float]
    result_consistency: Optional[float]
    gold_confidence: Optional[float]
    gold_decision: str                     # same as expected_decision (kept for clarity)
    gold_source: str                       # "manual" | "executed_gold_sql" | "manual+executed"


# ---------------------------------------------------------------------------
# Answerable questions — real gold SQL + gold results from execution.
# ---------------------------------------------------------------------------

ANSWERABLE = [
    # (id, question, gold_sql, kpi, dimension, difficulty, question_type)
    ("A01",
     "What is the total revenue?",
     "SELECT SUM(revenue) AS total_revenue FROM orders",
     "total_revenue", None, "simple", "aggregation"),
    ("A02",
     "How many orders are there in total?",
     "SELECT COUNT(*) AS order_count FROM orders",
     "order_count", None, "simple", "counting"),
    ("A03",
     "How many units have been sold?",
     "SELECT SUM(quantity) AS units_sold FROM orders",
     "units_sold", None, "simple", "aggregation"),
    ("A04",
     "What is the average order value?",
     "SELECT SUM(revenue)*1.0/COUNT(*) AS avg_order_value FROM orders",
     "avg_order_value", None, "simple", "aggregation"),
    ("A05",
     "What is the gross margin?",
     "SELECT SUM(revenue-cost)*1.0/SUM(revenue) AS gross_margin FROM orders",
     "gross_margin", None, "simple", "aggregation"),
    ("A06",
     "What is the discount rate?",
     "SELECT SUM(discount)*1.0/(SUM(revenue)+SUM(discount)) AS discount_rate FROM orders",
     "discount_rate", None, "simple", "aggregation"),
    ("A07",
     "Show revenue by region",
     "SELECT regions.region_name AS region, SUM(orders.revenue) AS total_revenue "
     "FROM orders JOIN regions ON regions.region_id = orders.region_id "
     "GROUP BY regions.region_name ORDER BY total_revenue DESC",
     "total_revenue", "region", "moderate", "breakdown"),
    ("A08",
     "Show revenue by category",
     "SELECT products.category AS category, SUM(orders.revenue) AS total_revenue "
     "FROM orders JOIN products ON products.product_id = orders.product_id "
     "GROUP BY products.category ORDER BY total_revenue DESC",
     "total_revenue", "category", "moderate", "breakdown"),
    ("A09",
     "What is the revenue by month?",
     "SELECT substr(order_date,1,7) AS month, SUM(revenue) AS total_revenue "
     "FROM orders GROUP BY substr(order_date,1,7) ORDER BY month",
     "total_revenue", "month", "moderate", "breakdown"),
    ("A10",
     "What is the gross margin by category?",
     "SELECT products.category AS category, "
     "SUM(orders.revenue-orders.cost)*1.0/SUM(orders.revenue) AS gross_margin "
     "FROM orders JOIN products ON products.product_id = orders.product_id "
     "GROUP BY products.category ORDER BY gross_margin DESC",
     "gross_margin", "category", "moderate", "breakdown"),
    ("A11",
     "Top products by revenue",
     "SELECT products.product_name AS product, SUM(orders.revenue) AS total_revenue "
     "FROM orders JOIN products ON products.product_id = orders.product_id "
     "GROUP BY products.product_name ORDER BY total_revenue DESC LIMIT 5",
     "total_revenue", "product", "moderate", "ranking"),
    ("A12",
     "What is the average order value in August?",
     "SELECT SUM(revenue)*1.0/COUNT(*) AS avg_order_value FROM orders "
     "WHERE order_date >= '2026-08-01' AND order_date < '2026-09-01'",
     "avg_order_value", None, "moderate", "aggregation"),
    ("A13",
     "What is the total revenue in July?",
     "SELECT SUM(revenue) AS total_revenue FROM orders "
     "WHERE order_date >= '2026-07-01' AND order_date < '2026-08-01'",
     "total_revenue", None, "simple", "aggregation"),
    ("A14",
     "Show revenue by segment",
     "SELECT customers.segment AS segment, SUM(orders.revenue) AS total_revenue "
     "FROM orders JOIN customers ON customers.customer_id = orders.customer_id "
     "GROUP BY customers.segment ORDER BY total_revenue DESC",
     "total_revenue", "segment", "moderate", "breakdown"),
    ("A15",
     "How many units sold by category?",
     "SELECT products.category AS category, SUM(orders.quantity) AS units_sold "
     "FROM orders JOIN products ON products.product_id = orders.product_id "
     "GROUP BY products.category ORDER BY units_sold DESC",
     "units_sold", "category", "moderate", "breakdown"),
]


# ---------------------------------------------------------------------------
# Ambiguous questions — expected CLARIFY. No gold SQL.
# ---------------------------------------------------------------------------

AMBIGUOUS = [
    ("B01", "Show me the performance.", "ambiguous", "moderate"),
    ("B02", "Tell me about the data.",  "ambiguous", "simple"),
    ("B03", "How are we doing?",        "ambiguous", "simple"),
    ("B04", "Give me a summary.",       "ambiguous", "simple"),
]


# ---------------------------------------------------------------------------
# Out-of-scope questions — expected CLARIFY. Not answerable from this DB.
# ---------------------------------------------------------------------------

OUT_OF_SCOPE = [
    ("C01", "What is the meaning of life?", "out_of_scope", "simple"),
    ("C02", "What is the weather in Paris?", "out_of_scope", "simple"),
    ("C03", "Who is the CEO of the company?", "out_of_scope", "moderate"),
    ("C04", "How much stock do we have on hand?", "out_of_scope", "moderate"),   # inventory not in schema
    ("C05", "What is the employee headcount?", "out_of_scope", "moderate"),      # HR not in schema
    ("C06", "What is the marketing spend?", "out_of_scope", "moderate"),         # not modelled
]


# ---------------------------------------------------------------------------
# Diagnostic / potentially-misleading causal — expected ANSWER but with
# evidence-supported wording; the system's answer must NOT overclaim causation.
# Gold answer here is (a) the target-month vs previous-month deltas and
# (b) the set of top negative contributors, both from executed SQL.
# ---------------------------------------------------------------------------

DIAGNOSTIC = [
    ("D01",
     "Why did revenue decrease in July?",
     # gold SQL returns the July total; the analyzer computes contributors.
     "SELECT SUM(revenue) AS total_revenue FROM orders "
     "WHERE order_date >= '2026-07-01' AND order_date < '2026-08-01'",
     "total_revenue", None, "challenging", "diagnostic"),
    ("D02",
     "Why did revenue drop in July compared to June?",
     "SELECT SUM(revenue) AS total_revenue FROM orders "
     "WHERE order_date >= '2026-07-01' AND order_date < '2026-08-01'",
     "total_revenue", None, "challenging", "diagnostic"),
]


# ---------------------------------------------------------------------------
# Execute gold SQL to derive `expected_result` deterministically.
# ---------------------------------------------------------------------------

def _run_gold(sql: str) -> list:
    """Execute a gold SQL statement and return the result set as a list of
    Python tuples (JSON-serialisable). Small round-tripping to keep floats
    comparable."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
    out = []
    for r in rows:
        row = []
        for v in r:
            if isinstance(v, float):
                row.append(round(v, 4))
            else:
                row.append(v)
        out.append(row)
    return out


def _build_answerable_items() -> list[Item]:
    items: list[Item] = []
    for qid, q, sql, kpi, dim, diff, qtype in ANSWERABLE:
        result = _run_gold(sql)
        items.append(Item(
            question_id=qid,
            natural_language_question=q,
            database="insightflow_demo",
            gold_sql=sql,
            expected_result=result,
            kpi=kpi,
            dimension=dim,
            difficulty=diff,
            question_type=qtype,
            answerability="answerable",
            required_evidence="orders table + KPI definition",
            expected_decision="ANSWER",
            sql_validity=1.0,
            schema_match=1.0,
            kpi_match=1.0,
            context_consistency=1.0,
            data_completeness=1.0,
            evidence_strength=1.0 if len(result) > 1 else 0.7,
            result_consistency=1.0,
            gold_confidence=None,   # not asserted — we don't invent a number
            gold_decision="ANSWER",
            gold_source="manual+executed",
        ))
    return items


def _build_ambiguous_items() -> list[Item]:
    return [
        Item(
            question_id=qid,
            natural_language_question=q,
            database="insightflow_demo",
            gold_sql=None,
            expected_result=None,
            kpi=None,
            dimension=None,
            difficulty=diff,
            question_type=qtype,
            answerability=qtype,
            required_evidence="user must specify KPI/dimension/time",
            expected_decision="CLARIFY",
            sql_validity=None,
            schema_match=None,
            kpi_match=0.0,
            context_consistency=0.55,   # ambiguity value from confidence.py
            data_completeness=None,
            evidence_strength=None,
            result_consistency=None,
            gold_confidence=None,
            gold_decision="CLARIFY",
            gold_source="manual",
        )
        for qid, q, qtype, diff in AMBIGUOUS
    ]


def _build_oos_items() -> list[Item]:
    return [
        Item(
            question_id=qid,
            natural_language_question=q,
            database="insightflow_demo",
            gold_sql=None,
            expected_result=None,
            kpi=None,
            dimension=None,
            difficulty=diff,
            question_type=qtype,
            answerability=qtype,
            required_evidence="not present in database",
            expected_decision="CLARIFY",  # existing policy raises out-of-scope as CLARIFY (see orchestrator.py)
            sql_validity=None,
            schema_match=None,
            kpi_match=0.0,
            context_consistency=0.10,   # out-of-scope value from confidence.py
            data_completeness=None,
            evidence_strength=None,
            result_consistency=None,
            gold_confidence=None,
            gold_decision="CLARIFY",
            gold_source="manual",
        )
        for qid, q, qtype, diff in OUT_OF_SCOPE
    ]


def _build_diagnostic_items() -> list[Item]:
    items: list[Item] = []
    for qid, q, sql, kpi, dim, diff, qtype in DIAGNOSTIC:
        result = _run_gold(sql)
        items.append(Item(
            question_id=qid,
            natural_language_question=q,
            database="insightflow_demo",
            gold_sql=sql,
            expected_result=result,
            kpi=kpi,
            dimension=dim,
            difficulty=diff,
            question_type=qtype,
            answerability="answerable",
            required_evidence="target-month + previous-month totals + dim-broken contributors",
            expected_decision="ANSWER",
            sql_validity=1.0,
            schema_match=1.0,
            kpi_match=1.0,
            context_consistency=1.0,
            data_completeness=1.0,
            evidence_strength=0.7,
            result_consistency=1.0,
            gold_confidence=None,
            gold_decision="ANSWER",
            gold_source="manual+executed",
        ))
    return items


# ---------------------------------------------------------------------------

def main() -> int:
    reset_engine()
    refresh_schema()

    items: list[Item] = []
    items += _build_answerable_items()
    items += _build_ambiguous_items()
    items += _build_oos_items()
    items += _build_diagnostic_items()

    DATASET_DIR.mkdir(parents=True, exist_ok=True)

    jsonl_path = DATASET_DIR / "reliability_benchmark.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(asdict(it), ensure_ascii=False) + "\n")

    csv_path = DATASET_DIR / "reliability_benchmark.csv"
    fieldnames = list(asdict(items[0]).keys())
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for it in items:
            row = asdict(it)
            # flatten complex fields to JSON strings for CSV
            for k, v in list(row.items()):
                if isinstance(v, (list, dict)):
                    row[k] = json.dumps(v, ensure_ascii=False)
            w.writerow(row)

    print(f"Wrote {len(items)} items to")
    print(f"  {jsonl_path}")
    print(f"  {csv_path}")

    # Breakdown by category
    from collections import Counter
    cat = Counter(it.answerability for it in items)
    dif = Counter(it.difficulty for it in items)
    dec = Counter(it.expected_decision for it in items)
    print("\nCategory counts:", dict(cat))
    print("Difficulty:     ", dict(dif))
    print("Expected decision:", dict(dec))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
