# Paper evidence — results tables

All numbers computed from `paper_evidence/per_question.csv`,
27-question InsightFlow Reliability Benchmark × 5 configurations.
Values shown as `point (lo, hi)` for 95 % Wilson CIs.

## Table VI — Baselines + Full

| Config | n | Exec acc. | Sem. acc. / answerable | Coverage | Unsafe-answer | ECE | Fidelity | p50 ms | p95 ms |
|---|---:|---|---|---|---|---:|---:|---:|---:|
| Full | 27 | 1.000 (0.875, 1.000) | 0.882 (0.657, 0.967) | 0.630 (0.442, 0.785) | 0.074 (0.021, 0.234) | 0.416 | 0.630 | 4 | 6 |
| B1 | 27 | 1.000 (0.875, 1.000) | 0.882 (0.657, 0.967) | 0.630 (0.442, 0.785) | 0.074 (0.021, 0.234) | 0.416 | 0.630 | 4 | 6 |
| A1 | 27 | 1.000 (0.875, 1.000) | 0.882 (0.657, 0.967) | 0.630 (0.442, 0.785) | 0.074 (0.021, 0.234) | 0.416 | 0.630 | 5 | 7 |
| A2 | 27 | 1.000 (0.875, 1.000) | 0.882 (0.657, 0.967) | 0.630 (0.442, 0.785) | 0.074 (0.021, 0.234) | 0.416 | 0.630 | 4 | 6 |
| A3 | 27 | 1.000 (0.875, 1.000) | 0.882 (0.657, 0.967) | 0.630 (0.442, 0.785) | 0.074 (0.021, 0.234) | 0.416 | 0.630 | 5 | 7 |

## Decision mix per config

| Config | ANSWER+WARN | CLARIFY | ABSTAIN |
|---|---:|---:|---:|
| Full | 17 | 10 | 0 |
| B1 | 17 | 10 | 0 |
| A1 | 17 | 10 | 0 |
| A2 | 17 | 10 | 0 |
| A3 | 17 | 10 | 0 |

## Pairwise McNemar vs Full

| Pair | sem. b,c (p-value) | unsafe b,c (p-value) |
|---|---|---|
| Full vs B1 | 0,0 (p=1.0000) | 0,0 (p=1.0000) |
| Full vs A1 | 0,0 (p=1.0000) | 0,0 (p=1.0000) |
| Full vs A2 | 0,0 (p=1.0000) | 0,0 (p=1.0000) |
| Full vs A3 | 0,0 (p=1.0000) | 0,0 (p=1.0000) |

## Abstention on non-answerable questions

| Config | Non-answerable n | CLARIFY+ABSTAIN rate |
|---|---:|---|
| Full | 10 | 1.000 (0.722, 1.000) |
| B1 | 10 | 1.000 (0.722, 1.000) |
| A1 | 10 | 1.000 (0.722, 1.000) |
| A2 | 10 | 1.000 (0.722, 1.000) |
| A3 | 10 | 1.000 (0.722, 1.000) |

## Notes

- Benchmark `answerability` has three values: `answerable` (17),
  `ambiguous` (4), `out_of_scope` (6). The 'non-answerable'
  population above combines the latter two.
- All 10 non-answerable questions were correctly routed to CLARIFY by
  all five configurations.
- All five configurations produced IDENTICAL per-question outputs on
  this 27-question benchmark: the ablations (A1/A2/A3) and the
  gate-removal baseline (B1) are indistinguishable from Full. See
  `discrepancies.md` and `SUMMARY.md` for interpretation.
- B0 (legacy generator) and B2 (direct LLM-to-SQL) are reported as
  NOT MEASURED — see `paper_evidence/SUMMARY.md`.
- `semantic_match` on `answerable` rows is computed by comparing the
  system's executed result against the oracle, which re-runs each
  benchmark row's `gold_sql` directly against the raw DB via sqlite3.
- Relative tolerance ε = 1e-6 (see `evaluation/oracle.py::EPSILON`).