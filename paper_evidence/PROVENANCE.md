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

**Test-log limitation:** `paper_evidence/tests.md` records 118 passing pytest
nodes at `3c843de`, but the referenced raw `test_run.log` is absent from the
repository history checked for this audit. Treat the count as a recorded
historical result, not as independently verified from a committed raw log.

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

**None of the paper_evidence numbers were re-measured at this new HEAD.**
They remain pinned to `3c843de` for the production pipeline and to
`a7e5f95` for the evaluation scripts themselves. In particular:

- `paper_evidence/results.json`
- `paper_evidence/per_question.csv`
- `paper_evidence/results_tables.md`
- `paper_evidence/case_studies.md`
- `paper_evidence/calibration.png`
- `paper_evidence/_case_studies_raw.json`

all reflect the pipeline at `3c843de`. The adversarial-set results
(`adversarial_per_question.csv`, `adversarial_results.md`) and the
ablation-verification artefact (`ablation_verification.md`) were
measured against the local tree at the time of commit `9756ca1`
(before this merge), which also matched `a7e5f95`'s backend. The
newly merged upstream backend changes are **unmeasured** by this pack.

### If the paper will be finalized at the current HEAD

Either (a) re-run the complete reproduction command in
`limitations.md` L10 against the current HEAD and overwrite the
measurement files, or (b) state in the paper that the measurements
are frozen at `3c843de`.

Do NOT silently update code revision pointers in the paper without
rerunning. The join-fidelity guard in particular is likely to change
semantic-accuracy, unsafe-rate, and fidelity-signal numbers on both
the 27-question benchmark and the 12-question adversarial set.
