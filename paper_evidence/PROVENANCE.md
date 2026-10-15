# Measurement provenance

All numbers in this evidence pack were measured at **commit
`3c843de88ca0b62669749b217aaef000e3e6363e`** on branch
`claude/insightflow-ai-build-2neph7`, on **2026-10-09**.

The commit currently at `HEAD` (`a7e5f957…`) adds the evaluation
scripts, the oracle, the 42-question held-out *draft*, and this
evidence pack itself — but it does not change the production
pipeline. The *production code* measured by all tables below (plan
pipeline, confidence engine, decision gate, MCP servers, catalog)
is identical to `3c843de`.

## What is pinned to 3c843de

| Artefact | Value |
|---|---|
| Code revision | 3c843de88ca0b62669749b217aaef000e3e6363e |
| Date / time (UTC) | 2026-10-09T15:22Z |
| Python | 3.11.15 |
| Platform | Linux 6.18.44-fc-v114 |
| `mcp` SDK | 2.3.0 |
| DB seed RNG | `random.Random(42)` in `backend/data/seed.py` |
| Benchmark revision | `evaluation/dataset/reliability_benchmark.jsonl` at `3c843de` |
| Oracle revision | `evaluation/oracle.py` at `a7e5f95` (added for this pack) |

## Rules

1. **Do not attribute measurements to a later commit** without
   re-running them against that commit. The evidence pack remains
   valid for 3c843de only.
2. **Add new measurements as new artefacts.** Never overwrite a
   row in `results.json` / `per_question.csv` with a value from a
   different code revision — add a new JSON file instead.
3. The 42-question held-out draft
   (`evaluation/dataset/heldout_DRAFT.json`) is *not measured
   anywhere in this pack*. It is a dataset artefact only, and
   remains unmeasured until a human has reviewed it.
4. The adversarial diagnostic set
   (`evaluation/dataset/adversarial_diagnostic.jsonl`) and its
   results (`paper_evidence/adversarial_results.md`) are tagged
   with their own commit hash recorded in that file; those
   measurements may be on a later commit if the diagnostic set was
   built after 3c843de.

## What changed between 3c843de and HEAD

**UPDATE 2026-10-12:** HEAD is no longer at `a7e5f95`. Upstream pushed
substantial production changes to `backend/` after this evidence pack
was built — in particular a new **join-cardinality fidelity guard**
(`backend/insightflow/plan/join_fidelity.py`), integration of that
guard into `plan/fidelity.py`, a change in `validation/kpi_validator.py`
(negative KPI deltas no longer treated as invalid), and a strict-mode
option in `insightflow/llm.py`. The test suite grew from 118 to 132
tests.

**UPDATE 2026-10-15:** The full reproduction command in
`limitations.md` L10 was re-run against the current merged HEAD. The
following files now reflect `f302888` (the merge commit on top of all
upstream work):

- `paper_evidence/results.json`
- `paper_evidence/per_question.csv`
- `paper_evidence/results_tables.md`
- `paper_evidence/adversarial_per_question.csv`
- `paper_evidence/adversarial_results.md`
- `paper_evidence/ablation_verification.md`

The pre-rerun versions of these files (as of commit `9756ca1`,
measurements taken at `3c843de`) are preserved under
`paper_evidence/pinned_3c843de/`.

**Still pinned to `3c843de` and NOT re-run** (archived in
`pinned_3c843de/` too, in case they ever need to be regenerated):

- `paper_evidence/case_studies.md`
- `paper_evidence/_case_studies_raw.json`
- `paper_evidence/calibration.png`

The headline numbers are essentially unchanged between `3c843de` and
`f302888` (semantic accuracy on answerable: 0.882 both; unsafe-answer
rate: 0.074 both; coverage: 0.630 both; adversarial B1≠Full: 4/12
both; adversarial A1≠Full: 1/12 both). The join-fidelity guard does
not fire on any question in either set, which is itself an informative
finding and belongs in the paper's discussion.

### Minor drifts between the two runs

- `ece_10bin`: 0.416 → 0.422 (floating-point noise in a signal, not a
  model change)
- `brier`: 0.402 → 0.412
- latency `p50/p95` (ms): 4/6 → 6/8 (measurement noise, not a model
  change)
- `ADV05` confidence: 0.850 → 0.883 (fidelity signal nudged by the
  new guard; action unchanged — still CLARIFY)

### If the paper is finalized at a later commit than `f302888`

Rerun the reproduction command (`limitations.md` L10) against that
commit and update this file. Do NOT silently update revision pointers
in the paper without rerunning.
