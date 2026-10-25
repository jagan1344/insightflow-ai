# Semantic correctness layer - round 6 (2026-10-25)

Starting point `c5edbbd` (verified clean). Implementation frozen at `78d906b` before the new sealed set was authored.

## 1. Architecture
New package `backend/insightflow/semantics/`:
- `spec.py` - `SemanticSpec`: metrics (aggregation + grounded source column + semantic type money/count/flag/id/date/...), requested vs produced output shape, dimensions, sort/limit, filters with polarity, exclusions, date role (named/guessed), join paths (safe / semi-join / fan-out), units, unresolved/unsupported. Built from the AnalyticalPlan and, independently, from the wording (`requested_shape`). Every reference must resolve to a discovered column or a validated metric definition, otherwise it is recorded as `unresolved`.
- `typecheck.py` - before execution: flag used as quantity, identifier used as quantity, ungrounded reference, scalar-vs-grouped mismatch, guessed date role, unsafe join, polarity inverted, ratio ("X per Y") asked but not representable.
- `preserve.py` - after execution: spec vs SQL vs rows vs written answer (time bounds, row shape, exclusions kept, numbers in the explanation traceable to rows).
- `verify.py` - `verify_semantics(...)` -> findings (violation | note). A violation vetoes ANSWER (CLARIFY, confidence capped at 0.30); a note adds an assumption caveat (WARN).
- Integrated in `orchestrator.py` step 12b for non-demo datasets and intents direct_kpi / breakdown / top_n / trend / ratio.
- Supporting: `knowledge/abbrev.py` (abbreviation/synonym canonicalisation), related-table 0/1 flags (`rel_context.py`, `dataset_registry.py`), planner/mention-coverage guards (see git diff).
- Ambiguity policy unchanged and reused: governed definitions first; alternative readings/join paths are executed; identical results -> answer with the assumption noted; different -> clarify showing each value; unsafe -> abstain.

## 2. Error classes prevented (each has a test)
success-but-wrong-grain (flag counted as money, customer vs transaction count), scalar vs grouped, inverted flag polarity ("excluding cancelled" -> is_cancelled=0), "X per Y" answered as two sums, guessed date role, fan-out measure double count, related-table filter/measure, unknown values silently dropped, ungrounded names. Tests: `tests/test_semantic_layer.py` (32), `tests/test_round6.py` (4).

## 3. Test results
- Full backend suite (from `backend/`): **473 passed, 0 failed** (469 + 4 new in `test_round6.py`; the new file restores global dataset state after itself - without that it broke 80 other tests, caught and fixed before commit).
- Historical benchmarks unchanged: exec_accuracy_bench 27/27, advanced 25/25, held-out 23/23 answerable (printed 23/28 = all answerable correct). `evaluation/v2` was restored with `git checkout`.
- Monitor sets (post-tuning, label M3): adversarial 15/15 correct, 0 silent wrong; dev4 44/46, 0 silent; final5 44/47, 0 silent; final4 25/27, 1 silent (F17, disputed label, see round 4); final (schema C) 24/24, 1 silent (C25, outdated label, see round 4).

## 4. New sealed evaluation (3 unfamiliar schemas: airline, saas, farm; 66 questions, reference answers by independent sqlite3 SQL; sha256 seal `evaluation/v3/FINAL6_SEAL.txt`; code frozen at `78d906b`)
First run `final6_K1_first_and_only` (preserved, unedited; recorded before inspecting failures):
- correct / answerable: **42/54**; answered / answerable: 43/54; abstained on answerable: 11
- incorrect / answered: 2/46 answers were wrong (counting clarify-kind questions answered); silent wrong / all: **2/66** (A17 inverted polarity 45804.48 vs 618324.80; V07 "yield per acre" answered although ratio unsupported)
- correct clarifications: 11/12; unnecessary clarifications (answerable but abstained): 11 (coverage gaps: FK names not inferred, unmapped abbreviations, related-table flags, "not paid", word stems)
- confidence: band [0.9,1.0]: 43 answered, 39 correct, 2 silent wrong (+2 WARN on trap questions); band [0.7,0.9): 3/3 correct. **Both silent errors had confidence ~0.98** - the score does not separate right from wrong. Mean 0.976 (correct) vs 0.979 (wrong).
- latency p50/p95 14/38 ms; no destructive SQL generated (read-only validator tests unchanged and passing).

Post-hoc run `final6_K3_posthoc_not_heldout` (tuned after seeing K1; **not held out**; K2 is an intermediate tuned run): 49/54 correct, 49/54 answered, 0/66 silent wrong, 12/12 correct clarifications, 5 unnecessary clarifications (A11, A12, A13, R05, R15), p50/p95 15/43 ms.
The K3 numbers show fixes of the observed classes, not generalisation. K1 is the generalisation evidence.

## 5. Remaining silent wrongs / limits
- None observed in the tuned runs except the two disputed-label cases above, but 5 small developer-authored sealed sets cannot prove absence. Pooled over all first runs, 23 of 177 answers scored >= 0.9 were wrong (13%).
- Unnecessary clarifications remain (5/54 on K3; 11/54 on K1): safer than wrong, but a real coverage cost.
- Confidence is not calibrated; it is a validity score. Protection comes from vetoes, not from the number. Do not read 0.98 as 98%.
- Unsupported (abstain): ratios of two measures, period-over-period with dimensions, share-of-total over joins, many-to-many group-by, anti-joins, non-ISO dates, non-SQLite, non-English, FKs with unconventional names that are neither declared nor inferable.
- Heuristic checks (wording, stems, abbreviations) can over/under-trigger.

## 6. Reproduce
    cd backend && python -m pytest -q
    cd ../evaluation/v3 && sha256sum -c FINAL6_SEAL.txt
    python run_r6.py final6 <label>          # K1 needed code at 78d906b
    python calibration_report.py > results/SUMMARY_round6.md
    cd ../v2 && python exec_accuracy_bench.py && python exec_accuracy_advanced.py && python heldout_e2e.py; cd ../.. && git checkout -- evaluation/v2
