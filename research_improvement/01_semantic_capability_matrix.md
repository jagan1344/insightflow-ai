# 01 — Semantic capability matrix (development evidence)

Status legend: **supported** (answers, value checked against independent SQL), **conditional** (answers
only in some phrasings / schemas, otherwise clarifies), **safely rejected** (CLARIFY/ABSTAIN by design),
**defective** (can return a wrong answer). Evidence: `dev_probe/probe_results_pre_freeze.json`
(33 probes on the round-6 schemas, which were used for tuning, so this is development evidence, not a
held-out measurement) and the named tests.

## Which safeguards run where
| stage | runs for | not for |
|---|---|---|
| 0 pre-SQL safety (destructive / injection) | every question | - |
| 2 plan validation, 2b adaptive clarification (alt. readings / join paths executed) | planner path | legacy demo fallback |
| 5a plan->SQL fidelity, 5b structural SQL validation, 5c dialect, 5d cost pre-flight | every compiled query | - |
| 6b result validation, 6c semantic fulfilment | every executed query | - |
| 10-11 confidence score + threshold decision (0.70 / 0.40) | every answer path | - |
| 11c mention coverage (values, numbers, table nouns, columns) | every answer path | unexplained-word check: relational (registered) datasets only |
| 11c2 wording audit (`intent_audit`) | every answer path | - |
| 11d answer verifier (reconciliation, semi-join equivalence, sensitivity) | every answer path | - |
| 11e standing caveats (inferred FK, related-table measure grain) | relational datasets | - |
| 12b semantic layer (spec, type check, preservation, fail-closed on exception) | non-demo datasets, intents direct_kpi / breakdown / top_n / trend / ratio | demo dataset; comparison, growth, share_of_total, contribution, average_at_grain, relative_to_stat, extremum, distinct_count, null_count, rolling_avg, top_n_per_group, threshold_grouped, post_agg_stat |

## Matrix
| # | category | status | evidence / notes |
|---|---|---|---|
| 1 | Direct KPI | supported | probe 2/2; K1 single-family 100% |
| 2 | Breakdown | supported | probe 2/2 incl. NULL group kept (`test_round6::test_null_group_not_dropped`) |
| 3 | Top-N | supported | probe 1/1 (ordered match); NULL group never ranked (round 4) |
| 4 | Trends | conditional | plain monthly trend works when only one date column exists; with two date columns "Monthly total usd" clarifies (correct), but a role named as "by issue date" is not bound to `issued_on` (unnecessary clarification, probe) |
| 5 | Multi-table joins | supported (registered relational datasets, SQLite only) | probe 1/1; LEFT JOIN on many-to-one paths |
| 6 | Related-table numeric thresholds | supported (fixed in this mission) | "larger/bigger/smaller than", "at least/most"; unknown comparatives ("taller than") never read as "="; `test_coverage_phase2::test_related_numeric_threshold`, `test_inclusive_threshold`, `test_unknown_comparative_is_not_read_as_equality` |
| 7 | FK inference | conditional (extended in this mission) | name evidence, or (new) key-suffix evidence for TEXT declared keys with full containment, >=3 distinct values, unique parent; inferred edges disclosed as WARN; integer codes without name evidence stay unlinked; `test_role_playing_inferred_fk`, `test_suffix_inference_rules` |
| 8 | Abbreviated columns | conditional | dictionary `knowledge/abbrev.py` (pax, temp, apt, carr, flt, ...); unknown abbreviations clarify; "how many <measure noun>" now clarifies instead of counting rows (`test_how_many_measure_noun_is_not_a_row_count`) |
| 9 | Negation / exclusion | supported | NOT IN / `<>` keeping NULLs, flag = 0; A17 regression; `test_round6::test_flag_exclusion_keeps_the_zero_rows`, `test_negated_value_filter_keeps_other_groups` |
| 10 | Boolean flags | supported (polarity fixed in this mission) | flags never summed (type check); polarity-named flags (`sensor_ok`) need the polarity word or a listed antonym, negation honoured; `test_polarity_flag*` |
| 11 | NULL conditions | supported | "no temperature", "not been paid" -> IS NULL |
| 12 | Distinct counting | supported | entity counts use COUNT(DISTINCT key); `test_entity_count_is_distinct` |
| 13 | Join fan-out | supported as semi-join filter; grouping safely rejected | EXISTS filters (fixed: value-qualified noun "High priority tickets"); grouping by a one-to-many attribute clarifies; `test_value_qualified_fanout_filter_is_a_semi_join` |
| 14 | Date-role ambiguity | supported | ambiguous date -> clarify unless all readings agree; named role answers |
| 15 | Period comparisons | safely rejected on relational datasets (probe); supported on the demo dataset only | |
| 16 | Ratios of two measures | safely rejected | `ratio_unsupported` type check; no formula implemented because business definition (sum/sum vs mean of ratios) and units are not established; `test_per_measure_ratio_is_not_two_sums` |
| 17 | Share of total | safely rejected on relational datasets (probe); demo only | |
| 18 | Many-to-many joins | safely rejected | |
| 19 | Anti-joins ("no tickets") | safely rejected | |
| 20 | Ambiguous questions | safely rejected | vague wording, role-ambiguous dimension ("by airport") |
| 21 | Unsupported metrics | safely rejected | unknown measure, forecasting |
| 22 | Verifier exceptions | supported (fail-closed) | exception -> CLARIFY, conf <= 0.30, no chart/recommendation, diagnostic recorded; `test_round6::test_verifier_exception_fails_closed` |

No category was found **defective** after the fixes below. Two defects were found and fixed during this
mission (both were masked by the mention-coverage veto, i.e. they produced CLARIFY, not wrong answers):
- R15: "larger than 100 acres" compiled to `acres = 100`.
- R05: "faulty sensor" compiled to `sensor_ok = 1` (inverted polarity).
One defect was introduced and caught during development: after adding "passengers" as an alias,
"How many passengers were there?" returned COUNT(*) of flights (700 vs 104698). Fixed by the new
`count_of_measure_noun` type check before freezing.

## Fixes made in this mission (general, schema-driven; no question-specific rules)
| file | change |
|---|---|
| `plan/planner.py` | comparative vocabulary (larger/bigger/higher/smaller/lower than); an unknown "<word>er/than N" never defaults to "="; polarity-named flags need polarity word or antonym (negation-aware); fan-out check skips a column already filtered by a value |
| `reliability/mention_coverage.py` | `words_consumed_by_plan`: comparatives / "at least" / flag antonyms count as explained only when the plan applied the matching filter |
| `orchestrator.py` | uses `words_consumed_by_plan`; research-only ablation switches (default off) |
| `semantics/spec.py` | "average X per <base-table row>" is a per-row mean, not a grouping |
| `semantics/typecheck.py` | `count_of_measure_noun` violation |
| `knowledge/kpi_catalog.py` | expanded core abbreviation aliases (`pax_cnt` -> passenger(s)) |
| `knowledge/relational.py` | key-suffix FK evidence tier (`_suffix_candidates`) |
| `config.py`, `reliability/decision.py` | `INSIGHTFLOW_ABLATE` research switches (semantic, confidence_gate, result_consistency, plan_fidelity, mention_coverage, answer_verifier) |
