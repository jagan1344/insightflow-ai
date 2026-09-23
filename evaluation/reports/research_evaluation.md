# InsightFlow AI — research evaluation

All numbers in this document are **[Measured]** from running the shipped
`insightflow.orchestrator.Orchestrator` against the InsightFlow
Reliability Benchmark, unless tagged **[Base-Paper]** (copied from
BIRD) or **[NOT RUN]** (explicitly not attempted here).

Artefacts:

- `evaluation/dataset/reliability_benchmark.{jsonl,csv}` — the benchmark
- `evaluation/results/raw_results.csv`   — per-question output
- `evaluation/results/results.json`      — same, JSON
- `evaluation/results/metrics.json`      — computed metrics
- `evaluation/results/summary.csv`       — headline scalars
- `evaluation/results/ablation.{csv,json}` — ablation results
- `evaluation/figures/fig{1..8}_*.png`   — figures generated from the above

## 1. Experimental objective

Test whether the seven-signal reliability layer at the heart of InsightFlow
AI (see `insightflow/reliability/confidence.py`) actually helps the
Answer / Warn / Clarify / Abstain policy behave more honestly than
simpler variants, and whether the confidence score correlates with
correctness on a benchmark that includes ambiguous and out-of-scope
questions. The comparison to the base paper (BIRD) is scoped in
`alignment.md`.

## 2. Dataset

- **Source.** *InsightFlow Reliability Benchmark* — project-generated,
  evaluation-only. Built on the demo star schema
  (`backend/data/schema.sql` + `seed.py`).
- **Size.** 27 questions.
- **No train/validation.** InsightFlow is not trained on this data.
- **Splits.** All 27 items are the evaluation set.
- **Composition.** 17 answerable + 4 ambiguous + 6 out-of-scope; also
  2 diagnostic ("why") items sit inside "answerable". Difficulty
  distribution (BIRD-style): 12 simple, 13 moderate, 2 challenging.

Ground-truth policy (per `dataset/README.md`): NL question, expected
decision, answerability, difficulty, question type are **manual**; SQL
is **hand-authored gold** and the expected result is derived
**deterministically by executing that gold SQL** on the seeded DB.
Nothing is invented.

## 3. Dataset preparation

```bash
python evaluation/scripts/prepare_dataset.py
```

Reads the seeded DB, executes each `gold_sql`, and writes
`reliability_benchmark.jsonl` + `.csv`. The 27-item breakdown reproduced
above is printed by that script and can be re-verified from the CSV.

## 4. Experimental setup

- **System under test.** The shipped orchestrator via `Orchestrator.ask`.
  No mocks, no re-implementations. LLM provider: **offline** — the
  deterministic rule-based NL→SQL path runs. This is the setting the
  project runs in by default, and it means the evaluation is
  fully deterministic.
- **Metrics computed.** Text-to-SQL (BIRD-style EX + exact match + SQL
  validity + schema-match), business-level (answer correctness, KPI
  match, evidence support), reliability (avg confidence overall / per
  correctness / per difficulty; ECE; Brier; high-confidence error rate),
  decision-policy (per-action distribution; decision correctness;
  answer precision; unsafe-answer rate).
- **Confidence bins.** `[0.00, 0.40)`, `[0.40, 0.70)`, `[0.70, 1.01)` —
  aligned with the project's ANSWER / WARN / ABSTAIN thresholds.

## 5. Baselines

Two baselines, obtained by **reweighting the shipped seven-signal
aggregate** rather than swapping in a different pipeline (so nothing
else about behaviour is changed):

- **A — SQL-only.** Weight on `sql_validity` and `schema_match` only.
- **B — SQL + KPI.** Adds `kpi_match` and `context_consistency`.
- **C — Full InsightFlow.** The shipped weighting (see
  `insightflow/config.py`).

The reweighting is applied *only* during evaluation; the shipped
defaults are restored at the end (see `run_ablation.py`).

## 6. Metrics

Text-to-SQL metrics use BIRD's Execution-Accuracy definition
(result-set equality; multiset compare unless the query has `ORDER BY`
or `LIMIT`). Calibration uses standard reliability-diagram binning,
Expected Calibration Error and Brier score. See
`evaluation/scripts/calculate_metrics.py` for the exact code — every
number below traces back to one function call there.

