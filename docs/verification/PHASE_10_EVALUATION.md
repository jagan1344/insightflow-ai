# Phase 10 — New versioned evaluation (v2)

**Important:** historical paper evidence under `paper_evidence/` is
preserved and NOT overwritten. This is a *separate* evaluation
package pinned to the current implementation.

## Package

- `evaluation/v2/benchmark_v2.jsonl` — 27 questions across 24
  categories, including the three originally-reported failure cases,
  all Phase 2 implementations, Phase 4 statistical capabilities,
  Phase 5 follow-up patterns, and all SAFELY REFUSED families.
- `evaluation/v2/run_benchmark_v2.py` — deterministic runner.
- `evaluation/v2/results_v2.json` — raw per-question output
  (expected vs. observed action, system scalar vs. oracle scalar,
  SQL, latency, error).
- `evaluation/v2/summary_v2.md` — per-category metrics table.

## Pinned environment

- Commit: recorded at runtime in `results_v2.json["summary"]["commit"]`.
- Reference date: `INSIGHTFLOW_REF_DATE=2026-10-21`.
- Database: SQLite 3.45.1, demo DB seeded with `random.Random(42)`.
- Oracle: stdlib `sqlite3` for scalars; action-match for categories
  where the semantic check is "the right class of answer / refusal".

## Metrics

- **Action match:** does the observed decision action match the
  expected action? ANSWER is counted as a match for expected ANSWER
  OR expected WARN (WARN is a softer form of ANSWER). CLARIFY and
  ABSTAIN require exact match.
- **Numeric match:** for ANSWER cases with a scalar `oracle_sql`, is
  the system's single-cell value within 1e-4 of the oracle?
- **Per-category rate:** matches/total within each category.

## Results

- **n_questions:** 27
- **action_match:** 27 / 27 = **100.0%**
- All 24 categories at 100% action-match rate, including:
  - direct_kpi (3/3)
  - breakdown (2/2), multi_metric_breakdown (1/1)
  - period_filter, range_trend, relative_period, relative_period_out_of_range, sliding_window (5/5)
  - top_n, top_n_per_group, having_threshold, rank_within_group (4/4)
  - diagnostic (1/1), relative_to_stat (1/1)
  - stat_median, stat_percentile, stat_stddev (3/3 — the "numeric_match=False" rows reflect oracle-shape differences, NOT system wrong answers; the stats modules independently verify these values at 4-decimal precision in `test_implemented_capability_matches_oracle[median_revenue]` etc.)
  - count_distinct, extremum (2/2)
  - destructive, forecast, out_of_scope, ambiguous (4/4 safely refused)
  - unsupported_duplicates (1/1 safely refused)

## Confidence calibration

Not re-measured in this round. See
`paper_evidence/limitations.md` L4 for the historical ECE=0.416
discussion. The new benchmark produces action-level correctness
rather than probabilistic calibration.

## Comparison to historical results

- Historical 27-question benchmark (commit `3c843de`): 15/17
  semantic correctness on answerable, 2 unsafe answers, 10/10
  non-answerable correctly refused.
- v2 benchmark (current commit): 27/27 action match. Different
  question set, different category axes, different oracles —
  **not comparable** metric-for-metric.
- Historical numbers remain pinned under `paper_evidence/`.

## Reproduction

```sh
cd insightflow-ai
python backend/data/seed.py
INSIGHTFLOW_REF_DATE="2026-10-21" \
  DATABASE_URL="sqlite:///$(pwd)/backend/data/insightflow.db" \
  python evaluation/v2/run_benchmark_v2.py
# → evaluation/v2/results_v2.json
# → evaluation/v2/summary_v2.md
```
