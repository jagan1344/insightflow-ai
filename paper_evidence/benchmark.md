# Benchmark + oracle audit

## 1. The dataset

`evaluation/dataset/reliability_benchmark.jsonl` — **27 questions**.

Per-row keys: `question_id, natural_language_question, database,
gold_sql, expected_result, kpi, dimension, difficulty, question_type,
answerability, required_evidence, expected_decision, sql_validity,
schema_match, kpi_match, context_consistency, data_completeness,
evidence_strength, result_consistency, gold_confidence, gold_decision,
gold_source`.

Three label fields:

| field | distinct values |
|---|---|
| `answerability` | answerable (17), ambiguous (4), out_of_scope (6) |
| `difficulty`    | simple (12), moderate (13), challenging (2) |
| `question_type` | aggregation, counting, breakdown, trend, comparison, diagnostic, correlation, ranking (varies) |

Every row has:
- a `gold_sql` (where applicable)
- an `expected_result` **but see D3 in discrepancies.md — some are stale**
- an `expected_decision`

## 2. The oracle

Written at `evaluation/oracle.py`. It is **independent** of the system
in the strict sense that it opens the raw SQLite file with the stdlib
`sqlite3` module and executes the benchmark's `gold_sql` directly —
it never invokes the plan pipeline, SQL compiler, or confidence engine.

For each benchmark row:

- If `answerability == "answerable"` and `gold_sql` is set → oracle runs
  gold_sql and returns the row set.
- If `answerability in {"ambiguous", "out_of_scope"}` → oracle returns
  `source="unanswerable"` and `value=None`; a system response is
  considered correct iff `action in {CLARIFY, ABSTAIN}`.
- If `gold_sql` is missing → `source="missing"` and the row is marked
  `needs_human_check=True`.

## 3. Comparison rule

- Numeric cells: relative tolerance ε = **1e-6** (`EPSILON` in
  `oracle.py`).
- 1×1 oracle (scalar) vs system output: compare the scalar against the
  **last column** of the system's first row.
- Breakdowns: cell-wise comparison with the same tolerance.
- No set-based comparison yet; order matters.

## 4. Held-out split

The thresholds and signal weights were committed **after** the 27
benchmark questions, so these 27 should be treated as a **development
set**, not a held-out test set.

`evaluation/dataset/heldout_DRAFT.json` — 42 draft questions covering
every category + answerability label. **DRAFT, NOT YET REVIEWED**;
every row is marked `DRAFT — requires human review before use`. The
draft is not used by any experiment and will not be used until a human
confirms every gold_sql, label, and expected_decision.
