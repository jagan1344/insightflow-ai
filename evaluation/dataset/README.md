# InsightFlow Reliability Benchmark

**Type.** Evaluation-only benchmark (no training, no validation split — the
system is not learned from the data). Built from the project's own demo
star-schema DB. Serves as the ground-truth substrate for confidence
calibration, decision-quality and ablation experiments in `evaluation/`.

**Size.** 27 questions.

| Answerability | Count |
|---|---:|
| answerable   | 17 |
| ambiguous    | 4 |
| out_of_scope | 6 |

| Difficulty (BIRD-style) | Count |
|---|---:|
| simple      | 12 |
| moderate    | 13 |
| challenging | 2 |

| Expected decision | Count |
|---|---:|
| ANSWER  | 17 |
| CLARIFY | 10 |

## Files

- `reliability_benchmark.jsonl` — one JSON object per line (canonical).
- `reliability_benchmark.csv`   — same data in a spreadsheet-friendly form.
- `README.md` — this file.

## Fields (per question)

| Field | Source |
|---|---|
| `question_id` | manual |
| `natural_language_question` | manual |
| `database` | `"insightflow_demo"` — the seeded SQLite DB |
| `gold_sql` | manual, then executed against the DB |
| `expected_result` | **result of executing `gold_sql`** — deterministic; not a hand-written number |
| `kpi`, `dimension`, `difficulty`, `question_type` | manual, following BIRD's taxonomy |
| `answerability` | manual: `answerable` / `ambiguous` / `out_of_scope` |
| `required_evidence` | manual |
| `expected_decision` | manual (`ANSWER` for answerable + diagnostic, `CLARIFY` for ambiguous/OOS per existing orchestrator policy) |
| `sql_validity`, `schema_match`, `kpi_match`, `context_consistency`, `data_completeness`, `evidence_strength`, `result_consistency` | For answerable/diagnostic items: derived from the executed gold SQL and the KPI definitions. For ambiguous/OOS: only fields the confidence engine explicitly hard-codes (`context_consistency = 0.55` for ambiguous, `0.10` for OOS) are set; the rest are `null` — we do not invent them. |
| `gold_confidence` | `null`. We do **not** assert a scalar target for the seven-signal aggregate — this benchmark scores calibration by outcome, not by a hand-picked score. |
| `gold_decision` | duplicates `expected_decision` for clarity in downstream analysis. |
| `gold_source` | traceability: `"manual"`, `"executed_gold_sql"`, or `"manual+executed"`. |

## Ground-truth policy

Ground truth is **never invented**. Three categories:

1. **Answerable + diagnostic** — hand-authored gold SQL, executed against the
   demo DB to produce `expected_result`. Seven-signal ground truth is derived
   from what the SQL touches (all tables/columns exist → `schema_match = 1`,
   KPI is a registered KPI → `kpi_match = 1`, etc.).
2. **Ambiguous** — no gold SQL. Correct behaviour is `CLARIFY`. Seven-signal
   ground truth is set only where the confidence engine hard-codes it
   (`context_consistency = 0.55`).
3. **Out-of-scope** — no gold SQL. Correct behaviour per existing orchestrator
   policy is `CLARIFY` (out-of-scope explicitly routes to CLARIFY in
   `insightflow/orchestrator.py`; the seven-signal aggregate is hard-capped
   at 0.30). Seven-signal ground truth is set only where the engine
   hard-codes it (`context_consistency = 0.10`).

## No data leakage

- These 27 questions are **not** copied into the rule-based generator's
  examples.
- No hardcoded string answers to any specific question exist in the
  pipeline.
- The rule-based generator matches on generic keywords (KPI synonyms,
  dimension words like "by region", month names, `top`/`bottom`, causal
  cue-words); it does not memorise the benchmark.

## Rebuilding

```bash
DATABASE_URL="sqlite:///$(pwd)/backend/data/insightflow.db" \
  backend/.venv/bin/python evaluation/scripts/prepare_dataset.py
```

## BIRD external subset

**Status: NOT RUN.** Reason: (a) no LLM API key is configured in this
environment, and InsightFlow's rule-based generator is tuned to the demo
schema so it cannot translate general BIRD-domain queries; (b) downloading
the full BIRD SQLite corpus (33.4 GB) is unnecessary for a small sanity
subset, but even a small subset requires the LLM path to be usable. See
`evaluation/reports/alignment.md` for the honest framing.
