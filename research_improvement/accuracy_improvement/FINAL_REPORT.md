# Accuracy and coverage improvement mission — final report (2026-10-26)

## 1. SHAs
Start `0cde65b`. Frozen revised implementation `da925ad` (backend tree `d760e82`). Final: see `git log`
(local commits only, nothing pushed). Previous frozen build `38b60d1` and all its first-run artifacts unchanged.

## 2. Root causes of the 57 unanswered v5 questions (`root_causes.json/.md`)
Machine split: 22 produced no SQL; 29 produced SQL that disagreed with the reference (the veto was right);
6 produced correct SQL that a veto rejected. Classes (57 + 3 wrong values): unsupported capability 15,
missing business synonym 10, column abbreviation mismatch 9, excessively strict coverage audit 6, null-state
phrasing 5, wrong measure 3, unit terminology 2, missing relationship 2, and single cases (inclusion phrase,
number parsing, wrong aggregation, exclusion cue, intent misclassified, ambiguous metric, value negation,
comparator phrasing). Label disputes recorded: EN12 and RI12 (borderline); IN04 NULL-group convention;
HO08 date-role design rule.

## 3. Semantic improvements (`DESIGN_AND_CHANGES.md`)
Vocabulary normalisation with recorded/stated rewrites; composite questions with stated formulas built from
fully verified sub-questions; comparator suffixes; null-state filters; flag polarity synonyms; inclusion and
exclusion phrasing; role words for role-playing values; composite-key attributes as fan-out filters; catalog
alias fixes; four new wording checks; semantic layer extended to distinct and null counts. Inspectable semantic
catalog: `semantic_catalog.py`, `catalogs/`.

## 4. Wrong-answer defects corrected (v5, post-hoc)
IN14 extra unrequested column (entity-noun alias removed), RI12 negation of a value filter (exclusion cue +
`negated_value_kept` check), HO21 vague metric, RI24 rate as sum, IN28 bare-entity alias (now clarified).
Found and fixed during development: IN06 "1,000 or more" (comparator), HO14 "with us" -> 'US' (short codes),
"how many passengers" counting rows (new type check), gym-schema "guest visits included" (inclusion) and
"members with no visits" (null-state on an id). Not changed: HO08, IN04 (disagreements, documented).

## 5. Backend tests
Full suite at the freeze: 597 passed, 0 failed, 3 warnings (FastAPI deprecation). New: 16 mechanism tests,
55 generalization/metamorphic tests on a separate gym schema. Historical benchmarks 27/27, 25/25, 23/23;
six earlier evaluation sets (P4) identical to their previous results. One intermediate regression (P3: three
"paid by X" groupings) was found and fixed before the freeze.

## 6. Original vs post-hoc development results on v5 (`DEV_COMPARISON_v5_posthoc.md`) — NOT held out
correct 14 -> 63 / 74; answered 17 -> 64; wrong 7 -> 2 / 105; refusals 27 -> 30 / 31; unnecessary
clarifications 57 -> 10; 49 correct gained, 0 lost, 5 wrong eliminated, 0 new wrong; latency p50 54 -> 214 ms.

## 7. New blind evaluation (`BLIND_RESULTS_v6.md`) — provisional, agent-authored, not human-adjudicated
Frozen da925ad, 106 questions, first and only run: correct 5/73 (6.8%, CI 3.0-15.1); answered 11/73;
wrong 10/106 (9.4%, CI 5.2-16.5); refusals 29/33; unnecessary clarifications 62/73; p50/p95 319/1741 ms.
**The post-hoc improvement did not generalize**: on unseen schemas and wording the revised build is not better
than the previous build was on its own unseen set (14/74, 7/105). External licensed benchmarks were
unreachable (proxy blocks Hugging Face/GitHub); the blind set is from a separately instructed agent of the same
model family and is not independent human validation.

## 8. Safeguard ablations
Blind v6: all off 9 correct / 35 wrong; coverage+wording alone prevent 23 (cost 4 correct); semantic layer
alone 4; plan-fidelity alone 2; confidence gate, result consistency, answer verifier: 0. Post-hoc v5: full
63/2, all off 64/9. Better grounding on the tuned questions removed most of the coverage cost of the checks;
on blind data the checks remain the main protection. Confidence: AUROC 0.45 (A0) / 0.48 (A7) on v6, ECE 0.64;
the score carries no usable signal on unseen data.

## 9. Remaining unsupported capabilities
Ratios of two measures without a stated formula ("per"), products of columns ("quantity times unit cost"),
unit conversion, date differences, measures on child tables, parent-entity measures from a child anchor,
many-to-many grouping, anti-joins, period comparison without a stated order, non-SQLite relational mode,
non-English.

## 10. Paper and evidence paths
Manuscript revision: `paper/ieee_round8/InsightFlow_AI_IEEE_Round8.tex` (from Round 7 via `revise_round8.py`,
9 asserted edits; not compiled — no TeX toolchain). Round 7 revision and the unchanged original are kept.
Evidence: this directory (`PROGRESS.md`, `root_causes.*`, `DESIGN_AND_CHANGES.md`, `DEV_COMPARISON_v5_posthoc.md`,
`BLIND_RESULTS_v6.md`, `blind/`, `results/`, `catalogs/`, `freeze/FREEZE_MANIFEST_v2.json`,
`audit_round8_claims.py` (21/21 checks)).

## 11. Remaining research limitations
Agent-generated, unadjudicated question sets; small samples; the revised build overfits the revealed set;
new silent-error classes on v6 (time-unit word over a numeric column at confidence 1.0, inverted date state,
products returned as two sums, vague requests answered); latency roughly 4-6x higher; confidence uncalibrated
and uninformative; no external baseline; the paper is not publication-ready.

## Reproduce
    cd backend && python -m pytest -q                                          # 597 passed
    cd research_improvement/accuracy_improvement
    python run_dev.py A0 <label>; python compare.py results/v5_A0_posthoc_dev_<label>.json      # post-hoc v5
    cd blind && sha256sum -c V6_MANIFEST.sha256 (from evaluation/v6_blind)
    python run_v6.py A0 <new_label>; python score_v6.py results/v6_A0_<new_label>.json        # needs tree d760e82
    for c in A1 A2 A3 A4 A5 A6 A7 B1 B2 B3 B4 B5 B6; do python run_v6.py $c <label>; done; python analyse_v6.py
    cd .. && python audit_round8_claims.py
    cd ../../paper/ieee_round8 && python revise_round8.py
