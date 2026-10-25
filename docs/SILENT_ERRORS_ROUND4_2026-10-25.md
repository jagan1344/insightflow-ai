# Silent-wrong-answer elimination - round 4 (2026-10-25)

Starting point `e5394ba` (clean, equal to origin). The original Schema-C first run
(`evaluation/v3/results/final_F1_first_and_only.json`) was reproduced exactly (32/32 questions: same action, SQL and
value) by running the committed question set at commit `c503182` in a throw-away git worktree. The original JSON is
untouched; every later run on that set is tuned and labelled so.

## 1. Root cause of each Schema-C first-run error (reproduced at c503182)
Artifact gap: the committed F1 JSON stores question, SQL, value, confidence and action only - not schema, parameters,
safeguard notes or signals. Those were regenerated at c503182 and saved as a NEW file,
`evaluation/v3/results/diagnosis_F1_silent_errors_reproduced_at_c503182.json`; the old record was not edited.

| id | question | system returned | reference answer | root cause | why existing checks passed |
|---|---|---|---|---|---|
| C05 | Total tuition paid by students from California | 7 rows, one per student | 51248.51 (single figure) | "by students from X" parsed as GROUP BY student; the groups do add up to 51248.51 | breakdown reconciliation proves additivity, not grain; plan fidelity compares plan with SQL and both came from the same reading |
| C24 | ... by students from Texas and Ohio | 36 rows | 399643.45 | same | same |
| C29 | ... completed in 2031 | 698600.43 | NULL (no rows) | a bare year was not a time filter, so the constraint was dropped | no signal compared the question's year with the SQL |

Abstentions on the same run: C09 (three equal-length join paths), C21/C22 (measure / numeric filter on a related
table), C27 (comma inside "O'Neil, Sam" split the question as a compound). A later run also exposed a regression
(C07: digits in "1800-1900" read as a year). Each class has a regression test in `test_semantic_audit.py` and
`test_reliability_features.py::TestPostHocFixes`.

## 2. Why the confidence score cannot catch these
`score_confidence` is a weighted blend of SQL validity, schema match, KPI match, result consistency, data completeness,
evidence strength, intent coverage and plan fidelity, capped at `min(coverage, fidelity)+0.05`. Every input measures
execution validity or plan-to-SQL agreement; none compares the user's wording with the data. It is not a probability of
correctness and no calibration was ever established. Pooled over the five first runs: 93 answers scored >= 0.9, of which
75 were correct and 18 silently wrong (19%). Mean score of correct answers 0.975-0.979, of wrong answers 0.979-0.993.
The score was left numerically unchanged. Protection comes from vetoes (cap 0.30, CLARIFY) and from WARN for answers that
rest on a stated assumption; nothing was lowered across the board.

## 3. Verification and fixes added (heuristic, English only, none a proof)
- `verification/intent_audit.py`: aggregation cue, unrequested grouping for "Total X"-shaped questions, measure never
  named, an added count, month named but not applied.
- `reliability/mention_coverage.py`: dimension values, table nouns (base-table noun and plain many-to-one parent mentions
  exempt), column phrases, qualifier words tied to unused columns, years, numeric literals.
- Planner: year bounds (after / since / before / until / between), exclusions as NOT IN / NOT EXISTS with NULLs kept,
  contradictory include+exclude, anti-join and self-reference refusal, "average per X" asked, month-without-year taken
  from the data (asked when it spans several years), related-table measures, numeric filters and date columns, top-N
  never ranks the NULL group.
- Relationship inference: head-noun name evidence plus a reverse-FK check (a false `orders.order_id -> order_lines.line_id`
  edge was found on the retail schema); declared keys outrank coincidentally unique columns; only flat uploads count as
  foreign tables (the demo registry row used to hide a user table called `orders`).
- Adaptive clarification covers alternative join routes of different length: every route is executed, identical
  results are answered without asking, different results are asked with each value shown.
- Caveats (WARN, not abstention): a related-table measure counted once per base row; an undeclared FK actually used.