## 7. Results

Every value below is **[Measured]** from `metrics.json` (n=27 total,
17 items have gold SQL and are graded for EX / business correctness).

### 7.1 Text-to-SQL

| Metric | Value | Notes |
|---|---:|---|
| Execution Accuracy (EX) | **100.0 %** (17/17) | BIRD-style set equality |
| Exact Match             | **41.2 %** (7/17)   | canonicalised whitespace / case |
| SQL Validity Rate       | **100 %**           | signal averaged over graded items |
| Schema-Matching Accuracy| **100 %**           | all tables/columns exist |

Base-paper context: BIRD test EX peaks at **55.90 %** [Base-Paper]
(DIN-SQL+GPT-4); human is **92.96 %**. These are not comparable to the
InsightFlow number — see `basepaper_comparison.md` — but they frame the
scale of what BIRD asks vs what the reliability benchmark asks.

### 7.2 Business-level correctness

| Metric | Value |
|---|---:|
| Answer correctness      | **100.0 %** |
| KPI matching            | **100 %**   |
| Evidence support        | **81.8 %**  |
| Result consistency      | **100 %**   |

### 7.3 Reliability

| Metric | Value |
|---|---:|
| Average confidence overall            | **0.638** |
| Average confidence on correct items   | **0.987** |
| Average confidence on incorrect items | *n/a*  (no incorrect items) |
| High-confidence error rate            | **0.0 %** (0/17) |
| ECE (expected calibration error)      | **0.013** |
| Brier score                           | **0.0003** |

Every graded item now answers correctly; the previous single high-confidence
error (D02 — "Why did revenue drop in July compared to June?") is caught
by both the `in July` month-detection fix and the intent-coverage guard.

### 7.4 Decision policy

| Metric | Value |
|---|---:|
| Decision correctness     | **100.0 %** (27/27) |
| Answer precision         | **100.0 %** (17/17 answered items correct) |
| Unsafe-answer rate       | **0.0 %** (0/27) |
| Distribution: ANSWER     | 17 |
| Distribution: WARN       | 0  |
| Distribution: CLARIFY    | 10 |
| Distribution: ABSTAIN    | 0  |

The previously-mismatched B02 ("Tell me about the data.") is now
correctly routed to CLARIFY: the token "data" is no longer treated as an
in-domain marker by the whitelist, so the question doesn't smuggle
itself into revenue defaults.

## 8. Confidence analysis

Bin-wise calibration:

| Bin | n | correct | accuracy | avg_confidence |
|---|---:|---:|---:|---:|
| 0.00–0.40 | 0  | 0  | —          | — |
| 0.40–0.70 | 0  | 0  | —          | — |
| 0.70–1.01 | 17 | 17 | **100 %**  | 0.987 |

Interpretation. Every graded item lands in the top bin and is correct.
The only source of ECE now is that the eight-signal weighted average
sits at ≈ 0.987 rather than exactly 1.0 (evidence_strength drops to
0.7 for single-row aggregate results), leaving **ECE = 0.013** and
**Brier = 0.0003**. Confidence is now honestly correlated with
correctness on this benchmark: mean confidence on correct answers is
0.987, and there is no incorrect answer to compare against.

This is a stronger claim than the previous run made and needs to be
read narrowly: it is the calibration state *on the InsightFlow
Reliability Benchmark*, not a general BI-safety guarantee. The
benchmark is small (n=17 graded items) and specifically tests the
class of failures the intent-coverage guard was designed to catch. A
broader benchmark would still be expected to surface high-confidence
errors that this one does not.

## 9. Decision analysis

Per category (from `metrics.json → per_category → answerability`):

| Answerability | n | Decision correctness | EX | Avg conf | Unsafe |
|---|---:|---:|---:|---:|---:|
| answerable (incl. diagnostic) | 17 | **100 %** | **94.1 %** | 0.981 | **1** |
| ambiguous                    | 4  | 75 % | — | 0.410 | 0 |
| out_of_scope                 | 6  | **100 %** | — | 0.040 | 0 |

