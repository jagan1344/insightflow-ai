# Multi-table generalization and reliability layer - 2026-10-25

Historical files (`paper_evidence/`, `evaluation/v2/*` results, `docs/HELDOUT_EVAL_2026-10-25.md`)
are unchanged. New artifacts: `evaluation/v3/` (fixtures, question sets, `results/`, `FINAL_SEAL.txt`).
All counts are raw numerators/denominators on SMALL sets of 20-32 questions; none is a claim of
general correctness. Every expected value is plain sqlite3 SQL written from the fixture schema.

## Evaluation protocol
| set | schema(s) | n | role | authored |
|---|---|---|---|---|
| dev | A clinic, B logistics | 32 | used while building | before code changes |
| adversarial | A, B | 20 | used while building | before looking at its output |
| FINAL | C university (never used for any design decision) | 32 | held out | after code freeze `c503182`; sealed in `6a25cb4` before first run |

Scoring: *answerable* = reference SQL exists; *correct* = answered and equal to reference;
*silent wrong* = answered but wrong, or answered when only a clarification is right;
*abstained* = answerable but CLARIFY/ABSTAIN (coverage loss, not an error).

## Results
| run | answerable correct | answered/answerable | silent wrong | abstained | correct clarifications |
|---|---|---|---|---|---|
| dev, before this work (fact table only, `M0_baseline`) | 2/25 | 4/25 | 4/31 | 21 | 4/6 |
| dev, after (`M3_integrated`) | 24/25 | 24/25 | 0/32 | 1 | 7/7 |
| adversarial, first run (`A0_first`) | 10/15 | 13/15 | 4/20 | 2 | 4/5 |
| adversarial, after generic fixes (`A5`) | 15/15 | 15/15 | 0/20 | 0 | 5/5 |
| **FINAL, first and only held-out run (`F1`)** | **17/24** | **20/24** | **3/32** | **4** | **8/8** |
| FINAL after post-hoc fixes (`F2`, NO LONGER HELD OUT) | 22/24 | 22/24 | 0/32 | 2 | 8/8 |

M0 ran on the 31-question version of the dev set; A15 was then reclassified from scalar to clarify and A17 added (32 questions) because two date columns make "in June 2025" ambiguous - a change made after seeing M0, so M0 and M3 differ by that one question.
Dev and adversarial improvements were obtained while tuning on those sets and must not be read as
generalization. **F1 is the only honest generalization number: 17/24 correct, 3 silent wrong (all at confidence >= 0.98).**

Per-family F1 (correct incl. correct clarification / total, from `final_F1_first_and_only.json`):
single 3/3, nulls 3/3, grouped 2/2, topn 3/3, distinct 1/1, time 1/1, zero_fact 1/1, ambiguous 3/3, unknown 2/2,
grain 1/1, negation 1/1, join_filter 1/2, unusual_value 2/3, fanout 1/2, multi_value 0/1, empty 0/1,
foreign_measure 0/1, numeric_filter 0/1.

### F1 failures and root causes (generic, none question-specific)
- C05, C24 (silent wrong; fanout family C09 abstained too): "paid **by** students **from** X" was parsed as GROUP BY student. Fixed: agent phrase is a filter.
- C29 (silent wrong): "in 2031" - a bare year was ignored, answering with the all-time total. Fixed: year filter + a
  question->SQL guard that vetoes any year the SQL never uses.
- C27 (abstained): the comma in "O'Neil, Sam" split the question as a compound. Fixed: commas inside known values are protected.
- C09 (abstained): instructors reachable by three equally short paths. Fixed: paths through a declared bridge table win.
- C07 regression introduced by the year fix ("1800-1900" read as a year) was caught by F2 and fixed (digits inside a known value are masked).
- C21, C22 (abstained, NOT fixed): measure or numeric filter living on a non-anchor table is unsupported.

### Confidence calibration (observed, not a probability)
| run | mean conf correct | mean conf wrong | wrong with conf >= 0.7 |
|---|---|---|---|
| dev M0 | 0.979 | 0.984 | 4/4 |
| adversarial A0 | 0.975 | 0.981 | 4/4 |
| FINAL F1 | 0.979 | 0.993 | 3/3 |
The score does not separate right from wrong answers (it rates wrong slightly higher). Safety in this
work comes from vetoes (mention coverage, verification, ambiguity checks), not from the score. Confidence
is capped at 0.30 whenever a veto fires; no recalibration was attempted.

## What was already present vs. added
| area | already present | added |
|---|---|---|
| 1 independent verification | plan/SQL fidelity, result plausibility | `verification/answer_verifier.py`: breakdown-reconciliation, semi-join equivalence, AVG bounds, COUNT DISTINCT bound; violations downgrade to CLARIFY |
| 2 relationship discovery | demo-only static join whitelist | `knowledge/relational.py`, `rel_context.py`: declared+inferred FKs (name evidence AND containment, declared keys preferred), safe/fan-out/ambiguous paths, LEFT-join group-bys, EXISTS semi-joins, join fidelity for discovered schemas; opt-in via `register_relational` |
| 3 governance | KPI aliases | `governance/metrics.py`: validated metric JSON, synonym conflicts clarified, date defaults |
| 4 adaptive clarification | generic "missing X" message | `clarify/materiality.py`: each reading executed; identical -> answer, different -> ask with each value; `clarify/messages.py` targeted text with close-match suggestions |
| 5 counterfactual/sensitivity | - | NULL-measure share, one-day filter-boundary shift (diagnostics in explanation/notes) |
| 6 schema change | `refresh_schema` manual | DDL-version schema cache (was a never-invalidated lru_cache), fingerprinted relational cache, schema-diff notes, replan on "no such table/column", missing-anchor message |
| 7 adversarial/drift eval | - | `evaluation/v3/adversarial_questions.py`, sealed schema-C final set, drift tests |
| 8 cost-aware execution | row cap only | read-only pragma, wall-time budget, EXPLAIN-based cartesian/scan-budget pre-flight |

## Not implemented / limitations
- No query rewriting for speed: optimization requires proven equivalence and none was attempted.
- Measures and numeric filters on non-anchor tables, counting a non-anchor entity (C20/B08 clarify instead), set-exclusion
  ("except X"), cross-period comparison with dimensions, and many-to-many group-by are unsupported (they clarify).
- Relational mode only for SQLite and only for datasets registered with `register_relational`; flat uploads are never linked.
- Month-only questions still default the year to 2026; join-row-loss and join-choice sensitivity diagnostics were not built
  (only LEFT-join reconciliation is verified).
- Three schemas, 84 questions in total, one author: no statistical claim.
