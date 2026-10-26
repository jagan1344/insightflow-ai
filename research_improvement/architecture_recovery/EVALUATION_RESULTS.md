# Evaluation results

All numbers come from committed raw files, scored with the same row-matching rule as every earlier set
(`evaluation/v3/run_eval.score`). "Wrong" means an answer that was given and does not match the reference, or an
answer to an item that should have been clarified or refused. Abstaining on an answerable item is counted as not
correct, never as wrong.

## Provenance at a glance

| Set | Author | Seen during development? | Role |
|---|---|---|---|
| dev questions (107) | engine developer | yes, used to fix the engine | capability on development data |
| held-out check (63) | engine developer, written after tuning | committed before run 1 (26d4aa1), raw run committed before scoring (d6b7559); fixed afterwards | first run = held-out; later runs = post-hoc |
| **v7 provisional (75)** | engine developer, written after the freeze | **no**: sealed (dba1d66), run once (0c81a7a), scored (2a0ca20) | the cleanest evidence here; still same-author, **not independent, not human-adjudicated** |
| Round 7 (v5, 105) | external author | revealed before this work began; two policy decisions were informed by it | diagnostic only, contaminated |
| Round 8 (v6, 106) | external author | revealed before this work began | diagnostic only |

## 1. v7 provisional (sealed, single first run, frozen backend tree 128cdf88)

Run through the full Orchestrator in all three modes on 75 items: 58 answerable, 10 to clarify or refuse, 7 "either".
Raw output is in `v7_provisional/v7_raw_first_run.json` (sha256 `47b641ec…`), and the score in `v7_scored.json` and
`v7_score_report.txt`.

| Mode | Answerable correct (95% CI) | Wrong, all kinds | Answered | Wrong among answered (95% CI) | Clarify/refuse items refused | Latency p50 / p95 |
|---|---|---|---|---|---|---|
| **typed (default)** | **38/58 = 65.5%** (52.7–76.4) | **1** | 40 | **2.5%** (0.4–12.9) | 10/10 | 7.6 / 24.0 ms |
| legacy (frozen da925ad pipeline) | 28/58 = 48.3% (35.9–60.8) | 6 | 35 | 17.1% (8.1–32.7) | 9/10 | 87.7 / 135.1 ms |
| typed+legacy | 44/58 = 75.9% (63.5–85.0) | 1 | 46 | 2.2% (0.4–11.3) | 10/10 | 22.1 / 123.1 ms |

Paired outcomes, legacy → typed, per item:
- correct → correct 21; abstain → correct 14; wrong → correct 3;
- wrong → abstain 1; wrong → refused-correctly 1; unanswerable-answered → refused 1;
- correct → abstain 7; correct → refused-correctly 1;
- abstain → wrong 1 (BA25); abstain → abstain 11; refused → refused 13; refused → correct 1.

**The typed engine's one wrong (BA25).** In "Batches without any complaint for pastry recipes", the negation was
applied both to the complaint and to the category. This is a general scoping bug and was fixed after the run
(commit 8fe5cfd). Post-hoc, BA25 is correct, but the first-run numbers above are the ones that count.

**Why typed abstained on 19 answerable items** (recorded, not tuned on):
- 9 are words absent from the schema: cars, written, carried ×2, fuel (column `fuel_litres`), kg, degrees,
  New Jersey (stored as NJ), recipe/category nouns via a lookup.
- 3 are "departure"/"arriving" not linked to `dep_`/`arr_` role prefixes (the global abbreviation list maps `dep`
  to "deposit").
- 2 are verbs naming a nullable date or id column ("never actually departed", "not checked").
- 1 is `oven_temp_c`: the unit suffix `c` is required.
- 1 is "How many fines over 100": `fine_amt` is money, so a count vs sum question.
- 1 is "unpaid" (no `paid` flag, only `paid_dt`).
- 1 is "mixed by each baker" (the role verb is in the column name, not in the table).
- 1 is "Ticket revenue by departure island".

**The hybrid mode.** It adds 6 correct answers on v7 at no extra wrong answers. On the dev set it added 3 wrong
answers. The default was fixed as *typed* before v7 was run and is not changed on the strength of v7. The hybrid is
available as `INSIGHTFLOW_ENGINE=typed+legacy`.

## 2. Controlled comparison on development and held-out questions (`compare_modes.py`, `comparison_raw.json`)

The same questions, databases, scorer and Orchestrator were used for all three modes; only `INSIGHTFLOW_ENGINE`
differs. Legacy mode is the frozen pipeline: the backend at c4c6087 is byte-identical to da925ad, and the typed hook
is bypassed.

