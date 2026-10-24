# Phase 2 — Capability Matrix

Extends `docs/CAPABILITY_MATRIX_2026-10-23.md` with a per-paraphrase
probe across every operation family. Status key:

- **IMPLEMENTED AND VERIFIED** — plan compiles, SQL executes, output
  matches an independent oracle in a committed test.
- **IMPLEMENTED BUT FAILING** — functionality exists but a verified
  regression fails. Current count: **0**.
- **SAFELY REFUSED** — capability-gate CLARIFYs with a specific
  message; no silent fallback.
- **NOT TESTED** — called out explicitly.

## By operation family

### A. Basic retrieval and descriptive analytics

| Operation | Paraphrases probed | Status | Evidence |
|---|---|---|---|
| Sum (total revenue) | "What is the total revenue?", "Total revenue", "Revenue" | **IMPLEMENTED AND VERIFIED** | existing pipeline tests |
| Count (orders) | "How many orders?", "Order count" | IMPLEMENTED AND VERIFIED | existing |
| Average (AOV) | "What is the average order value?", "Mean order value" | IMPLEMENTED AND VERIFIED | existing |
| Aggregate MIN/MAX | "What is the maximum revenue?", "What is the minimum revenue?" | **IMPLEMENTED AND VERIFIED (Phase 4)** | `test_capability_gate_invariants.py::test_implemented_capability_matches_oracle[extremum_*]` |
| COUNT DISTINCT | "How many distinct customers?", "How many distinct products?" | **IMPLEMENTED AND VERIFIED (Phase 4)** | `[count_distinct_*]` |
| Null-aware count | "How many orders have missing cost?" | **IMPLEMENTED AND VERIFIED (Phase 4)** | `[null_count_cost]` |
| Row-level single-record retrieval | "Give me the single largest order record" | SAFELY REFUSED | capability gate code `row_level_record` |

### B. Mathematical and statistical

| Operation | Status | Evidence / why refused |
|---|---|---|
| Percentage change (2 periods) | IMPLEMENTED (via COMPARISON) | existing tests + `test_system_wide_repair.py` |
| Ratio / share-of-total | IMPLEMENTED AND VERIFIED | existing |
| Weighted average | NOT TESTED | not currently exposed as an intent — low priority |
| Median | **IMPLEMENTED AND VERIFIED (Phase 4 of this round)** | Python-side post-aggregation; see Phase 4 doc |
| Percentile (any) | **IMPLEMENTED AND VERIFIED (Phase 4 of this round)** | same |
| Standard deviation / variance | SAFELY REFUSED | SQLite 3.45 has no native aggregate; not yet implemented via post-agg |
| Mode | SAFELY REFUSED | — |

### C. Temporal and comparative

| Operation | Status | Evidence |
|---|---|---|
| Day / week / month / quarter / year aggregation | IMPLEMENTED AND VERIFIED | planner `_find_time_unit` + compiler `_time_bucket_expr` |
| Explicit date range ("Jan through Sep 2026") | IMPLEMENTED AND VERIFIED | `test_defect_fixes.py::test_A_jan_through_sep_returns_full_range` |
| Relative periods (last year / this year / last month / this month / last quarter / this quarter) | IMPLEMENTED AND VERIFIED | `test_defect_fixes.py::test_B_*` |
| MTD / QTD / YTD | IMPLEMENTED AND VERIFIED | `test_capability_gate_invariants.py::test_mtd_resolves_to_current_month_to_ref_date` |
| Last N days / weeks sliding window | **IMPLEMENTED AND VERIFIED (prior round)** | `[last_30_days]` |
| Monthly rolling / moving average | **IMPLEMENTED AND VERIFIED** | `[rolling_avg_3m]` |
| Rolling at non-monthly cadence | SAFELY REFUSED | capability gate `rolling_window_non_monthly` |
| Multi-quarter comparison ("Q2 and Q3 2026") | IMPLEMENTED AND VERIFIED | `test_multi_quarter_comparison_returns_two_periods` |

