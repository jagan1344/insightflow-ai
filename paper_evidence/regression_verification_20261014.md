# Regression Verification — 2026-10-14

## Result

- Backend suite: 142 passed, 0 failed, 0 errors.
- Runtime: 76.34 seconds.
- Warnings: 2 FastAPI shutdown-event deprecation warnings.
- Exit code: 0.
- Command: `python -m pytest backend/tests -q --tb=short`
- Log: `backend_full_rerun_20261014.txt`
- Log SHA-256: `7BF6E52AB4028C76E2E602C42580A15D050152B450F5C19B8E232A2B9DEAC4C8`

## Provenance

- Branch: `claude/insightflow-ai-build-2neph7`
- HEAD at recording: `6daa9683c0327c3dcdb1113a90975374bb00b0a4`
- Working-tree modifications existed during the run. HEAD alone does not identify the complete tested source state.

## Key source hashes

| File | SHA-256 |
|---|---|
| `backend/insightflow/orchestrator.py` | `E013C9BCAE44C315107E6821AE054DE78AAB12CC9161DB2FA130477C5E0CCF57` |
| `backend/insightflow/reliability/decision.py` | `BC0E30F21FC4303D06C97D59AF90CEAE4D496BD989A26B15E866B7BF5ADEF197` |
| `backend/tests/test_safety.py` | `A08C3AA0EED3202DABCF753EFB0A0CDFF2E2243BB292A11DEF747A6BE497CC3D` |
| `backend/tests/test_decision_policy_stress.py` | `C655F3787E5F0E11803F8CE40C21612FB6B2BF5406C090B9355A3F23C5157E93` |

## Interpretation and limits

This is a regression-test result for the local working tree, not a benchmark accuracy result. It does not independently establish natural-language correctness, calibration, or real-world safety. Historical benchmark and revised diagnostic results remain separate.
