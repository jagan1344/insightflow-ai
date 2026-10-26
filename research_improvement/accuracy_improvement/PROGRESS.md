# Accuracy-improvement mission: progress ledger

Start: `0cde65b` (after the Round 7 manuscript revision). Frozen first-run baseline: `38b60d1`
(v5 A0: 14/74 correct, 7/105 wrong). v5 is now a REVEALED DIAGNOSTIC set; all v5 runs below are
POST-HOC DEVELOPMENT results (`results/v5_A0_posthoc_dev_*.json`), never held out.

| step | status | evidence |
|---|---|---|
| Phase 1 root causes | done | `root_causes.json/.md`, `trace_frozen.jsonl`, `stage_frozen.json`: of 57 refusals, 22 no SQL, 29 wrong SQL caught by a veto, 6 correct SQL vetoed |
| s1 vocabulary normalisation | done | 22/74 correct, 8 wrong (IN06 '1,000 or more' read as '= 1000') |
| s2 comparator suffix, wording checks, catalog aliases | done | 24/74, 2 wrong |
| s3 flag synonyms, exclusion cues | done | 26/74, 3 wrong (HO14 'with us' -> 'US') |
| s4 short-code case rule, null-state filters, function words | done | 33/74, 2 wrong |
| s5/s6 unbound-dim cleanup, generic money aliases, agent 'by', null-count fix | done | 47/74, 2 wrong (HO08 date-role policy, IN04 NULL-group convention) |
| monitor sets P2 (taken at s4) | done | identical to P1 on all six earlier sets |
| full suite at s6 | 525 passed, 1 failed (fixed: NOT EXISTS scope in negated_value_kept) | |
| composites, role words, composite-key attributes, agent rule | done | v5 post-hoc 63/74, 2 wrong |
| tests | done | 16 mechanism + 55 generalization tests; suite 597 passed |
| monitor sets P3 (regression found) / P4 (= P1) | done | |
| freeze | done | da925ad, tree d760e82, `freeze/FREEZE_MANIFEST_v2.json` |
| blind v6 set authored, sealed (4f4241c), first run (6276b24) | done | 5/73 correct, 10/106 wrong (negative) |
| v6 ablations + confidence | done | `BLIND_RESULTS_v6.md` |
| paper Round 8 | done (not compiled) | `paper/ieee_round8/` |
| final report | done | `FINAL_REPORT.md` |
