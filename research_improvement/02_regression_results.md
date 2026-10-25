# 02 — Regression results (pre-freeze)

All commands run from the repository root unless stated. All runs on 2026-10-25.

| command | result |
|---|---|
| `cd backend && python -m pytest -q tests/test_coverage_phase2.py` | 31 passed |
| `cd backend && python -m pytest -q tests/test_coverage_phase2.py tests/test_round6.py tests/test_semantic_layer.py` | 84 passed (before the last 5 tests were added) |
| `cd backend && python -m pytest -q` | **523 passed, 0 failed, 3 warnings** (warnings: FastAPI `on_event` deprecation, pre-existing); 5 more tests were added afterwards, see `PROGRESS.md` for the final count |
| `cd evaluation/v2 && python exec_accuracy_bench.py` | action 27/27, exec 27/27 |
| `cd evaluation/v2 && python exec_accuracy_advanced.py` | exec 25/25 |
| `cd evaluation/v2 && python heldout_e2e.py` | 23/23 answerable correct (prints "23/28") |
| `git checkout -- evaluation/v2` | historical result files restored (these scripts rewrite them) |

Earlier evaluation sets, re-run under the new label `P1` (new files, nothing overwritten). All of these
sets were used for tuning in earlier rounds, so they are regression monitors, not generalization evidence.

| set | correct / answerable | silent wrong / n | correct clarifications |
|---|---|---|---|
| adversarial (`run_adv.py P1`) | 15/15 | 0/20 | 5/5 |
| dev4 (`run_v4.py dev4 P1`) | 45/46 | 0/59 | 13/13 |
| final4 (`run_f.py final4 P1`) | 25/27 | 1/38 (F17, disputed label) | 10/11 |
| final / schema C (`run_final.py P1`) | 24/24 | 1/32 (C25, outdated label) | 7/8 |
| final5 (`run_f.py final5 P1`) | 44/47 | 0/57 | 10/10 |
| final6 (`run_r6.py final6 P1_posthoc_not_heldout`) | 54/54 | 0/66 | 12/12 |

The final6 figure is post-hoc and tuned on exactly these questions; the sealed first run remains
K1 = 42/54 (`evaluation/v3/results/final6_K1_first_and_only.json`, unchanged).

Development probe (`dev_probe/run_probe.py`, 33 questions): 20 correct, 12 safe rejections, 1 unnecessary
clarification (trend with "by issue date"), 0 wrong answers.

Test coverage added (`backend/tests/test_coverage_phase2.py`, 36 tests): related numeric thresholds
(4 positive + inclusive 2 + unknown comparative + plan-consumption unit test), polarity flags
(4 positive, never-ok-rows negative, negation / noun-alone), abbreviation (3 positive, measure-noun
count negative, row count positive), average per base row (3 positive, other-entity negative),
role-playing inferred FK (2 positive with full rowset comparison, role not guessed, inference rule
unit test with 3 negatives), value-qualified fan-out semi-join (vs double-counting join), ablation
switches (default-off, switch effect). Every answer test compares the value with an independent
sqlite3 query, so a wrong ANSWER/WARN fails.
