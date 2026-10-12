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

Nothing in the production pipeline. `git log 3c843de..HEAD --name-status`:

```
a7e5f95 Paper evidence pack: oracle, eval runner, ablations + 27-question results
    paper_evidence/*            (new files only)
    evaluation/oracle.py        (new)
    evaluation/run_paper_eval.py (new)
    evaluation/compute_paper_metrics.py (new)
    evaluation/dataset/heldout_DRAFT.json (new)
```

So the evidence pack's claims about `backend/`, the plan pipeline,
MCP servers, confidence engine, and decision gate are unchanged
between 3c843de and HEAD.
