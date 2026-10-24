# Phase 4 — Implemented analytical capabilities

Implementations added across prior rounds + Phase 4 (median /
percentile / stddev / variance). Each is now **IMPLEMENTED AND
VERIFIED** against an independent numerical oracle (either stdlib
`sqlite3` or stdlib `statistics` module).

## Numeric capabilities

| Capability | Code path | Oracle test | Verified value (demo DB) |
|---|---|---|---|
| Sum / count / average | existing | existing | 3 388 831.47 revenue; 2 037 orders; 1 663.63 AOV |
| Aggregate MIN/MAX | `IntentKind.EXTREMUM` | `[extremum_max_revenue]` / `[extremum_min_revenue]` / `[extremum_max_quantity]` | 9 482.06 / 5.01 / 10 |
| COUNT DISTINCT (joined dim) | `IntentKind.DISTINCT_COUNT` + `_ensure_join_for_formula` | `[count_distinct_customers]` / `[count_distinct_products]` | 60 / 12 |
| Null-aware COUNT | `IntentKind.NULL_COUNT` + `FilterExpr("null")` | `[null_count_cost]` | 0 (demo has no nulls) |
| HAVING threshold | `IntentKind.THRESHOLD_GROUPED` + `metric_(gt\|lt)_grouped` | `[threshold_months_gt]` / `[threshold_regions_gt]` | 4 / 4 |
| Median (Phase 4) | `IntentKind.POST_AGG_STAT` + `stats.median` | `[median_revenue]` | 1 058.20 |
| Percentile (Phase 4) | same + `stats.percentile` | `[percentile_90_revenue]` | 4 180.50 |
| Standard deviation (Phase 4) | same + `stats.stdev` | `[stddev_revenue]` | 1 805.73 |
| Variance (Phase 4) | same + `stats.variance` | `[variance_revenue]` | 3 260 672.17 |

## Temporal capabilities

| Capability | Code path | Oracle test |
|---|---|---|
| Explicit calendar period / range | `_find_month_range` + `_bind_time_filter` | `test_A_jan_through_sep_returns_full_range` |
| Relative period (last/this/next year/month/quarter) | `_find_relative_period` | `test_B_*` |
| MTD / QTD / YTD | `_find_relative_period` (added in this round) | `test_mtd_resolves_to_current_month_to_ref_date` |
| Last N days / weeks sliding window | `_find_last_n_days` + day-level `time_range` | `[last_30_days]` |
| Multi-quarter comparison | `_find_two_months` extended for Q refs | `test_multi_quarter_comparison_returns_two_periods` |
| Monthly rolling / moving average | `IntentKind.ROLLING_AVG` + `_compile_rolling_avg` | `[rolling_avg_3m]` |

## Ranking + grouping

| Capability | Code path | Oracle test |
|---|---|---|
| Top-N / Bottom-N (incl. spelled numbers) | existing + `_parse_count_after` | existing + `test_invariant_equivalent_phrasings_same_sql_shape` |
| Top-N per group (window ranking) | `IntentKind.TOP_N_PER_GROUP` + `_compile_top_n_per_group` | `[top_2_per_category]` |
| Multi-metric breakdown | existing | `test_G_*` |

## Still SAFELY REFUSED

- Skewness, kurtosis, mode (no native SQLite; not implemented via
  post-agg in this round).
- Rolling at non-monthly cadence (day / week / quarter / year).
- Duplicate-row detection.
- "List customers with the most X" ranked-list phrasing — the
  equivalent "top N by metric" IS supported.
- Row-level single-record retrieval.
- Generic data-quality asks without a column name.

## Reproduction

```sh
cd backend
python data/seed.py
export DATABASE_URL="sqlite:///$(pwd)/data/insightflow.db"
export INSIGHTFLOW_REF_DATE="2026-10-21"
python -m pytest tests/test_capability_gate_invariants.py -v
```

Each `test_implemented_capability_matches_oracle[<label>]` runs the
pipeline AND an independent `sqlite3` or `statistics`-module oracle,
and asserts equality to 4 decimal places.
