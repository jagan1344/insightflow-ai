# Limitations — honest picture for the paper

This document is the single place to look up every limitation of the
reported results. The paper's Limitations section should mirror these
items; the paper's abstract and headline tables should NOT make claims
that this document contradicts.

## L1. Safety: two populations, two rates

The system has **zero unsafe answers on the 25-case safety matrix**
(`backend/tests/test_safety.py::CASES`, `test_no_unsafe_answers_across_matrix`
passes with no exceptions). The safety matrix tests a controlled slice:
clean answerable questions, vague-ask → CLARIFY, out-of-schema → CLARIFY.

On the **27-question InsightFlow Reliability Benchmark**, two answerable
items (D01 and D02) produced high-confidence answers whose generated SQL
did not match the benchmark's `gold_sql` reference under the oracle:

- **D01** "Which category changed the most from June to July?" —
  decision ANSWER, confidence 0.85, reference-SQL mismatch.
- **D02** "Compare July vs June revenue" — decision ANSWER, confidence
  0.99, reference-SQL mismatch.

The mismatch rate is **2 / 17 answerable questions = 11.8%**
(95% Wilson CI 3.3–34.3%). Both cases are high-confidence reference-SQL
mismatches. The reference queries do not independently establish the
intended semantics, so this evidence alone does not prove that the
answers were semantically wrong or unsafe. Do not label these cases
confirmed unsafe answers unless independent adjudication is added.

Report the **25-case safety matrix** and the **27-question benchmark**
separately, with their scopes stated. Passing the safety matrix does not
cancel or replace the two observed reference-SQL mismatches.

## L2. Ablation null result on the current benchmark; genuine effect on an adversarial set

Full / B1 / A1 / A2 / A3 produce byte-identical per-question outputs on
all 27 benchmark questions. Pairwise McNemar b=0, c=0, p=1.0000 for both
semantic correctness and unsafe-answer rate across every pair.

An adversarial diagnostic set of 12 hand-crafted questions
(`evaluation/dataset/adversarial_diagnostic.jsonl`, results in
`paper_evidence/adversarial_results.md`) was built to stress each guard:

- **B1 (abstention gate removed) diverges from Full on 4 / 12 questions.**
  These are the direct cost of removing the gate: Full correctly routes
  the question to CLARIFY, B1 forces an ANSWER anyway with a
  near-zero confidence. B1 is strictly less safe on this set.
- **A1 (fidelity validator removed) diverges from Full on 1 / 12
  questions.** ADV05 "Average quarterly revenue by segment": Full
  routes to CLARIFY (plan_fidelity = 0.800 drops confidence below
  gate), A1 answers at confidence 0.98. The fidelity validator is
  actively protecting against a wrong answer in that case.
- **A2 (result validator removed) diverges from Full on 0 / 12.**
  **A3 (hard cap removed) diverges from Full on 0 / 12.**

Separately, `evaluation/verify_ablations.py` shows at the unit level
that **every** ablation switch (A1, A2, A3) does disable its guard on
a crafted input designed to trigger that guard — so the null results
above reflect the benchmark/adversarial coverage, not broken switches.

**Reporting rule.** The paper must not quote ablation deltas computed
only on the 27-question benchmark (they are all zero and would
mislead). The paper must report the adversarial-set divergences
alongside, with a clear statement that they come from a separate,
author-constructed stress set and are intended as a diagnostic, not an
accuracy headline.

## L3. Development set vs. held-out set

The 27-question benchmark was committed BEFORE the signal weights and
decision thresholds were tuned to their final values
(`backend/insightflow/config.py`: `threshold_high = 0.70`,
`threshold_low = 0.40`; weights in `DEFAULT_WEIGHTS`). The weights
file was last touched in the commits that introduced the plan
pipeline (`78a0a88`, 2026-09); the benchmark questions were committed
earlier (`4a2675c`). The 27 questions are therefore a **development
set**, not held-out, and the paper must call them that.

The 42-question held-out draft
(`evaluation/dataset/heldout_DRAFT.json`) is a dataset artefact only.
Every row carries a `DRAFT — requires human review before use` marker.
`paper_evidence/heldout_review_checklist.md` runs each row's
`gold_sql` against the pinned DB and flags 3 integrity issues (2
answerable rows without `gold_sql`, 1 answerable row whose `gold_sql`
returns 0 rows). **No metric derived from this file is reported in
the paper.** Until a human has ticked the checklist and the file is
renamed to drop the `_DRAFT` suffix, these questions remain
unmeasured.

## L4. Confidence calibration

ECE (10 equal-width bins) on the 27-question dev set = **0.416**. Only
3 of 10 bins are populated, so this is a noisy estimate.

The large value is driven by a structural effect: `CLARIFY` responses
carry a near-zero confidence (0.043) while scoring `semantic_match`
= True (correctly routed to clarify). Those two numbers lie in opposite
bins, which inflates ECE even though the system was correct.

