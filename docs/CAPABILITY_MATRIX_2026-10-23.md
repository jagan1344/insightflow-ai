# Capability matrix — 2026-10-23 (Phase 2 implementations)

**Starting commit:** `b00cd65`.
**This commit:** Phase 2 implementations + regression suite.
**Test counts:** 211 (prior) → 253 (Phase 1 regressions) → **251 passed** (after replacing refusal assertions with ANSWER + oracle-matched regressions, net +40 vs. 211 baseline).

## Status key

- **IMPLEMENTED AND VERIFIED** — plan compiles, SQL executes, output
  matches an INDEPENDENT numerical oracle (direct `sqlite3` query).
- **IMPLEMENTED BUT FAILING** — none.
- **SAFELY REFUSED** — capability-gate CLARIFYs with a specific user
  message; no silent `SUM(revenue)` fallback.
- **NOT TESTED** — called out explicitly below.

## IMPLEMENTED AND VERIFIED (7 new in this round, atop the existing ~13)

| Capability | Intent kind | Compiler | Test (oracle-matched) | Verified value |
|---|---|---|---|---|
| COUNT DISTINCT on a joined dim | `IntentKind.DISTINCT_COUNT` | `_compile_flat` with synthetic measure + auto-join | `test_implemented_capability_matches_oracle[count_distinct_customers]`, `[count_distinct_products]` | 60 customers, 12 products |
| Null-aware COUNT | `IntentKind.NULL_COUNT` | `_compile_flat` with `FilterExpr(kind="null", column=…)` | `[null_count_cost]` | 0 (demo DB has no nulls — matches oracle) |
| Aggregate MIN/MAX of a column | `IntentKind.EXTREMUM` | `_compile_flat` with synthetic `MIN(col)` / `MAX(col)` measure | `[extremum_max_revenue]`, `[extremum_min_revenue]`, `[extremum_max_quantity]` | 9482.06, 5.01, 10 |
| "Last N days" sliding window | existing `time_range` filter, day-level | `_extra_where` recognises YYYY-MM-DD lo/hi | `[last_30_days]` | 121,979.22 |
| HAVING threshold on grouped metric (month) | `IntentKind.THRESHOLD_GROUPED` | `_compile_flat` with `metric_gt_grouped` filter | `[threshold_months_gt]` | 4 months (Jun 454994, May 453981, Mar 413344, Apr 402345) |
| HAVING threshold on grouped metric (dim) | same | same | `[threshold_regions_gt]` | 4 regions above 500k |
| Monthly rolling / moving average | `IntentKind.ROLLING_AVG` | `_compile_rolling_avg` with window `AVG() OVER (ORDER BY ROWS BETWEEN N PRECEDING AND CURRENT ROW)` | `[rolling_avg_3m]` | 9-row series, each row matches oracle |
| Top N per group (window ranking) | `IntentKind.TOP_N_PER_GROUP` | `_compile_top_n_per_group` with `ROW_NUMBER() OVER (PARTITION BY …)` | `[top_2_per_category]` | 8 rows, 4 categories × 2 products, oracle-matched |

### Pre-existing (preserved and still verified)

Sums / counts / averages / breakdowns / trends / comparisons / top-N /
bottom-N / share-of-total / contribution diagnostic / relative-to-stat
("customers above average") / ratio / average-at-grain / growth —
all still ANSWER with the same SQL shape; existing tests cover them.

## SAFELY REFUSED (capability gate — specific CLARIFY messages)

| Capability | Reason refused | What a user should try instead |
|---|---|---|
| Median (as a statistic) | SQLite 3.45 has no `median()` aggregate; computing it with a self-count sub-select is slow and brittle on arbitrary data | "average order value" or a top-N / bottom-N view |
| Percentile / quartile / decile | Same reason | top-N / bottom-N |
| Standard deviation / variance / skewness / kurtosis | No native SQLite aggregate | — |
| Mode | No native SQLite aggregate | top-N by frequency |
| Rolling / moving average at non-monthly cadence (day / week / quarter / year) | Implemented only at monthly cadence | ask for the monthly equivalent |
| Duplicate-row detection | Not yet implemented | Analytics Explorer with direct SQL |
| "List customers with the most X" ranked-list style | Not yet implemented | "top 5 customers by X" phrasing |
| Row-level single-record retrieval (not aggregate) | SELECT * returning one specific row is a different intent | "bottom 5 orders by revenue" |
| Generic data-quality asks without a column name | Needs a column target | ask for a specific column, or use the Data Quality page |

The gate's full pattern list lives in
`backend/insightflow/safety/capability_check.py`. Each pattern has a
`code` and a user-facing `reason`; the orchestrator surfaces both.

## NOT TESTED

- **Multi-dataset switching mid-conversation** — covered by the
  existing `test_dataset_switching.py` suite, which still passes.
- **Statefully resolved follow-ups** ("that month", "compare it with
  the previous period") — intentionally not implemented. The pipeline
  treats each question fresh; the capability gate + semantic
  fulfilment ensure no silent wrong answer.
- **Uploaded dataset running the NEW intents** — the capability gate
  works per-question (no state); the compiler already differentiates
  `demo` vs. `uploaded` for the FLAT shape. The joined-table
  auto-injection in `_ensure_join_for_formula` is a `demo`-only path
  by design; uploaded datasets are single-table so no join is needed.
- **Rolling average on an uploaded dataset** — relies on time-bucket
  SQL (`substr(date, 1, 7)`) which the compiler already does for
  uploaded tables. Not tested end-to-end.

## Numbers reported

- Tested intent families: 20 (A–K from the audit matrix).
- Independently verified correct answers in Phase 2: 11
  (`test_implemented_capability_matches_oracle` parametrisations) +
  all prior test coverage.
- Safe refusals: 11 parametrised (`test_unsupported_capability_routes_to_clarify`).
- Remaining incorrect answers surfaced by this round's audit: 0.
- Full suite: `251 passed / 0 failed / 0 skipped`, 2 pre-existing
  FastAPI deprecation warnings.

## Reproduction

```sh
cd backend
pip install -r requirements.txt
python data/seed.py
export DATABASE_URL="sqlite:///$(pwd)/data/insightflow.db"
export INSIGHTFLOW_REF_DATE="2026-10-21"
python -m pytest tests -q           # 251 passed
python -m pytest tests/test_capability_gate_invariants.py -v
```

The ask API endpoint (`POST /api/ask`) and the frontend Ask AI page
both use the same orchestrator, so every verified capability above
is available through the UI with no additional wiring.