| Split | Mode | Answerable correct | Wrong (answerable / unanswerable answered / either) | Latency p50 / p95 |
|---|---|---|---|---|
| dev (tuning data) | legacy | 42/82 | 4 / 3 / 1 | 160 / 239 ms |
| dev (tuning data) | typed | **77/82** | **0 / 0 / 0** | 31 / 45 ms |
| dev (tuning data) | typed+legacy | 77/82 | 1 / 2 / 0 | 7 / 161 ms |
| held-out, post-hoc | legacy | 26/53 | 4 / 1 / 0 | 186 / 290 ms |
| held-out, post-hoc | typed | **44/53** | **0 / 0 / 0** | 42 / 59 ms |
| held-out, post-hoc | typed+legacy | 46/53 | 0 / 0 / 0 | 9 / 200 ms |

Paired legacy → typed:
- **dev:** correct→correct 42, abstain→correct 32, wrong→correct 3, wrong→refused 1, unanswerable-answered→refused 3,
  wrong→abstain 1, correct→refused 1.
- **held-out:** correct→correct 25, abstain→correct 16, wrong→correct 4, unanswerable-answered→refused 1,
  correct→abstain 2.

The latency order effect is visible: within each question the modes run legacy, then typed, then hybrid, so the
first mode pays the cold caches. The engine's own planning plus execution is about 1 ms (see `run_dev.py`).

## 3. Held-out check: first run and post-hoc

| Run | Answerable correct | Wrong | Status |
|---|---|---|---|
| run 1 (engine at 26d4aa1) | 32/53 | 3 (no_show read as "number"; group target reused as count target; agentive "by" read as grouping) | held-out |
| after fixing those general causes | 47/53 | 0 | post-hoc |
| after withdrawing the default-date rule (more clarifications) | 44/53 | 0 | post-hoc, current |

## 4. Development questions (`devsets/run_dev.py`)

| Engine state | Answerable correct (abbr / full naming) | Wrong |
|---|---|---|
| first run of the new engine (`dev_run_initial.json`) | 32 / 35 of 87 | 6 / 6 |
| current (`dev_run_tuned.json`) | 77 / 75 of 82 (5 items relabelled "either", see GROUNDING_DESIGN.md) | 0 / 0 |

Metamorphic agreement between the abbreviated and spelled-out schemas is 105/107. The two differences are
questions that use "csat", a word that exists only in the abbreviated names.

## 5. Round 7 / Round 8 diagnostics (`diag_r7r8.py`, `diag/`)

These sets were revealed before this work. The engine was **not** tuned on them. Two policy decisions were informed
by R7, which therefore counts as contaminated:
- the default-date rule was withdrawn;
- verb-asserted links were extended to single paths.

R8 exposed two engine bugs, a crash and a comparison/series conflict, which were fixed.

| Set | Engine | Correct | Wrong answers | Clarify items refused | Unnecessary clarifications |
|---|---|---|---|---|---|
| R7 (v5) | frozen legacy, first run (`v5_A0_first_run.json`) | 14/74 | 7 (3 answerable + 4 clarify items answered) | 27/31 | 57 |
| R7 (v5) | typed engine, current | 29/74 | **0** | 31/31 | 45 |
| R8 (v6) | frozen legacy, blind first run (`v6_A0_first_run.json`) | 5/73 | 10 (6 + 4) | 29/33 | 62 |
| R8 (v6) | typed engine, current | 12/73 | **0** | 33/33 | 61 |

Coverage on R8 is low (16%). Most abstentions are "words not grounded": domain synonyms the schema does not contain.
These are reported as a limitation and were not added by hand.

## 6. Test suite

| Configuration | Result |
|---|---|
| default (`pytest`): engine tests on the typed engine, the 28 pre-existing legacy-spec modules pinned to `legacy` by `tests/conftest.py` | **642 passed** at the final commit (641 at the freeze) |
| legacy specs run against the typed engine (`INSIGHTFLOW_TEST_ENGINE=typed`) | 83 failed / 641 |
| legacy specs run against typed+legacy (`INSIGHTFLOW_TEST_ENGINE=typed+legacy`) | 42 failed / 641 |

The typed-mode failures on the legacy specs were classified at commit 9b4b90b, when 85 failed:
- about 52 are abstentions (clarifications where the legacy pipeline answered: domain synonyms, KPI catalog
  terms such as "revenue"/"profit", relative phrasing);
- about 32 assert legacy-specific wording, formats or internals:
  - "Which did you mean" / "maps to this data" / "included and excluded" texts;
  - shares as fractions rather than percentages;
  - `semantic_spec` diagnostics;
  - a monkeypatched legacy verifier;
  - `dataset_` table prefixes in SQL;
- 1 asserted a legacy safeguard path.

Running the legacy specs in typed mode found **eight families of silent wrong answers in the typed engine**:
- year-like numbers;
- yearless months ("may");
- entity counts;
- per-row totals;
- capitalised participles inside names;
- verb/value clashes;
- "report to";
- lookup attributes summed in ratios.

All were fixed generally, before the v7 freeze, with regression tests in `tests/test_engine.py`.

## 7. Latency

- Engine alone (schema model cached): planning plus execution is about 1 ms median on the dev schemas.
- Through the Orchestrator: typed p50 is 8–42 ms depending on cache state, against 88–186 ms for legacy.
- No LLM is called by either path in this configuration (offline provider), so the cost is compute only.
