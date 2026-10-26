# Architectural correction and generalization recovery: final report

Start commit **c4c6087**; its backend is identical to the frozen da925ad. The v7 freeze commit is **4e9c5e8**,
with backend tree 128cdf88, sealed in **dba1d66**. Nothing was pushed.

## 1. What was wrong (ARCHITECTURE_AUDIT.md)

The legacy pipeline's failures on unfamiliar schemas came from the **planner**, not from the safeguards behind it.
On Round 8, planner SQL was correct for 9 of 73 answerable questions; 40 were wrong and 24 had no SQL.

The confirmed causes, each demonstrated on a specific item:
- keyword-triggered intents;
- partial-token column matching;
- spurious inferred foreign keys;
- values confused with words;
- role phrases not grounded;
- negation and NULL phrasing;
- no expression structure;
- abbreviations;
- falling back to a row count;
- development overfitting;
- a confidence score with no discrimination (blind AUROC 0.45).

## 2. What replaced it

A new package, `backend/insightflow/engine` (≈2,400 lines). It is used by the Orchestrator for every non-demo
dataset.

```
question ──► Grounder ──► typed Query (IR) ──► verify ──► Compiler ──► read-only SQLite ──► answer + evidence
               │  schema model (established vs inferred), lexicon (schema-derived words, values, roles)
               └─ every content word accounted for; ambiguities kept as structured readings
```

| Component | File | Doc |
|---|---|---|
| Schema semantic model: kinds, units, strict FK inference, paths with roles and fan-out flags | `schema_model.py` | SEMANTIC_MODEL.md |
| Lexicon: schema-derived abbreviations, core words, role words, stored values | `lexicon.py`, `words.py` | SEMANTIC_MODEL.md |
| Typed IR: Col, Lit, Agg (conditional), Arith, Cmp, InSet, IsNull, Exists, BoolOp, Not; Query with evidence | `ir.py` | TYPED_QUERY_PLAN.md |
| Grounding with full accounting, negation safety, role/date/value readings | `grounding.py` | GROUNDING_DESIGN.md |
| Plan verification before SQL | `verify.py` | TYPED_QUERY_PLAN.md |
| Compiler: parameters, identifier checks, LEFT JOIN for many-to-one, EXISTS for one-to-many, NULLIF, window shares | `compiler.py` | SQL_COMPILER_DESIGN.md |
| Execution (read-only URI, timeout, row cap); reading evaluation (answer when every reading agrees, otherwise ask with each value) | `engine.py` | SQL_COMPILER_DESIGN.md |
| Orchestrator integration; decision by hard rules; reliability components labelled uncalibrated | `orchestrator.py` (`_typed_engine_response`), `config.py` (`engine_mode`) | SQL_COMPILER_DESIGN.md |

**Modes** (`INSIGHTFLOW_ENGINE`):
- `typed` (default): the typed engine answers or asks.
- `typed+legacy`: the legacy planner is tried only when the typed engine abstained purely over vocabulary, never on
  an ambiguity, an unsupported construct or a failed verification.
- `legacy`: the frozen pipeline.

**Decision.**
- CLARIFY when anything is unsupported, ambiguous, unresolved or fails verification; the message is specific.
- WARN when the answer rests on stated assumptions.
- ANSWER otherwise.

There are no tuned thresholds. The reliability components are reported separately: grounding completeness,
ambiguities, unresolved items, plan violations, executed, empty result, assumptions and inferred joins.
`Confidence.score` is a coarse ordinal level kept for API compatibility. It is explicitly *not* a calibrated
probability.

## 3. Results (details in EVALUATION_RESULTS.md)

**Cleanest evidence: v7 provisional.** Three new domains, sealed before the run, run once, raw output committed
before scoring. It was written by the same developer, so it is **not independent and not human-adjudicated**.

| | typed (default) | legacy (frozen) | typed+legacy |
|---|---|---|---|
| answerable correct | **38/58 (65.5%)** | 28/58 (48.3%) | 44/58 (75.9%) |
| wrong answers (all kinds) | **1** | 6 | 1 |
| wrong among answered | **2.5%** | 17.1% | 2.2% |
| clarify/refuse items refused | 10/10 | 9/10 | 10/10 |
| latency p50 | 7.6 ms | 87.7 ms | 22.1 ms |