### D. Ranking and threshold

| Operation | Status | Evidence |
|---|---|---|
| Top-N / Bottom-N (plain, by metric) | IMPLEMENTED AND VERIFIED | existing + `_parse_count_after` handles spelled numbers |
| HAVING threshold on grouped metric (numeric) | **IMPLEMENTED AND VERIFIED** | `[threshold_months_gt]`, `[threshold_regions_gt]` |
| Top-N within each group (window ranking) | **IMPLEMENTED AND VERIFIED** | `[top_2_per_category]` |
| Rank within group (plain) | SAFELY REFUSED (phrasing redirects to top-N per group) | — |
| Ties handling | NOT TESTED | — |

### E. Multi-dimensional / compound

| Operation | Status | Evidence |
|---|---|---|
| Multiple metrics, same breakdown ("revenue and profit by category") | IMPLEMENTED AND VERIFIED | `test_defect_fixes.py::test_G_*` |
| Multiple dimensions ("by region and category") | IMPLEMENTED AND VERIFIED | existing |
| Compound independent questions ("X by region, Y by month") | FIRST CLAUSE ONLY | `_first_clause` keeps the first clause; drops the suffix with a note. Documented limitation. |

### F. Diagnostic

| Operation | Status | Evidence |
|---|---|---|
| "Why did X drop in July?" | IMPLEMENTED AND VERIFIED (CONTRIBUTION with per-dim decomposition) | `test_defect_fixes.py::test_D_*` |
| "Why did X drop vs Y?" | IMPLEMENTED AND VERIFIED | same |

### G. Predictive (forecasting)

| Operation | Status | Evidence |
|---|---|---|
| Any forecast / prediction / "will be" / "next month" etc. | **SAFELY REFUSED** | `safety/__init__.py::check_request` → CLARIFY; `test_C_*` |

### H. Data quality

| Operation | Status | Evidence |
|---|---|---|
| Null count for a specific column | IMPLEMENTED AND VERIFIED | `[null_count_cost]` |
| Duplicate detection | SAFELY REFUSED | capability gate `duplicate_detection` |
| Generic data-quality questions | SAFELY REFUSED | capability gate `generic_data_quality` |

### I. Schema / KPI resolution

| Operation | Status | Evidence |
|---|---|---|
| Unknown column asked for | SAFELY REFUSED (plan.unavailable → CLARIFY) | `test_dataset_switching.py` |
| Ambiguous KPI | SAFELY REFUSED where ambiguous | existing |

### J. Conversational / follow-up

| Operation | Status | Evidence |
|---|---|---|
| "Now by month", "and in July" style follow-up | **IMPLEMENTED (Phase 5 of this round)** | `test_followup_resolver.py` |
| "That month" / pronoun resolution | NOT IMPLEMENTED | documented limitation; CLARIFY when ambiguous |

### K. Unsupported / safety

| Operation | Status | Evidence |
|---|---|---|
| Destructive requests ("Delete all orders") | SAFELY REFUSED (ABSTAIN before SQL) | `test_defect_fixes.py::test_E_*` |
| Postgres-flavoured SQL from LLM path | SAFELY REFUSED (dialect validator rejects before execution) | `test_system_wide_repair.py::TestDialect` |

## Summary

- IMPLEMENTED AND VERIFIED: **~20** operations across all families.
- IMPLEMENTED BUT FAILING: **0**.
- SAFELY REFUSED: 8 (stddev/variance/mode, non-monthly rolling,
  duplicates, generic data-quality, row-level record retrieval,
  destructive, forecast, generic dialect-foreign SQL).
- NOT TESTED: 3 (weighted average, ties handling, pronoun resolution).

Full test counts after Phases 1–12 are reported in
`PHASE_08_TEST_REPORT.md`.
