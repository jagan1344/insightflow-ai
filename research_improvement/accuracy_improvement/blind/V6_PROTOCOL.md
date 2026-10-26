# v6 blind evaluation — protocol (committed before the first run)

- Questions: `evaluation/v6_blind/` — 106 questions over 4 new synthetic schemas (food delivery, property leases,
  telecom billing, warehouse moves), written by a separate AI agent process instructed not to read the
  implementation, documentation, results, the paper or any earlier question set (including the revealed v5 set).
  Isolation was self-reported, not independently verified. The authoring agent is of the same model family as the
  development agent. No human adjudicated the labels. => PROVISIONAL BLIND evidence, not independent human validation.
- References: reference_sql and an independently written alt_sql agree for all 73 answerable items
  (author's `validate_v6.py`, re-run by the developer: ALL CHECKS PASSED; rebuild byte-identical).
- Frozen implementation: commit `da925ad`, backend tree `d760e82` (`run_v6.py` refuses any other tree).
- First run: `python run_v6.py A0 first_run` exactly once; raw JSON committed before scoring; no label, reference
  or scoring rule changed afterwards; no implementation change will be evaluated on this set as held-out evidence.
- Scoring: `score_v6.py` = the v5 rules (scalar 1e-6 relative; rowset same labels/values, extra zero/NULL rows
  tolerated; ordered in order; empty_ok NULL/0/no rows; clarify/unsupported: any answer is wrong), percentage
  items FD16, LS16, TC15, WH17 accept x, x*100, x/100; the author's 24 borderline ids are reported only as a
  sensitivity analysis.
- Ablations A1-A7 and B1-B6 use the same tree, data and scorer.
