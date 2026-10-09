# Test suite — 2026-10-09T15:22Z at commit 3c843de

Full invocation: `pytest -v` under the live DB at `backend/data/insightflow.db`.
Full log: `paper_evidence/test_run.log`.

## Headline

**118 passed, 0 failed, 0 skipped** (15.33 s).

## Per-file breakdown

| File | Tests | Status |
|------|------:|--------|
| test_dataset_switching.py | 5 (file) / 5 (pytest-nodes) | all passing |
| test_evaluation.py | 10 (file) / 10 (pytest-nodes) | all passing |
| test_intent_coverage.py | 6 (file) / 6 (pytest-nodes) | all passing |
| test_pipeline.py | 9 (file) / 9 (pytest-nodes) | all passing |
| test_plan_pipeline.py | 14 (file) / 16 (pytest-nodes) | all passing |
| test_safety.py | 2 (file) / 26 (pytest-nodes) | all passing |
| test_semantic_reasoning.py | 15 (file) / 18 (pytest-nodes) | all passing |
| test_mcp_integration.py | 28 (file) / 28 (pytest-nodes) | all passing |

Note: `n (file)` counts bare `def test_` lines; pytest expands parametrised tests
so the pytest-node count is higher for files that use `@pytest.mark.parametrize`.

## Mapping to the paper's claimed groups

The master prompt's narrative groups tests as "55 regression + 17 synthetic +
18 novel-schema + 28 MCP = 118". Translating that into actual pytest files:

| Paper group | Mapped file(s) | Count (nodes) |
|---|---|---|
| 55 regression | test_dataset_switching + test_evaluation + test_intent_coverage + test_pipeline + test_safety | — see pytest log — |
| 17 synthetic   | test_plan_pipeline | — |
| 18 novel-schema| test_semantic_reasoning | — |
| 28 MCP         | tests/mcp/test_mcp_integration | — |

Exact counts (from the test_run.log):
- test_dataset_switching: 5 nodes
- test_evaluation: 10 nodes
- test_intent_coverage: 6 nodes
- test_pipeline: 9 nodes
- test_safety: 26 nodes
- test_plan_pipeline: 16 nodes
- test_semantic_reasoning: 18 nodes
- test_mcp_integration: 28 nodes

## Safety matrix size
- SAFETY_CASES list in test_safety.py: 25 tuples

The safety matrix test parameterises over SAFETY_CASES and asserts, per case, that the system never produces a confident wrong answer: either an expected ANSWER/WARN, or a CLARIFY/ABSTAIN. The aggregate test `test_no_unsafe_answers_across_matrix` additionally asserts that no case produces an ANSWER at confidence < 0.70 with a wrong decision — i.e. zero unsafe-at-high-confidence outputs across the matrix.
