"""Engine selection for the test suite.

The test modules that existed before the typed-IR engine (commit c4c6087) are specifications of the legacy
planner pipeline, which remains available as INSIGHTFLOW_ENGINE=legacy. They run against that pipeline by default.
Set INSIGHTFLOW_TEST_ENGINE=typed (or typed+legacy) to run them against the typed engine instead; the outcome of
that run is reported in research_improvement/architecture_recovery/EVALUATION_RESULTS.md. Tests written for the
typed engine (test_engine.py) are never pinned.
"""
import os

import pytest

LEGACY_SPECS = {
    "test_accuracy_mechanisms.py", "test_capability_gate_invariants.py", "test_coverage_phase2.py",
    "test_dataset_switching.py", "test_defect_fixes.py", "test_evaluation.py", "test_followup_resolver.py",
    "test_generalization_dev.py", "test_heldout_generalization.py", "test_intent_coverage.py",
    "test_join_fidelity.py", "test_llm_strict_mode.py", "test_multitable_eval.py", "test_pipeline.py",
    "test_plan_pipeline.py", "test_relational_schema.py", "test_reliability_features.py", "test_round4.py",
    "test_round4b.py", "test_round5.py", "test_round5b.py", "test_round6.py", "test_safety.py",
    "test_semantic_audit.py", "test_semantic_layer.py", "test_semantic_reasoning.py",
    "test_system_wide_repair.py", "test_value_filter.py",
}


@pytest.fixture(autouse=True, scope="module")
def _engine_for_module(request):
    # module scope: module-level fixtures (e.g. test_multitable_eval's precomputed outcomes) see the setting too
    if os.path.basename(str(request.node.fspath)) not in LEGACY_SPECS:
        yield
        return
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("INSIGHTFLOW_ENGINE", os.environ.get("INSIGHTFLOW_TEST_ENGINE", "legacy"))
        yield
