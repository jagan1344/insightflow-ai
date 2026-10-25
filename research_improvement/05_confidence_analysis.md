# 05 — Confidence analysis (v5 provisional set)

Source: `eval/results/confidence_analysis.json` (`eval/confidence_analysis.py`). Figure: `figures/fig6_risk_coverage.pdf`.

| | A0 full pipeline | A7 safeguards off |
|---|---|---|
| answered (ANSWER/WARN) | 21 | 49 |
| correct among answered | 14 | 17 |
| wrong among answered | 7 | 32 |
| confidence of correct answers: min / median / mean | 0.979 / 0.993 / 0.988 | 0.979 / 0.993 / 0.989 |
| confidence of wrong answers: min / median / mean | 0.979 / 0.979 / 0.981 | 0.979 / 0.979 / 0.982 |
| wrong answers with confidence >= 0.9 | 7 of 7 | 32 of 32 |
| AUROC (confidence, correct vs wrong) | 0.673 | 0.685 |
| ECE, 5 equal-width bins | 0.319 | 0.637 |

Findings
- Every answer, right or wrong, scored >= 0.979. All errors are high-confidence errors. The score is
  **not calibrated**: accuracy among answered items is 0.667 (A0) and 0.347 (A7) against a mean score of ~0.985.
- There is weak separation (AUROC ~0.68). It comes mostly from answer shape: plain scalar answers receive
  0.979, grouped answers with reconciliation receive 0.99-1.0, and most wrong answers here were scalars.
  A threshold of 0.98 would have cut A0's wrong answers from 7 to 1 but correct answers from 14 to 7;
  this threshold was found by looking at the test outcomes, so it is not a validated operating point.
- Raising the existing thresholds (0.70 / 0.40) cannot reduce silent errors on this set: no answer scores
  below 0.979. The safety effect measured in `04` comes from vetoes, which cap the score at 0.30 and force
  CLARIFY, not from the score itself.
- Clarifications (84 in A0) mostly carry 0.05 (planner could not bind) or 0.30 (veto cap); these are
  decision markers, not probabilities.
- Earlier rounds show the same pattern (pooled first runs: 23 of 177 answers scored >= 0.9 were wrong;
  `evaluation/v3/results/SUMMARY_round6.md`).
