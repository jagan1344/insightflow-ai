# Phase 12 — Final submission checklist

## Verdict: **NOT READY** — manuscript + author info blockers

The implementation and evaluation deliverables are complete and
verified. Submission is blocked on items that only the user / author
can supply.

## Submission-readiness checks

| # | Item | Status | Blocker |
|---|---|---|---|
| 1 | Target conference / journal identified | ❌ NOT CONFIRMED | user must name venue (prior rounds referred to an IEEE conference) |
| 2 | Official formatting template | ❌ NOT CONFIRMED | depends on venue; e.g. IEEE conference template |
| 3 | Page limits satisfied | ❌ NOT CONFIRMED | depends on venue + manuscript |
| 4 | Required template used | ❌ NOT CONFIRMED | manuscript file absent |
| 5 | Author names & affiliations | ❌ NOT CONFIRMED | `placeholder_fill.md` row 1 |
| 6 | Corresponding author confirmed | ❌ NOT CONFIRMED | same |
| 7 | Required author emails | ❌ NOT CONFIRMED | same |
| 8 | References complete + consistent | ❌ NOT CONFIRMED | depends on manuscript |
| 9 | Figures and tables legible | ✅ (`calibration.png` + markdown tables in `paper_evidence/`) | — |
| 10 | Equations correct | ✅ (confidence formula + cap formula verified in code) | — |
| 11 | Reported metrics match evidence | ✅ (all metrics traceable to `paper_evidence/` + `evaluation/v2/`) | — |
| 12 | Code + reproducibility consistent | ✅ (`PHASE_09_RELEASE.md`) | — |
| 13 | Repository publication status | ⚠️ public repo at `jagan1344/insightflow-ai`; the manuscript may or may not want to disclose this URL | user decision |
| 14 | Required disclosures | ❌ NOT CONFIRMED | venue-specific |
| 15 | Final PDF compiles | ❌ NOT CONFIRMED | no manuscript |
| 16 | No unintended placeholders | n/a | depends on manuscript draft |
| 17 | Submission package complete | ❌ NOT READY | manuscript absent |
| 18 | Final version reviewed for unsupported claims | n/a | depends on manuscript |

## What IS ready

- Implementation (`backend/`) — 264 passing backend tests, web
  typecheck clean.
- Verification docs — `docs/verification/PHASE_01` through `PHASE_12`.
- New versioned evaluation — `evaluation/v2/` with 27 questions,
  100% action match, raw results in `results_v2.json`.
- Capability matrix — `docs/CAPABILITY_MATRIX_2026-10-23.md` +
  `docs/verification/PHASE_02_CAPABILITY_MATRIX.md`.
- Historical evidence pack — `paper_evidence/*` (preserved).

## Specific unresolved blockers

1. Add `paper/InsightFlow_AI_IEEE_Paper.docx` (or whatever format you
   want) to the repository.
2. Supply author names, affiliations, emails, corresponding author.
3. Choose MCP spec revision string.
4. Decide primary unsafe-answer-rate story (0/25 safety matrix OR
   2/27 benchmark — scope must be stated for whichever is quoted).
5. Decide whether to report v2 benchmark results in addition to the
   historical pack.
6. Confirm venue + formatting template.

## Required user actions

- Provide the manuscript file.
- Fill in author metadata.
- Confirm venue.
- Confirm whether the public repository URL should be disclosed in
  the paper.