## 4. Results (exact numerators / denominators; `evaluation/v3/results/SUMMARY_round4.md` is generated from the JSON)
| set | status | correct/answerable | answered/answerable | silent wrong | correct clarifications |
|---|---|---|---|---|---|
| Schema C (university) F1 | first run, sealed in `6a25cb4` | 17/24 | 20/24 | 3/32 | 8/8 |
| Schema F (library) G1 | first run; sealed in `c9c89bb` before the run; code frozen at `36878e7` | 18/27 | 20/27 | 5/38 | 8/11 |

Tuned runs on the same sets (NOT held out): C 24/24 correct, 1/32 flagged (C25); F 25/27 correct, 1/38 flagged (F17).
Development sets (tuned on): dev4 (schemas D, E) 32/46 -> 45/46 correct, silent wrong 2/59 -> 0/59; adversarial
10/15 -> 15/15. Remaining abstentions on answerable questions in the tuned runs: C 0/24, F 2/27, dev4 1/46, dev 1/25,
adversarial 0/15. Latency p50/p95 in the tuned runs: 11-14 ms / 45-73 ms. Regression: full suite 400 passed, 0 failed
(335 before this task); historical benchmarks 27/27, 25/25 and held-out 23/23 answerable unchanged.

## 5. Silent-wrong labels that remain, and why
- G1 first run, 5 silent: F08 and F09 (a branch reachable through the loan or the member's home branch; the system took
  the shorter route without saying so - fixed afterwards by executing both routes), F24 (ranked the NULL-genre group as a
  genre), F32 ("returned late": qualifier dropped, COUNT of all loans), F17 (below). F08, F09, F24, F32 are real errors.
- F17 "How many distinct books were borrowed in 2025?" is answered 9 under every date column; the adaptive-clarification
  policy is to answer when all readings agree, so the sealed label (CLARIFY) contradicts the stated design. It is left
  unedited and still counted as an error in the tuned figures.
- C25 "excluding California students" is now answered with 647351.92, which matches the reference; its sealed label
  predates exclusion support (expected CLARIFY), so the tuned run counts it as an error.
- Found by probing outside the sets: "Average tuition paid per student" returned 65 per-student rows (now asked).
- Unprobed classes certainly remain; 400 tests and five small developer-authored sets cannot show their absence.

## 6. Unsupported query classes and limitations
These abstain rather than answer: wording that differs from the column ("published after 2000" for `pub_year`),
comparison between two columns ("returned late" now clarifies), anti-joins, hierarchies, many-to-many group-by,
period-over-period with dimensions, share-of-total over joins, non-ISO date formats, relational mode for non-SQLite
databases or tables not registered with `register_relational`, and any language but English. The wording audit,
qualifier-word and proper-noun heuristics can over-trigger on unusual phrasing and miss errors. All evaluation sets are
small and written by the developer; first-run numbers (17/24 and 18/27) are the generalization evidence, not the tuned ones.

## 7. Reproduce
    cd backend && python -m pytest -q                      # 400 passed
    python -c "import sys;sys.path.insert(0,'.');from insightflow.knowledge.dataset_registry import set_active,DEMO_ID;set_active(DEMO_ID)"
    cd .. && python evaluation/v2/exec_accuracy_bench.py && python evaluation/v2/exec_accuracy_advanced.py && python evaluation/v2/heldout_e2e.py
    git checkout -- evaluation/v2                           # these scripts rewrite their historical result files
    cd evaluation/v3 && sha256sum -c FINAL_SEAL.txt && sha256sum -c FINAL4_SEAL.txt
    python run_final.py <label>        # schema C; compare with results/final_F1_first_and_only.json (first run needs code at c503182)
    python run_f.py final4 <label>     # schema F; compare with results/final4_G1_first_and_only.json (first run needs code at 36878e7)
    python run_v4.py dev4 <label>      # schemas D, E
    python run_adv.py <label>; python baseline_current.py <label>
    python calibration_report.py > results/SUMMARY_round4.md
    # exact F1 reproduction: git worktree add /tmp/wt c503182; copy final_questions.py fixtures.py run_eval.py baseline_current.py into it; run run_final.py