**Development and held-out** (same author; held-out numbers are post-hoc after its first run):
- dev: typed 77/82 with 0 wrong, against legacy 42/82 with 8 wrong;
- held-out: typed 44/53 with 0 wrong, against legacy 26/53 with 5 wrong;
- held-out first run before fixes: 32/53 with 3 wrong.

**Revealed external sets (diagnostic only; R7 contaminated by two policy decisions):**
- R7: 29/74 correct, 0 wrong, 31/31 clarify items refused (legacy first run: 14/74, 7 wrong).
- R8: 12/73 correct, 0 wrong, 33/33 refused (legacy blind run: 5/73, 10 wrong).

**Main remaining weakness: coverage.**
- Where users use words the schema does not contain, the engine asks rather than guesses. This is most of the 19
  abstentions on v7 and most of R8.
- Concrete gaps found by v7 (not fixed, because v7 is revealed):
  - role prefixes (`dep_`/`arr_`) against "departure"/"arriving";
  - unit suffixes such as `_c`;
  - verbs on nullable date or id columns without a date-like name;
  - a global abbreviation entry (`dep` → deposit) that misfires.

## 4. What the engine does not do (it refuses or asks; never approximates)

- Date arithmetic and durations; relative dates.
- Medians and percentiles; top-N per group; HAVING thresholds; nested aggregates.
- Anti-joins from a lookup's side; measures at child grain mixed with base grain.
- Totals or averages of lookup attributes over base rows (weighting).
- Counting a related entity without words that tie it to the base rows.
- Months without a year.
- Words not present in the schema or its values (no synonym dictionary).
- Forecasting.

## 5. Tests

- `backend/tests/test_engine.py` has 45 tests:
  - schema model;
  - compiler safety (parameters, identifiers, NULLIF, EXISTS);
  - verifier;
  - answers against reference SQL;
  - asking instead of guessing;
  - negation and dropped-word families;
  - readings;
  - metamorphic renaming;
  - read-only access.
- Default `pytest`: 642 passed at the final commit (641 at the freeze). The 28 pre-existing modules are specifications of the legacy pipeline and are pinned
  to `legacy` by `tests/conftest.py`. Against the typed engine they give 83 failures (`INSIGHTFLOW_TEST_ENGINE=typed`),
  classified in EVALUATION_RESULTS.md §6. Running them that way exposed eight silent-wrong families in the typed
  engine, all fixed before the freeze.

## 6. Reproducing

From `backend/`, with `PYTHONPATH=.` set for every command:

| What | Command |
|---|---|
| test suite | `python -m pytest -q`, then `git checkout -- evaluation/v2` (a legacy test rewrites that file) |
| dev set, both namings | `python ../research_improvement/architecture_recovery/devsets/run_dev.py out.json` |
| held-out | `python …/devsets/run_heldout.py run raw.json`, then `… score raw.json` |
| old vs new comparison | `python ../research_improvement/architecture_recovery/compare_modes.py out.json` |
| R7/R8 diagnostic | `python ../research_improvement/architecture_recovery/diag_r7r8.py outdir` |
| v7 scoring | `python ../research_improvement/architecture_recovery/v7_provisional/score_v7.py` |

The v7 runner refuses to run again: the output exists, and the backend tree differs from the manifest after the
post-run bug fix.

All databases are generated deterministically from seeds; generated `.db` files are not committed.

## 7. Integrity notes

- No sealed set, first-run output, `evaluation/v2` result, `paper_evidence` file or manuscript was modified.
  `evaluation/v2/heldout_e2e_results.json` is rewritten by a legacy test on every suite run and was restored each
  time.
- One post-run engine change was made: the negation-scope bug found by v7 item BA25 (8fe5cfd). It is labelled
  post-hoc, and the v7 numbers above are from the frozen engine.
- Every evaluation set in this work is same-author. The next step that would add real evidence is a set written by
  someone who has not seen the engine.
