# Corrected Diagnostic Benchmark - 14 October 2026

## Scope and provenance

This is a separate diagnostic rerun using the revised D01/D02 gold-SQL reference definitions. It does not replace the historical 27-question benchmark results or their original evidence.

- Questions per configuration: 27
- Configurations: Full, B1, A1, A2, A3
- Total runs: 135
- Benchmark SHA-256: `e9045647a5a25f03f9e8c7892c80d82f713fe0ded2883c3eb94defdda5f985fc`
- Verified CSV SHA-256: `2fc8ce2e5e19ca5173256f2aaaec00571e3a57b41db58923b78ad84e73891af3`

## Results

| Configuration | Runs | Answerable SQL validation pass | Correct CLARIFY | Execution success | Semantic match | Decision agreement | SQL validation pass (all rows) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full | 27 | 17/17 | 10/10 | 27/27 | 27/27 | 27/27 | 17/27 |
| B1 | 27 | 17/17 | 10/10 | 27/27 | 27/27 | 27/27 | 17/27 |
| A1 | 27 | 17/17 | 10/10 | 27/27 | 27/27 | 27/27 | 17/27 |
| A2 | 27 | 17/17 | 10/10 | 27/27 | 27/27 | 27/27 | 17/27 |
| A3 | 27 | 17/17 | 10/10 | 27/27 | 27/27 | 27/27 | 17/27 |

## Interpretation and limitations

- Across all configurations, 85 answerable runs were evaluated; 85 passed SQL validation.
- 50 of 50 expected clarification cases were routed to CLARIFY. These cases intentionally emitted no SQL; they must not be counted as SQL execution failures.
- Recorded execution success was 135/135; this does not establish semantic correctness.
- Implemented-matcher semantic agreement was 135/135. This is specific to the benchmark, oracle, and matcher; it is not independently validated natural-language accuracy.
- Expected-decision agreement was 135/135 on this diagnostic run only.
- The five configurations had identical recorded outputs on the audited fields. Thus, this benchmark provides no measured ablation advantage.
- Separately, the three crafted-case checks in `ablation_verification.md` passed. Those checks demonstrate targeted guard behavior, not an accuracy improvement on this benchmark.
- D01 and D02 use revised diagnostic gold SQL to compare month-level revenue and category-level changes. These are quantitative contributors, not proof of underlying business causes.
- Do not merge these metrics into the historical results table without explicitly labeling the benchmark revision and rerun.

### D01
All five configuration rows: semantic match passed; SQL validation passed.

### D02
All five configuration rows: semantic match passed; SQL validation passed.
