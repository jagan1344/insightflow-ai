# Generalization tests

All sets here were written by the same developer who wrote the engine. None of them is independent evidence; their
role is development and regression. The only externally-authored items available are the revealed Round 7 / Round 8
sets, and they are used as diagnostics only (EVALUATION_RESULTS.md).

## 1. Development schemas (`devsets/dev_schemas.py`)

Four domains used nowhere before: bike sharing, school exams, e-commerce orders, support tickets. They were built to
contain the failure causes found in the audit:

| Feature | Where |
|---|---|
| role-playing lookups (two FKs to one table) | rentals.start/end station (undeclared, abbreviated `stn`), tickets.opened_by/resolved_by agent (undeclared) |
| ids that hold another table's keys with no name evidence | exam_results.grader_id / proctor_id (must NOT be joined) |
| one-to-many children (fan-out risk) | rental_issues, accommodations (with duplicates), order_lines, returns, ticket_tags |
| flags of both polarities | helmet_used, gps_ok, paid_ok, sla_met, is_gift, is_retake, absent |
| NULLs with meaning | end station, rider, proctor, graded date, ship date, promo code, closed time, csat |
| several date columns | start/end, exam/graded, order/ship, opened/closed |
| derived expressions | duration × per-minute rate, earned / possible, gross − discount |
| abbreviations | dur_min, dist_km, fare_amt, crs_cd, stu_nm, pts_earned, csat, reopen_cnt, arr_usd |
| misleading words | "monthly" is a stored plan type; "rate" is a rate, not minutes; "no" in no_show |
| unsupported / ambiguous | revenue, loyalty, churn, relative dates, forecasts, station without role, agent without role |

**Metamorphic variant:** `scheme="full"` renames every abbreviated column to its spelled-out name over the same
data (e.g. `dur_min` → `duration_minutes`). The same question must give the same answer under both schemes, unless
the question uses a word that exists only in one naming ("csat").

## 2. Development questions (`devsets/dev_questions.py`, harness `devsets/run_dev.py`)

There are 107 items: 82 answerable, 15 that should be clarified or refused, and 10 marked "either" (abstaining is
fine; an answer must match the reference).
- Reference SQL was written by hand against the abbreviated scheme and translated to the full scheme by the rename
  map.
- Rows are matched with the same row-matching rule as every earlier sealed set (`evaluation/v3/run_eval.score`).

These questions were used to fix the engine, so their scores show what the engine can do on the data it was
developed against.

## 3. Held-out check (`devsets/heldout.py`, `run_heldout.py`)

There are 63 items:
- 44 on two schemas never used during development (library loans, clinic appointments);
- 19 new phrasings on the dev schemas.

They were written after tuning and committed before the first run (commit 26d4aa1, sha256 `ea6cbc08…`). The raw
output of that run was committed before scoring (commit d6b7559). Every later rerun is labelled post-hoc.

## 4. Unit and behaviour tests (`backend/tests/test_engine.py`, 35 tests)

| Area | Tests |
|---|---|
| Schema model | established vs inferred separated; FK by vowel-less abbreviation; **no** FK without name evidence; column kinds |
| Compiler safety | literals are parameters (an injection string is bound, never inlined); bad identifiers rejected; division NULLIF-guarded; one-to-many only inside EXISTS |
| Verifier | SUM of a category, fan-out column outside EXISTS, ordered comparison on a category: all rejected |
| Behaviour | 9 answers checked against reference SQL (negation, NOT EXISTS, product, verb-form conditions, roles) |
| Asking instead of guessing | 8 items (role ambiguity, date ambiguity, undefined metric, relative date, id without lookup, lookup-attribute weighting, value/operation clash) |
| Safety | dangling negation never answered; trace has evidence and the "not a calibrated probability" label; read-only connection |
| Metamorphic | 4 questions give identical rows under both naming schemes |

## 5. Earlier repository tests

The 597 tests that existed at the start of this work exercise the legacy pipeline on its development fixtures.
They are run in all three engine modes (EVALUATION_RESULTS.md, section "Test suite").
