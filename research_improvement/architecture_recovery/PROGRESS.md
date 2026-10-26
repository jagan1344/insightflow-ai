# Architecture recovery — progress ledger

Start commit: c4c6087 (backend identical to frozen da925ad). Never push. Never edit sealed sets, first-run
outputs, `evaluation/v2` results (restore with `git checkout -- evaluation/v2` after any suite run), `paper_evidence`,
or the original manuscript.

## Done
- [x] Phase 1 audit: ARCHITECTURE_AUDIT.md, stage_split.py.
- [x] Engine `backend/insightflow/engine`: schema_model, words, lexicon, ir, grounding, verify, compiler, engine.
- [x] Dev schemas and 107 dev questions (`devsets/`), harness `run_dev.py`; abbr and full naming schemes (metamorphic).
- [x] Held-out check (63 items): committed 26d4aa1 before the run; raw run 1 committed d6b7559 before scoring.
      Run 1: 32/53 answerable correct, 3 wrong. Post-hoc (after fixes): 44/53, 0 wrong.
- [x] R7/R8 diagnostic (`diag_r7r8.py`, `diag/`). R7 is contaminated by two policy decisions (date default
      withdrawn, verb-asserted links); disclosed.
- [x] Integration: `Orchestrator._typed_engine_response`; `INSIGHTFLOW_ENGINE` = typed (default) | typed+legacy
      (falls back only on vocabulary-only abstentions) | legacy.
- [x] Engine unit tests `backend/tests/test_engine.py` (37).
- [x] Controlled comparison `compare_modes.py` → `comparison_raw.json`.
- [x] Readings of structured ambiguities (answer when they agree, ask with each value otherwise).
- [x] Docs: SEMANTIC_MODEL, TYPED_QUERY_PLAN, GROUNDING_DESIGN, SQL_COMPILER_DESIGN, GENERALIZATION_TESTS.

## In progress / next
- [ ] Classify the existing-suite failures in typed mode; fix general gaps; decide test policy for legacy specs.
- [ ] Re-run the comparison after the readings feature.
- [ ] Freeze; write a new provisional sealed set (new schemas) before running; run once; raw output before scoring.
- [ ] EVALUATION_RESULTS.md, FINAL_REPORT.md, final summary.
