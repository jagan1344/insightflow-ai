# 04 — Safeguard ablation analysis (v5 provisional set, 105 questions)

Same frozen tree (`00db6e2`, commit `38b60d1`), databases, questions and scorer for every configuration.
Switches: `INSIGHTFLOW_ABLATE` (default off). Raw files `eval/results/v5_<cfg>_*.json`; per-config
metrics `03_ablation_results.csv`; per-question transitions `eval/results/ablation_transitions.json`
(produced by `eval/ablation_analysis.py`). Denominators: 105 questions, 74 answerable, 31 clarify/unsupported.

## Results
| config | removed | correct /74 | answered /74 | wrong answers /105 | unnecessary clarify /74 | correct clarify /31 |
|---|---|---|---|---|---|---|
| A0 | nothing (first run) | 14 | 17 | 7 | 57 | 27 |
| A1 | semantic layer (12b) | 14 | 18 | 8 | 56 | 27 |
| A2 | confidence threshold gate | 14 | 17 | 7 | 57 | 27 |
| A3 | result validation + semantic fulfilment + empty-period check | 14 | 17 | 7 | 57 | 27 |
| A4 | plan-SQL fidelity / coverage gate | 14 | 17 | 7 | 57 | 27 |
| A5 | mention-coverage vetoes + wording audit | 17 | 38 | 28 | 36 | 24 |
| A6 | answer verifier | 14 | 17 | 7 | 57 | 27 |
| A7 | all six | 17 | 41 | 32 | 33 | 23 |
| B1 | all except semantic layer | 17 | 38 | 28 | 36 | 24 |
| B5 | all except coverage + audit | 14 | 18 | 8 | 56 | 27 |

(B2, B3, B4, B6 are identical to A7.)

## Paired transitions (which safeguard changed which question)
- **A5 vs A0 (coverage + audit removed):** 18 unnecessary-looking clarifications became wrong answers;
  3 appropriate clarifications became wrong answers (IN27, EN16, RI06); 3 clarifications became correct
  answers (HO03, HO16, EN04; HO03 and EN04 are on the author's borderline list); 81 unchanged.
  Net: these checks prevented **21** wrong answers at the cost of **3** correct answers.
- **A1 vs A0 (semantic layer removed):** 1 question (EN12, "average price per kWh") became a wrong answer;
  104 unchanged.
- **B1 vs A7 (semantic layer alone):** RI19, EN09, EN10, EN12 go from wrong to clarification (4 errors
  prevented, 0 correct answers lost). Three of these are also caught by the coverage checks, which is why
  A1 shows only one.
- **B5 vs A7 (coverage + audit alone):** 24 wrong -> clarification, 3 correct -> clarification.
- **A2, A3, A4, A6 and B2, B3, B4, B6:** no change on any of the 105 questions.

## Interpretation
- On this set the measurable error reduction comes from two components: the mention-coverage /
  wording-audit vetoes (24 errors prevented alone, 21 marginally) and the semantic layer (4 alone,
  1 marginally). Together they cut wrong answers from 32 to 7 while correct answers fell from 17 to 14.
- The confidence threshold gate, result-consistency checks, plan-fidelity gate and answer verifier did
  not change a single outcome here. This does not show they are useless (unit tests exercise them on
  constructed failures, e.g. sort-order and reconciliation errors), only that this question set did not
  trigger them. The confidence gate is inert because every executed answer scored >= 0.979; vetoes act
  by overriding the decision, not through the threshold.
- A5 is **confounded by design**: it removes two checks at once (mention coverage and wording audit),
  because both live in the same orchestrator stage (11c/11c2). Their separate contributions are not isolated.
- Even with every safeguard on, 7/105 answers are wrong; the safeguards reduce but do not remove silent errors.
- The vetoes also cost coverage: in A0, 57 of 74 answerable questions are clarified (see `06_error_analysis.md`).
