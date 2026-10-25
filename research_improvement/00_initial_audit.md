# 00 — Initial audit (2026-10-25)

## Repository state at mission start
- Root: `/home/user/insightflow-ai`; branch `claude/insightflow-ai-build-2neph7`.
- HEAD `b11793bbb199855ed1ac83a83656fa2840122b2e` ("Fix semantic verifier fail-open path and strengthen
  round-6 regression tests"), equal to `origin/claude/insightflow-ai-build-2neph7`. The previously reported
  HEAD `a63cec1` is its parent; the reported uncommitted changes to `orchestrator.py` / `test_round6.py` had
  already been committed as `b11793b` (verified with `git show --stat`).
- Uncommitted at mission start: the Phase-2 coverage work of the preceding request (planner, relational,
  kpi_catalog, mention_coverage, spec, typecheck, orchestrator; new `backend/tests/test_coverage_phase2.py`).
  It was reviewed, kept and folded into Phase 1 of this mission (nothing reset).
- Baseline tests: at `b11793b` 495 passed / 0 failed / 3 warnings (run in the preceding request);
  with the uncommitted Phase-2 work 521 passed / 0 failed / 3 warnings (`cd backend && python -m pytest -q`).
- Seal check: `cd evaluation/v3 && sha256sum -c FINAL6_SEAL.txt` -> both files OK.

## Components
| area | location |
|---|---|
| backend pipeline | `backend/insightflow/orchestrator.py` (`Orchestrator.ask`, steps 0-12b) |
| planner -> IR -> compiler | `backend/insightflow/plan/{planner,plan,compiler,validator,fidelity}.py` |
| schema discovery / FK inference | `backend/insightflow/knowledge/{relational,rel_context,dataset_registry,kpi_catalog,abbrev}.py` |
| SQL safety | `backend/insightflow/sql/` validator, read-only executor, cost pre-flight (orchestrator 5b-5d) |
| confidence + decision | `backend/insightflow/reliability/{confidence,decision}.py` (9 weighted signals, thresholds 0.70 / 0.40) |
| post-hoc vetoes | `reliability/mention_coverage.py`, `verification/intent_audit.py`, `verification/answer_verifier.py` |
| semantic layer | `backend/insightflow/semantics/{spec,typecheck,preserve,verify}.py` (step 12b) |
| tests | `backend/tests/` (61 files) |
| evaluation | `evaluation/v2` (historical, pinned `3c843de`), `evaluation/v3` (sealed sets FINAL, FINAL4, FINAL5, FINAL6 + dev sets) |
| sealed artifacts | `evaluation/v3/results/final6_K1_first_and_only.*`, `final6_K3_posthoc_not_heldout.*`, earlier `*_first_and_only.*` |
| paper evidence | `paper_evidence/` (pinned to `3c843de`), `docs/` round reports |

## Manuscript
No manuscript source or PDF exists in the repository or its git history (`git log --all --name-only`
shows no .tex/.bib/.docx/.pdf). This was already recorded in `docs/verification/PHASE_11_PAPER_REVIEW.md`
and `paper_evidence/discrepancies.md` D1 (expected `paper/InsightFlow_AI_IEEE_Paper.docx`).
No LaTeX toolchain is installed (`pdflatex`, `latexmk`, `tectonic` absent). See Phase 10 for the
consequence.

## Environment
Python 3.11.17, SQLite 3.45.1, matplotlib 3.11.2, numpy 2.5.3, pydantic 2.13.5, pytest 9.1.1, mcp 2.3.0.
No GPU; no local LLM weights; outbound network via a proxy.
