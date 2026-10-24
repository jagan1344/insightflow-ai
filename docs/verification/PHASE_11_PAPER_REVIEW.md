# Phase 11 — Manuscript review

## Status: BLOCKED — manuscript file not in repository

The InsightFlow AI manuscript (reported as
`paper/InsightFlow_AI_IEEE_Paper.docx`) is NOT present in this
checkout. See `paper_evidence/discrepancies.md` D1 for the historical
record of this absence. I cannot edit a `.docx` that does not exist
in the repository.

## What CAN be prepared in this phase

The `paper_evidence/` directory already contains a complete
evidence-pack for the manuscript:

- `SUMMARY.md` — headline numbers for the paper
- `PROVENANCE.md` — commit pinning
- `limitations.md` — L1–L10 honest limitations
- `placeholder_fill.md` — 30 values for yellow-highlight placeholders
- `benchmark.md`, `results_tables.md`, `case_studies.md` — the paper's
  tables and case studies

In addition, this round's work adds:

- `docs/CAPABILITY_MATRIX_2026-10-23.md` — current capability matrix
- `docs/verification/PHASE_*.md` — the 12-phase audit trail
- `evaluation/v2/*` — new versioned benchmark + results

Any claim in a future revision of the paper should trace to one of
those files. The claim-to-evidence mapping, when a manuscript is
present, would use this table:

| Claim | Evidence file |
|---|---|
| 9-signal confidence engine with cap formula | `paper_evidence/placeholder_fill.md` rows 7–12 |
| 14 intent kinds (14, not 13) | `placeholder_fill.md` row 6 |
| 2,037 orders demo DB, revenue 3,388,831.47 | `placeholder_fill.md` rows 19–20 |
| 25-case safety matrix, 0 unsafe answers | `placeholder_fill.md` row 26 + `test_safety.py::CASES` |
| 27-question benchmark, 2 unsafe answers | `paper_evidence/SUMMARY.md` + `discrepancies.md` D4 |
| Ablation null result on 27 questions | `discrepancies.md` D5 + `adversarial_results.md` |
| ECE = 0.416 (dev set) | `calibration.png` + `limitations.md` L4 |
| p95 latency = 6 ms (deterministic) | `SUMMARY.md` + `limitations.md` L7 |
| 24 capability families implemented and verified | this round — `PHASE_02_CAPABILITY_MATRIX.md` |
| Statistical functions via post-aggregation | `PHASE_04_ANALYTICS.md` |
| Follow-up resolver (narrow + safe) | `PHASE_05_CONVERSATION.md` |

## Required user decisions (unchanged from historical placeholder_fill.md)

1. **Authors / affiliations / corresponding author email.** Still
   `AUTHOR MUST SUPPLY`.
2. **MCP specification revision** — pick `2026-07-28` or `2024-11-05`
   depending on which the paper cites.
3. **Decision on how to report unsafe-answer rate:** 0/25 safety
   matrix OR 2/27 benchmark (both are real; both must have scope
   stated).
4. **Decision on how to report ablations:** null result on 27-question
   benchmark + divergences on 12-question adversarial set (both
   available; must label the second as a diagnostic set, not an
   accuracy headline).
5. **Which commit the paper's results pin against.** Prior rounds
   measured at `3c843de`; this round's work is at `27f683f` or later.
   The paper must pin one commit and the rerunning instructions must
   match.
6. **Whether to also report new v2 benchmark results** (27 questions,
   100% action match) — if so, make it an ADDITIONAL section, not a
   replacement for the historical benchmark.

## Claims the paper should NOT make

- First-ever system of its kind.
- Guaranteed correctness.
- Zero hallucinations (0/25 safety matrix is not the same as "zero
  hallucinations across all possible questions").
- Perfect accuracy.
- Complete elimination of errors.
- Superiority over systems not actually evaluated.
- Causal "root causes" in diagnostic analysis — use "observed
  contributing factors" instead.

## Acceptance

Blocked until the manuscript file is added to the repository (or a
plaintext draft is explicitly requested). The evidence pack and the
updated verification docs are ready to drop into whatever manuscript
format the user supplies.
