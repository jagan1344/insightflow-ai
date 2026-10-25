# v5 provisional evaluation — protocol (written and committed before the first run)

- Question source: `evaluation/v5_provisional/` — 105 questions over 4 new synthetic schemas (hotel, insurance,
  energy, rides), authored by a separate agent process instructed not to read the backend, prior question
  sets, docs or results. It is the same model family as the developer agent, and nobody human-adjudicated the set.
  So it is **agent-generated provisional evidence, not independent held-out evidence**.
- Reference answers: sqlite3 execution of `reference_sql`; every answerable item also agrees with an
  independently written `alt_sql` (author's `validate_v5.py`, re-run by the developer: ALL CHECKS PASSED).
- Labels were not reviewed against system output; none will be changed after the run. Borderline items
  named by the author are listed in `score_v5.py::BORDERLINE_IDS` and reported only as a sensitivity analysis.
- Frozen implementation: commit `38b60d1`, backend tree `00db6e2` (`run_v5.py` refuses any other tree).
- First run: `python run_v5.py A0 first_run` exactly once; raw JSON saved before scoring
  (`score_v5.py` writes a separate `.summary.json`). Ablations A1-A7 use the same frozen tree, data and scorer.
- Scoring (fixed before the run): scalar within 1e-6 relative; rowset = same label set and values (extra
  zero/NULL rows tolerated); ordered = same order; empty_ok = no rows / NULL / 0; clarify items: CLARIFY or
  ABSTAIN is correct, any ANSWER/WARN is a wrong answer; percentage items (`PERCENT_IDS`) accept x, x*100, x/100.
- Hashes: `V5_MANIFEST.sha256`.
