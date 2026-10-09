# paper_evidence — summary

Measured 2026-10-09 at commit `3c843de` on branch
`claude/insightflow-ai-build-2neph7`. No LLM API key present; all
measurements use the deterministic rule-based plan pipeline.

## What was measured

- **Environment snapshot** (`environment.md`, `requirements_frozen.txt`)
- **Implementation facts** (`facts.md`) — every IR field, intent kind,
  signal, weight, cap formula, decision threshold, validator check,
  MCP tool, with code citations (`file:line`).
- **Full test suite** — 118 / 118 pytest nodes passed in 15.33 s;
  per-file breakdown in `tests.md`, full log in `test_run.log`.
- **Benchmark audit** — 27-question dataset, 3 answerability labels
  (`answerable` 17, `ambiguous` 4, `out_of_scope` 6). Independent
  pandas / sqlite3 oracle at `evaluation/oracle.py`.
- **Experiments**: 27 questions × 5 configurations (Full, B1, A1, A2,
  A3) = 135 runs in `per_question.csv`, aggregated to `results.json`
  and `results_tables.md` with 95 % Wilson CIs and McNemar vs Full.
- **Case studies** — the 4 questions from the prompt, Full + B1, with
  plan, SQL, result, action, confidence signals (`case_studies.md`).
- **Calibration plot** — `calibration.png` (3 of 10 bins populated;
  ECE = 0.416 on the 27-question dev set).
- **Held-out draft** — 42 new questions at
  `evaluation/dataset/heldout_DRAFT.json`, each tagged
  "DRAFT — requires human review". NOT USED in any run.

## What was NOT measured — and why

- **B0 (legacy pre-plan generator)** — still callable in-tree, but only
  through the demo→AMBIGUOUS path. Reaching it on every benchmark
  question would require monkey-patching the plan dispatcher. Marked
  NOT MEASURED.
- **B2 (direct LLM text-to-SQL)** — no `OPENAI_API_KEY` and no local LLM
  configured. `backend/insightflow/llm.py` defaults to `offline`.
- **Tool-selection accuracy for MCP** — requires an LLM to choose tools.
  NOT MEASURED.
- **Superstore generalisation** — no Superstore file in-tree during
  evaluation.
- **The paper document itself** — the .docx file the master prompt
  refers to does not exist in this checkout. See `discrepancies.md` D1.

## Headline results (27-question dev set, 95 % Wilson CIs)

- Execution accuracy, Full: **1.000 (0.875, 1.000)** — all SQL executed.
- Semantic accuracy on answerable (n=17), Full: **0.882 (0.657, 0.967)**
  — 15 / 17 correct against the gold_sql oracle.
- Coverage (ANSWER+WARN), Full: **0.630 (0.442, 0.785)** — 17 / 27.
- Abstention on non-answerable, Full: **1.000 (0.722, 1.000)** —
  10 / 10 correctly routed to CLARIFY.
- **Unsafe-answer rate, Full: 0.074 (0.021, 0.234) — 2 / 27**. The two
  unsafe cases are benchmark IDs D01 and D02, both answered at high
  confidence (0.85 and 0.99) but semantically wrong.
- Latency: p50 = 4 ms, p95 = 6 ms end-to-end on this benchmark.
- ECE = 0.416 (10 equal-width bins); only 3 bins populated so the
  calibration estimate itself is noisy.

### Full vs B1 (gate-removed)

**Identical** — B1 "forces ANSWER whenever SQL executed and succeeded"
but on this benchmark no additional queries slipped past the gate
except the ones Full already answered. McNemar `b=0, c=0, p=1.0000`
for both semantic correctness and unsafe. **Same holds for A1, A2, A3.**

This is a genuine null-result finding on the current benchmark; see
`discrepancies.md` D5 for why ("the 27 questions do not trigger the
specific checks these guards exist to catch").

## Suggested result statements

- **Abstract (one sentence):** "On a 27-question benchmark targeting
  our demo star schema, InsightFlow AI's full pipeline attains 100 %
  execution accuracy, 88 % semantic accuracy on answerable questions
  (95 % CI 66–97 %), and 100 % correct abstention on 10 non-answerable
  questions, at 2 unsafe answers out of 27 (95 % CI 2–23 %) and p95
  latency 6 ms."
- **Conclusion (one sentence):** "The confidence-cap + plan-fidelity
  guards are **not demonstrably superior** to the uncapped pipeline on
  this benchmark; adversarial examples that stress the guards remain to
  be constructed, and the 42-question held-out draft at
  `evaluation/dataset/heldout_DRAFT.json` awaits human review before it
  can be used."

## Files produced

```
paper_evidence/
├── SUMMARY.md
├── environment.md
├── requirements_frozen.txt
├── facts.md
├── tests.md
├── test_run.log
├── benchmark.md
├── per_question.csv
├── results.json
├── results_tables.md
├── case_studies.md
├── calibration.png
├── discrepancies.md
├── placeholder_fill.md
└── _case_studies_raw.json
evaluation/
├── oracle.py
├── run_paper_eval.py
├── compute_paper_metrics.py
└── dataset/
    └── heldout_DRAFT.json     ← NOT YET REVIEWED
```

## Human review checklist

1. **Authors + emails + MCP spec version** in `placeholder_fill.md`.
2. **Paste the measured values** into the actual paper .docx (not
   present in this checkout).
3. **Review the 42 held-out drafts** in
   `evaluation/dataset/heldout_DRAFT.json` — specifically verify
   `gold_sql` and `answerability` for each row. Then rename and run.
4. **Decide the public story about ablations**: either (a) report the
   null result honestly on this benchmark, or (b) build an adversarial
   set and re-run.
5. **Decide the public story about the "0 unsafe" claim**: the
   `test_safety.py` matrix passes with 0 unsafe, the benchmark produces
   2 / 27. Both numbers are real; pick the one the paper quotes and
   describe its scope precisely.
6. **Re-generate `expected_result` fields** in the benchmark against
   the current seed if you want them trustworthy — or document that
   the metrics use re-executed `gold_sql` instead.
7. **Verify every placeholder in the actual .docx** matches a row in
   `placeholder_fill.md`.
