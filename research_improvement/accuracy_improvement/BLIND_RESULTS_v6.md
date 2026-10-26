# v6 blind evaluation of the improved build (frozen da925ad) — first run, ablations, confidence

Protocol: `blind/V6_PROTOCOL.md`; manifest `blind/V6_MANIFEST.sha256` committed in `4f4241c` before any run;
raw first run committed in `6276b24` before scoring. Provenance: 106 questions over 4 new synthetic schemas,
written by a separate agent process (same model family; isolation self-reported; not human-adjudicated) =>
PROVISIONAL BLIND evidence. No code was changed after the run.

## First run (A0) — exact denominators, Wilson 95% intervals
| measure | value |
|---|---|
| correct / answerable | 5/73 = 6.8% [3.0, 15.1] |
| answered / answerable | 11/73 = 15.1% |
| correct / answered answerable | 5/11 = 45.5% [21.3, 72.0] |
| wrong answers / all | 10/106 = 9.4% [5.2, 16.5] (6 wrong values + 4 answers to clarify items) |
| appropriate refusals | 29/33 (clarify 16/20, unsupported 13/13) |
| unnecessary clarifications / answerable | 62/73 |
| latency p50 / p95 | 319 ms / 1,741 ms |
| without the author's 24 borderline items | 5/58 correct, 8/82 wrong, 21/24 refusals |

**Comparison with the earlier frozen first run on its own unseen set** (R7: 38b60d1 on v5): 14/74 correct, 17/74
answered, 7/105 wrong. The improved build did NOT do better on unseen questions: 5/73 correct, 11/73 answered,
10/106 wrong. The large post-hoc gain on the revealed v5 set (14 -> 63 of 74, `DEV_COMPARISON_v5_posthoc.md`)
did not transfer. The sets differ (different schemas, wording and authoring run), so the two first runs are not a
paired comparison; but there is no evidence of improvement on new data, and the wrong-answer rate is not lower.

## The 10 wrong answers (inspected after scoring; not fixed — fixing them here would be tuning on the blind set)
| id | what happened | class |
|---|---|---|
| LS01 | "total monthly rent across active leases" -> numeric column `monthly_rent` bucketed as a month (trend) at confidence 1.0 | time-unit word read as a trend over a non-date column |
| LS12 | "unique tenants have ever signed a lease" -> `signed_dt IS NULL` | inverted date-state condition |
| LS11 | "leases that are month-to-month" -> all leases counted | condition dropped |
| WH08 | "value (quantity times unit cost)" -> two separate sums | product of two columns not supported, not refused |
| WH13 | "movements with no operator recorded" -> COUNT(DISTINCT move_type) under the right NULL filter | wrong measure |
| TC11 | distinct subscribers for March usage counted on `bill_period` (211) vs reference 214 | date-role / period convention |
| FD23 | "How many big orders?" (clarify) -> all orders counted | vague qualifier dropped |
| LS23 | "top-paying tenants" (clarify) -> lease counts | vague metric resolved by default |
| LS21, TC19 | date role guessed on clarify items | date role |

## Unnecessary clarifications (62): first cause
plan item unavailable 11; unexplained word 11; no measure bound 10; column word unused 8; value-vs-word
ambiguity ('delivered') 6; readings differ 5; table noun 3; fidelity 2; compile 2; other 4.

## Ablations on the blind set (same frozen build, data and scorer; `blind/v6_ablation_results.csv`)
| config | correct /73 | answered /73 | wrong /106 | unnecessary clarify |
|---|---|---|---|---|
| A0 full | 5 | 11 | 10 | 62 |
| A1 - semantic layer | 5 | 12 | 12 | 61 |
| A2 - confidence gate | 5 | 11 | 10 | 62 |
| A3 - result consistency | 5 | 11 | 10 | 62 |
| A4 - plan fidelity | 5 | 11 | 10 | 62 |
| A5 - coverage + wording | 9 | 34 | 29 | 39 |
| A6 - answer verifier | 5 | 11 | 10 | 62 |
| A7 all six off | 9 | 38 | 35 | 35 |
| B1 only semantic | 9 | 36 | 31 | 37 |
| B4 only plan fidelity | 9 | 36 | 33 | 37 |
| B5 only coverage + wording | 5 | 12 | 12 | 61 |
| B2, B3, B6 (only confidence gate / result consistency / verifier) | 9 | 38 | 35 | 35 |

Paired transitions (`blind/v6_transitions.json`): coverage + wording checks prevent 23 wrong answers when used
alone (cost: 4 correct answers) and 19 marginally; the semantic layer prevents 4 alone and 2 marginally; the
plan-fidelity gate prevents 2 alone and 0 marginally; the confidence gate, result-consistency checks and answer
verifier change nothing. Without any safeguard the improved planner answers 38/73 but only 9 correctly
(35/106 wrong): the gap between coverage and accuracy is a planning/grounding problem, and the vetoes are what
keep it from becoming 35 silent errors.

## Confidence (`blind/v6_confidence.json`)
A0: 15 answers, all scored >= 0.835; 9 of 10 wrong answers >= 0.9; mean 0.979 (correct) vs 0.969 (wrong);
AUROC 0.45; ECE 0.64. A7: AUROC 0.48; ECE 0.77. The score does not separate correct from wrong answers on unseen
data (no better than chance); it is not calibrated and must not be read as a probability.

## Post-hoc v5 ablations at da925ad (revealed set, not held out; `results/v5_*_posthoc_dev_ablation_da925ad.json`)
full 63 correct / 2 wrong; all safeguards off 64 / 9; semantic layer off 63 / 5; coverage + wording off 64 / 4.
On the questions the changes were tuned for, the safeguards cost one correct answer and prevent 7 errors.