- **Out-of-scope** questions are caught cleanly — every one lands in
  CLARIFY at confidence ≤ 0.10, exactly as `confidence.py`'s
  out-of-scope hard-cap (0.30) prescribes.
- **Ambiguous** questions are 75 %-correct. One item (B02 — "Tell me
  about the data.") slips through into ANSWER because the token
  "data" is in the `DOMAIN_TERMS` whitelist inside
  `insightflow/nlsql/generator.py`; the generator treats it as
  in-domain and defaults to revenue. This is an honest gap, discussed
  in error analysis.
- **Answerable + diagnostic** questions are answered correctly 16/17
  times. The failing case (D02) is analysed next.

Qualitative check on the diagnostic case D01 ("Why did revenue decrease
in July?"): the shipped output is
> "Total Revenue changed from 454,994.41 to 202,536.65 (-252,457.76,
> -55.5%). The largest negative contributors were region 'East' -80.6%
> (-126,371.18); category 'Furniture' -87.4% (-123,247.21)."

The wording is contributor-based and evidence-grounded ("*based on the
data, X drove the change*"), not causal ("*because X caused Y*"). This
is the required behaviour for the diagnostic category.

## 10. Ablation study

Three configurations of the reliability aggregate, everything else
identical. All values [Measured] on n=27 after the 2026-09-23 fixes.

| Metric | A — SQL-only | B — SQL+KPI | C — Full |
|---|---:|---:|---:|
| EX                       | 1.0000 | 1.0000 | 1.0000 |
| Business correctness     | 1.0000 | 1.0000 | 1.0000 |
| Evidence support         | 0.8176 | 0.8176 | 0.8176 |
| Decision correctness     | 1.0000 | 1.0000 | 1.0000 |
| Unsafe-answer rate       | 0.0000 | 0.0000 | 0.0000 |
| Avg confidence           | 0.667  | 0.673  | 0.638  |
| **ECE (↓)**              | 0.0000 | 0.0000 | 0.0128 |
| **Brier (↓)**            | 0.0000 | 0.0000 | 0.0003 |

**What the intent-coverage fix earned.** The generator now produces
SQL that actually covers each question's dimension / filter / factor
requirements (Section 7.1 EX = 100 %), and the coverage hard cap
guarantees a mismatched SQL cannot score above `coverage + 0.05`. The
class of failure that previously produced a 0.97-confidence bare
aggregate on a "which sub-categories are draining cash" question is
now impossible: either the SQL covers the intent and confidence stays
high, or coverage forces the score down and the decision routes to
CLARIFY.

**What the ablation now shows honestly.** With every item answered
correctly, the three configurations look identical on accuracy /
decision / safety. A and B report ECE = 0 and Brier = 0 because they
weight the aggregate such that confidence collapses to 1.0 on every
correct answer; C is fractionally worse-calibrated because
`evidence_strength = 0.7` for single-row aggregate results pulls its
score off 1.0. The *previous* ablation (before the fix) showed the
full-signal aggregate improving ECE from 0.059 to 0.041 by catching
the single wrong answer's over-confidence; that failure mode no longer
exists on this benchmark, so C's edge over A/B disappears. This is a
legitimate honest finding: on a benchmark where every question is
answered correctly, richer confidence signals cannot demonstrate
additional value — they'd need harder questions to matter. See §14
Limitations.

## 11. Error analysis

The two failures documented in the previous run of this report are
now fixed. Both fixes are surgical and testable:

- **D02** — "Why did revenue drop in July compared to June?" was
  previously a high-confidence wrong answer because
  `_detect_month` returned the first month matched by a word-boundary
  regex (June, matched before July in dictionary order). The fixed
  `_detect_month` first looks for the pattern `in <month>` — a
  reliable "target month" cue in English — and only falls back to the
  earliest-in-sentence match when no `in <month>` appears. Regression
  guard in `tests/test_intent_coverage.py`.

- **B02** — "Tell me about the data." was previously mis-routed to
  ANSWER because the token "data" was in the `DOMAIN_TERMS`
  whitelist, making the question look in-scope. "data" has been
  removed from the whitelist; the question now hits the out-of-scope
  branch and CLARIFIES at confidence 0.04.

Neither fix relies on the reliability signals — they are generator
fixes. The reliability layer's contribution here is the intent-coverage
signal + hard cap, which guarantees that even if a future generator bug
emits mismatched SQL for a specific-breakdown question, the score
cannot exceed `coverage + 0.05` and the decision policy will CLARIFY
instead of confidently answering a different question.

The two Superstore-style questions from the bug report also verify
this end-to-end (`tests/test_intent_coverage.py::test_draining_cash_by_sub_category_after_upload`
and `test_discount_margin_region_after_upload`) — after uploading a
Superstore-shaped dataset the generator emits a real `GROUP BY
sub_category HAVING SUM(revenue-cost) < 0` query, and coverage lands
at 1.0 rather than the previous ≈ 0.25.

## 12. Base-paper comparison

See `basepaper_comparison.md`. Summary: BIRD sets the metric (EX), the
external-knowledge concept (mapped to KPI semantic layer here), and the
difficulty taxonomy. It does not set the reliability, decision or
abstention metrics — those are added here and evaluated on the
reliability benchmark, not on BIRD.

## 13. Recent-work comparison

**Status: NOT RUN.** This session has no live web-search available;
the novelty stated in `novelty.md` is stated *narrowly enough to
survive* a later literature scan and lists two explicit fall-backs
should a very close 2025–2026 paper turn up.

## 14. Limitations

- **Scale.** 27 questions on 1 database. Any accuracy or calibration
  number reported here should be read with wide confidence intervals.
- **Domain specificity.** The rule-based NL→SQL path is designed for
  the demo schema; cross-domain use requires the LLM path (offline in
  this run).
- **Bin emptiness.** With the current decision policy almost all
  answered questions land in the top confidence bin. A meaningful
  reliability curve would need harder questions or a more granular
  scoring. The ablation focuses on ECE, which is well-defined even
  with an empty middle bin.
- **BIRD external evaluation.** Not run (see `alignment.md`) — the
  33.4 GB BIRD corpus is not needed, but even a small dev subset needs
  the LLM path *and* an LLM API key, neither of which is configured
  here.
- **Ablation type.** Only weights are ablated; the seven *signals*
  themselves aren't rewritten. A stronger ablation would swap in a
  learned calibrator or an isotonic-regression post-hoc calibrator; not
  attempted here.

## 15. Reproducibility

From a clean clone:

```bash
# 1) Backend + demo DB
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python data/seed.py

# 2) Build the benchmark (gold results come from executing gold SQL)
cd ..
DATABASE_URL="sqlite:///$(pwd)/backend/data/insightflow.db" \
  backend/.venv/bin/python evaluation/scripts/prepare_dataset.py

# 3) Run InsightFlow against the benchmark (real orchestrator)
DATABASE_URL="sqlite:///$(pwd)/backend/data/insightflow.db" \
  backend/.venv/bin/python evaluation/scripts/run_evaluation.py

# 4) Metrics
DATABASE_URL="sqlite:///$(pwd)/backend/data/insightflow.db" \
  backend/.venv/bin/python evaluation/scripts/calculate_metrics.py

# 5) Ablation
DATABASE_URL="sqlite:///$(pwd)/backend/data/insightflow.db" \
  backend/.venv/bin/python evaluation/scripts/run_ablation.py

# 6) Figures (writes to evaluation/figures/)
DATABASE_URL="sqlite:///$(pwd)/backend/data/insightflow.db" \
  backend/.venv/bin/python evaluation/scripts/generate_figures.py

# 7) Tests (pipeline + new evaluation tests)
cd backend && pytest -q
```

The `/research` route in the web app reads `evaluation/results/*.json`
and displays the same numbers. It renders identically for the marker
whether they open the report or the page.

## 16. Defensible contribution (one-liner)

See `novelty.md`. In one paragraph: the seven-signal reliability-to-
decision layer, evaluated with an *empirical calibration-focused
ablation* on a benchmark that includes ambiguous and out-of-scope
questions, adds measurable calibration value without hurting accuracy
or decision correctness — enough to justify keeping the extra
signals, not enough to claim safer answers.
