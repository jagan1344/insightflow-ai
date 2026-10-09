# Discrepancies between claims and reality

Every item here is a point where either the master prompt, an earlier
chat claim, or the stored benchmark contradicts what the code actually
does today (2026-10-09, commit `3c843de`). The research-integrity rule
is "if the code contradicts a claim, the code wins" — so each item lists
what the paper or claim says, what the code actually shows, and what
the paper should say.

## D1. The paper file does not exist in the repository

- **Claim:** master prompt refers to `paper/InsightFlow_AI_IEEE_Paper.docx`.
- **Reality:** `find . -iname "*.docx"` returns zero matches; no
  `paper/` directory exists.
- **Consequence:** the placeholder-fill step in `placeholder_fill.md`
  lists the fields the master prompt enumerates, with values measured
  from the repo, but it cannot verify them against the actual document
  layout. A human must paste the measured values into the yellow
  highlights after they review this evidence pack.

## D2. Benchmark size: 55 → 27

- **Claim (master prompt and earlier chat):** "the 55-question benchmark",
  "55 regression tests".
- **Reality:** `evaluation/dataset/reliability_benchmark.jsonl` contains
  **27** questions (not 55). The pytest regression suite consists of
  **56 nodes** across five files (`test_dataset_switching`,
  `test_evaluation`, `test_intent_coverage`, `test_pipeline`,
  `test_safety`) — but these are implementation tests, not the
  benchmark.
- **Correction:** the paper should say the benchmark currently has 27
  labelled questions; the regression test suite has 118 tests total.

## D3. Benchmark `expected_result` values are stale against the current seed

- **Claim (benchmark):** total_revenue = **3,428,686.53**;
  order_count = **2,077**; units_sold = **7,264**.
- **Reality (live DB after `python data/seed.py`):**
  total_revenue = **3,388,831.47**; order_count = **2,037**;
  units_sold = **7,164**.
- **Consequence:** six questions in the benchmark have `expected_result`
  values that no longer match a fresh seed. The current evaluation
  compares the system's output against the **gold_sql re-executed on
  the live DB**, not against `expected_result`, so this does not corrupt
  the semantic-accuracy numbers — but it is a real data-management issue
  and the paper should either (a) regenerate the benchmark against the
  current seed, or (b) describe the comparison methodology precisely
  (we rerun gold_sql; we do not trust `expected_result`).

## D4. "Zero unsafe answers" is not true on the benchmark

- **Claim (earlier chat):** "zero unsafe-answer rate on the safety matrix".
- **Reality:** on `test_safety.py` (25 safety-matrix cases) the aggregate
  test does pass — those 25 are a controlled slice. But on the full
  27-question **reliability benchmark**, Full produces **2 unsafe
  answers** (`D01` and `D02`, both answered as ANSWER at high confidence
  but semantically wrong per the gold_sql oracle). Unsafe-answer rate =
  **0.074 (95 % Wilson 0.021–0.234)**.
- **Correction:** the paper should quote the 2/27 unsafe rate with its
  CI and say that the system still clarifies on 10/10 non-answerable
  questions in the same benchmark.

## D5. Ablations A1/A2/A3 and baseline B1 produce **identical outputs** to Full on this benchmark

- **Claim (implied by having ablations):** removing the fidelity
  validator / result validator / hard cap should change results.
- **Reality:** every A1/A2/A3/B1 configuration produced byte-identical
  per-question results to Full on all 27 benchmark questions. The
  pairwise McNemar tests return `b=0, c=0, p=1.0000` for both semantic
  correctness and unsafe-answer rate across every pair.
- **Interpretation (candidate):** the 27 benchmark questions do not
  trigger the specific checks these guards exist to catch — i.e. this
  benchmark is **too easy to differentiate the ablations**. The guards
  may still matter in practice; the paper must either (a) construct
  adversarial questions that force each guard to fire and re-run, or
  (b) honestly report that on this benchmark the ablations are
  indistinguishable.
- **What NOT to do:** do not quote ablation deltas on this benchmark.
  Report them as "no measurable effect on this 27-question benchmark;
  effect size on an adversarial set is NOT MEASURED".

## D6. Clarification mix: no `ambiguous` label in the released benchmark — actually, there are 4

- **Claim (earlier chat):** "benchmark uses only two labels, `answerable`
  and `unanswerable`".
- **Reality:** the benchmark uses **three** labels — `answerable` (17),
  `ambiguous` (4), `out_of_scope` (6). There is no literal
  `unanswerable` label. The metrics code in `compute_paper_metrics.py`
  now treats `ambiguous` ∪ `out_of_scope` as the "non-answerable"
  population.

## D7. Legacy baseline B0 is still in-tree but hard to reach

- **Claim (master prompt):** B0 is the "pre-plan-pipeline rule-based
  generator".
- **Reality:** the legacy generator lives at
  `backend/insightflow/nlsql/generator.py` and is still callable through
  `orchestrator._legacy_ask`, but **only when the active dataset is
  `demo` AND the plan returns AMBIGUOUS**. Reaching it uniformly on all
  27 benchmark questions requires monkey-patching the plan dispatcher.
  Reported as **NOT MEASURED** in `results_tables.md`; the paper should
  state this honestly rather than cite an invented B0 number.

## D8. B2 (direct LLM text-to-SQL) is NOT MEASURED

- No `OPENAI_API_KEY` in this environment, no local LLM configured.
  `backend/insightflow/llm.py` defaults to `offline`.
- The paper should mark B2 as NOT MEASURED or run it in a future session
  with an API key configured.

## D9. Confidence calibration — only 3 bins populated

- 10 equal-width bins; only three bins actually contain questions
  (because the confidence distribution concentrates in [0.0–0.1],
  [0.3–0.5], and [0.9–1.0]).
- **ECE = 0.416** on the 27-question dev set.
- **Not well-calibrated.** Paper should either (a) report this honestly
  and discuss why (confidence values on CLARIFY are 0.05 → high ECE
  contribution because gold accuracy on CLARIFY is 1.0), or (b) rebuild
  calibration separately for ANSWER-only and CLARIFY-only populations.

## D10. "Twin hard caps" — stated versus implemented

- **Claim:** `C = min(S, min(σ_cov, σ_fid) + 0.05)`.
- **Reality (confidence.py):** `score = min(score, coverage + 0.05, fidelity + 0.05)`.
  Algebraically equivalent (both reduce to `min(S, min(cov,fid)+0.05)`).
  The paper's math is correct; the code just inlines the min.

## D11. Weights sum

- Weight sum from `DEFAULT_WEIGHTS` = **1.0000** (confirmed numerically).
  Paper is correct.

## D12. ANSWER threshold

- Config: `threshold_high = 0.70`, `threshold_low = 0.40`.
- Paper claims 0.70 (ANSWER) and 0.40 (WARN) — matches code.

## D13. Dates of benchmark vs threshold commits

- Threshold values and signal weights live in `backend/insightflow/config.py`.
- The weights file was last touched in the commits that introduced the
  plan pipeline (`78a0a88`, 2026-09). The benchmark questions were
  committed earlier (`4a2675c`, "Add research evaluation layer…").
- **The thresholds were tuned after the benchmark existed.** This
  violates the "never tune on held-out" rule if the benchmark was ever
  used as a hold-out. Treat the 27 current questions as a **development
  set**; use `evaluation/dataset/heldout_DRAFT.json` (after human
  review) as the actual held-out set.
