# Phase 6 — Confidence, decision policy, explanations

## Confidence (9 weighted signals)

Source: `backend/insightflow/reliability/confidence.py`.

| Signal | Weight (sum = 1.00) |
|---|---|
| sql_validity | 0.12 |
| schema_match | 0.10 |
| kpi_match | 0.13 |
| context_consistency | 0.13 |
| data_completeness | 0.08 |
| evidence_strength | 0.07 |
| result_consistency | 0.10 |
| intent_coverage | 0.13 |
| plan_fidelity | 0.14 |

**Twin hard cap:** `score = min(S, min(coverage, fidelity) + 0.05)` —
a semantic failure in either signal caps the overall score regardless
of the raw weighted sum.

## Decision policy

Source: `backend/insightflow/reliability/decision.py`.

Order (first match wins):

1. SQL invalid → **ABSTAIN**.
2. Execution failed → **ABSTAIN**.
3. Plan `intent_kind == AMBIGUOUS` → **CLARIFY**.
4. `plan.unavailable` non-empty → **CLARIFY**.
5. Plan validation issue → **CLARIFY**.
6. Fidelity validator failed → **CLARIFY**.
7. Result validator errored → **WARN**.
8. (orchestrator override) semantic fulfilment failed → **WARN** or
   **CLARIFY** by score.
9. (orchestrator override) relative-period resolved to empty data →
   **CLARIFY**.
10. Confidence ≥ `threshold_high` (0.70) → **ANSWER**.
11. Confidence ≥ `threshold_low` (0.40) → **WARN**.
12. Below `threshold_low` → **ABSTAIN**.

A semantic failure NEVER produces a confident ANSWER — the pre-gates
and orchestrator overrides guarantee that order.

## Explanation safety

Source: `backend/insightflow/explain/explainer.py`.

- Forecast-flavoured phrasing ("will be", "projected", "forecast",
  "predicted") is **stripped** when the plan intent is not UNSUPPORTED
  with "forecasting" in `plan.unavailable`.
- UNSUPPORTED plans with "forecasting" unavailable → explanation is
  the honest refusal, not an invented projection.
- Diagnostic explanations use the CONTRIBUTION per-dim decomposition
  and describe **observed contributing factors** rather than causal
  "root causes".

## Verified by

- `backend/tests/test_system_wide_repair.py::TestExplanationSafety`
- `backend/tests/test_defect_fixes.py::test_F_*`
- `backend/tests/test_capability_gate_invariants.py::test_invariant_semantic_failure_never_becomes_high_conf_answer`

## Known limitations

- Calibration drift as reported in historical paper evidence (ECE =
  0.416) is NOT re-measured here. See `paper_evidence/limitations.md`
  L4 for the full historical discussion.
- Confidence is a 9-signal weighted sum; it is not Platt-scaled or
  temperature-calibrated.
