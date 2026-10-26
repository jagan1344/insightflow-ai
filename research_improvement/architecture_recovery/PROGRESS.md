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

- [x] Legacy specs run in typed mode: eight silent-wrong families found and fixed; conftest pins legacy specs.
- [x] Freeze 4e9c5e8 (backend tree 128cdf88); v7 provisional sealed dba1d66; run once 0c81a7a; scored 2a0ca20.
      typed 38/58 correct, 1 wrong; legacy 28/58, 6 wrong; typed+legacy 44/58, 1 wrong.
- [x] Post-v7 general bug fix (negation scope, BA25) 8fe5cfd, labelled post-hoc.
- [x] EVALUATION_RESULTS.md, FINAL_REPORT.md.

## Possible next steps (not started)
- A set written by someone who has not seen the engine.
- Coverage gaps recorded from v7: role prefixes (dep_/arr_), unit suffixes (_c), the global 'dep' abbreviation,
  verbs on nullable dates or ids.