The paper should either (a) report this honestly and discuss the
structural cause, or (b) report ECE separately for ANSWER-only and
CLARIFY-only populations. Do NOT report "well-calibrated" as a
summary claim.

## L5. Benchmark `expected_result` staleness

6 rows of the benchmark had `expected_result` values from a prior
seed, inconsistent with the current pinned seed
(`random.Random(42)`). Example: total_revenue stored as 3,428,686.53;
pinned DB yields 3,388,831.47.

The oracle re-executes `gold_sql` against the live DB and never trusts
the stored `expected_result`, so this did not corrupt the
semantic-accuracy numbers — but it is a data-management issue.

Mitigation: `evaluation/regenerate_benchmark.py` builds
`reliability_benchmark_v2.jsonl` with fresh `expected_result` values
and preserves v1 as
`reliability_benchmark_v1.jsonl.archive`. 17 rows change.  The
regeneration is opt-in and the current benchmark file is unchanged
until a human reviews the diff in
`paper_evidence/benchmark_regen.md` and renames v2 into place.

## L6. Baselines B0 and B2 are NOT MEASURED

- **B0** (legacy pre-plan rule-based generator) is still callable at
  `backend/insightflow/nlsql/generator.py` but, as currently wired
  (`orchestrator._legacy_ask`), is only reached on the demo dataset
  when the plan returns AMBIGUOUS. Reaching it uniformly on all 27
  benchmark questions would require monkey-patching the plan
  dispatcher, which this evaluation does not do.
- **B2** (direct LLM text-to-SQL) requires `OPENAI_API_KEY` or a
  local LLM endpoint; `backend/insightflow/llm.py` is in offline
  mode in this environment. Not run.

**Reporting rule.** The paper must mark both B0 and B2 as NOT MEASURED
in Table VI, not quote an invented number for either.

## L7. Latency numbers are deterministic-pipeline only

Measured p50 / p95 end-to-end: **4 ms / 6 ms**. These are measured
with the deterministic rule-based planner (no LLM calls) against the
2,037-row demo DB. They DO NOT include the cost of an LLM-planner path
or an MCP tool-call path.

The paper must not quote these numbers as representative of
"LLM-driven agentic BI". Either describe the measurement scope
explicitly, or run a separate LLM-backed timing experiment and
report those numbers separately.

## L8. Scope limitations

- Measured on a single project-generated 2,037-row synthetic dataset.
- Not measured against the public Tableau Superstore workbook (no
  `.xls` file was present in the checkout at evaluation time).
- Measured against SQLite 3; cross-engine compatibility (Postgres,
  BigQuery, DuckDB) is NOT MEASURED.
- One language (English). One schema shape (star-ish). One domain
  (orders / products / regions / customers).

## L9. Provenance

The results tables, per_question CSVs, adversarial outputs, and
ablation verification were **re-run on 2026-10-15 against the merged
HEAD `f302888`**, which includes recent upstream work (join_fidelity
guard, kpi_validator change, llm strict mode; 132 tests passing).

The pre-rerun versions (measurements at `3c843de`) are archived
verbatim under `paper_evidence/pinned_3c843de/`.

**Still frozen at `3c843de`** (not re-run; archived in the same
folder for safety):

- `paper_evidence/case_studies.md`
- `paper_evidence/_case_studies_raw.json`
- `paper_evidence/calibration.png`

**Headline findings are stable between the two commits.** Semantic
accuracy on answerable (0.882), unsafe-answer rate (0.074), coverage
(0.630), the 2 unsafe cases D01/D02, and the adversarial B1=4/12 +
A1=1/12 divergences are all identical. ECE drifted 0.416 → 0.422,
Brier 0.402 → 0.412, and ADV05 confidence 0.850 → 0.883 — minor
drifts, all documented in `PROVENANCE.md`.

The new join_fidelity guard **does not fire on any question in either
set**. Report this as a null finding on the tested sets; it does not
establish that the guard is effective on untested failure modes.

## L10. Reproduction command

```sh
# 1) Pin the DB
python backend/data/seed.py

# 2) Verify ablation switches disable their guards (unit-level)
DATABASE_URL="sqlite:///$(pwd)/backend/data/insightflow.db" \
  python evaluation/verify_ablations.py

# 3) Run the 27-question benchmark × 5 configs
DATABASE_URL="sqlite:///$(pwd)/backend/data/insightflow.db" \
  python evaluation/run_paper_eval.py

# 4) Build the metric tables
python evaluation/compute_paper_metrics.py

# 5) Run the adversarial diagnostic × 5 configs
DATABASE_URL="sqlite:///$(pwd)/backend/data/insightflow.db" \
  python evaluation/run_adversarial.py

# 6) Build the held-out review checklist
python evaluation/build_heldout_checklist.py

# 7) Regenerate `expected_result` from the pinned seed (opt-in)
python evaluation/regenerate_benchmark.py
```

Each script writes under `paper_evidence/` and names its output file.
No step pushes to git; no step overwrites prior results outside its own
file.
