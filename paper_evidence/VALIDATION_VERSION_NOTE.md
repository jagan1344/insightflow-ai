# Benchmark Validation-Version Note

## Finding

The isolated rerun dated 2026-10-12 is not an exact reproduction
of the historical benchmark associated with commit `3c843de`.

## Verified implementation difference

The historical KPI validator falls back to the final result column
when the canonical KPI column is absent. The current validator avoids
that fallback when it detects a change/delta-style column.

This behavior is relevant to D01, whose SQL returns a `delta` column.
The historical and isolated CSVs both retain `semantic_match=False`
for D01, but the KPI-match and result-consistency signals differ.

The confidence module and `backend/insightflow/config.py` have no
diff against `3c843de` in the inspected worktree.

## Reporting decision

Retain the historical CSV as the evidence for the historical run.
Retain the isolated rerun as a separate diagnostic artifact.
Do not combine their per-question scores or describe the isolated
rerun as an exact reproduction.

The validator change addresses a KPI-level-versus-delta validation
issue; it does not establish semantic correctness for D01.
