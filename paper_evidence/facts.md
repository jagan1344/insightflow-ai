# Implementation facts for the paper

Every claim here has an exact code citation (file:line) or a reproducible SQL/pytest
output. Measured 2026-10-09 at commit 3c843de88ca0b62669749b217aaef000e3e6363e,
branch `claude/insightflow-ai-build-2neph7`.

Where the master-prompt narrative differs from the code, the code wins and the
delta is logged in `discrepancies.md`.

## 1. AnalyticalPlan IR

Dataclass `AnalyticalPlan` defined in `backend/insightflow/plan/plan.py`:

```
class AnalyticalPlan:
    intent_kind: str = IntentKind.DIRECT_KPI
    measures: List[MeasureRef] = field(default_factory=list)
    dims: List[DimRef] = field(default_factory=list)
    filters: List[FilterExpr] = field(default_factory=list)
    grain: Optional[Grain] = None
    comparison: Optional[ComparisonSpec] = None
    contribution: Optional[ContributionSpec] = None
    relative_stat: Optional["RelativeStatSpec"] = None
    top_n: Optional[int] = None
    share_of_total: bool = False
    order_by: str = ""       # "measure_desc" | "measure_asc" | "time_asc" | ""
    # what the planner asked for but couldn't bind on the current dataset —
    # each entry is human-readable so the CLARIFY message can name it
    unavailable: List[str] = field(default_factory=list)
    # planner notes explaining WHY it chose this shape — surfaced by the
    # explainer as the evidence trace
    notes: List[str] = field(default_factory=list)
    # the original question, retained for the evidence trace
    question: str = ""
    # the dataset table this plan targets
```

Source: `backend/insightflow/plan/plan.py` (lines containing the `AnalyticalPlan` definition).

## 2. Intent kinds (closed vocabulary)

From `backend/insightflow/plan/plan.py`, class `IntentKind`:

| # | Code name | String literal | One-line meaning (from code comment) |
|---|-----------|----------------|----------------------------------------|
| 1 | DIRECT_KPI | direct_kpi | "What's the revenue?" |
| 2 | BREAKDOWN | breakdown | "Revenue by region" |
| 3 | TREND | trend | "Revenue over time / by month" |
| 4 | COMPARISON | comparison | "June vs July revenue" |
| 5 | GROWTH | growth | "Revenue growth month-over-month" |
| 6 | TOP_N | top_n | "Top 5 products by revenue" |
| 7 | BOTTOM_N | bottom_n | "Bottom 3 regions by profit" |
| 8 | SHARE_OF_TOTAL | share_of_total | "% of revenue by region" |
| 9 | RATIO | ratio | "Profit per order" |
| 10 | AVERAGE_AT_GRAIN | average_at_grain | "Average monthly revenue" |
| 11 | CONTRIBUTION | contribution | "Which region contributed most to the decline?" |
| 12 | RELATIVE_TO_STAT | relative_to_stat |  |
| 13 | UNSUPPORTED | unsupported | dataset can't answer this |
| 14 | AMBIGUOUS | ambiguous | question needs clarification |

## 3. Confidence signals and weights

Signals and weights are defined in `backend/insightflow/config.py` and computed in `backend/insightflow/reliability/confidence.py`.

```python
DEFAULT_WEIGHTS: Dict[str, float] = {
    # 9-signal weighting (2026-09-24): adds `plan_fidelity` at 0.14 by
    # trimming intent_coverage (legacy) and kpi_match slightly. Sum = 1.00.
    "sql_validity":        0.12,
    "schema_match":        0.10,
    "kpi_match":           0.13,
    "context_consistency": 0.13,
    "data_completeness":   0.08,
    "evidence_strength":   0.07,
    "result_consistency":  0.10,
    "intent_coverage":     0.13,
    "plan_fidelity":       0.14,
}
```

**Sum of weights:** 1.0000  (expected 1.00)
**Signal count:** 9
**Thresholds:** threshold_high=0.7, threshold_low=0.4

## 4. Cap formula (code citation)

```python
17:The `plan_fidelity` hard cap `overall ≤ min(intent_coverage, plan_fidelity) + 0.05`
18-means neither a legacy-parse miss nor a plan-shape mismatch can be masked
19-by other signals.
--
162:        score = min(score, 0.30)
163-
164:    # Twin hard caps — neither a legacy-parse miss nor a plan-shape
165-    # mismatch can be masked by other signals.
```

Expressed: 662C = \min(S, \min(\sigma_{coverage}, \sigma_{fidelity}) + 0.05)662

## 5. Decision thresholds + commit history

Thresholds defined at `backend/insightflow/config.py` lines:
57:    threshold_high: float = field(default_factory=lambda: _envf("CONF_HIGH", 0.70))
58:    threshold_low:  float = field(default_factory=lambda: _envf("CONF_LOW",  0.40))

### git blame for threshold values (when they were set)
  5ee79e1 2026-09-22 Add web product: FastAPI backend, Next.js landing + app, live realtime dashboard

### git blame for the 55-question benchmark
  4a2675c 2026-09-22 Add research evaluation layer: benchmark, real experiments, BIRD alignment

## 6. SQL safety validator rules

Code: `backend/insightflow/validation/sql_validator.py`

- Only statements starting with SELECT or WITH are permitted.
- A deny-list of mutating keywords rejects any of: insert, update, delete, drop, alter, create, truncate, replace, attach, detach, pragma, grant, revoke, vacuum, merge, call, exec.
- Multiple statements are rejected (any `;` outside a trailing position fails validation).
- Schema check: every referenced table must exist, every qualified column must exist.
- CTE aliases (`WITH foo AS …`) are detected and excluded from the unknown-table check.

## 7. Plan-to-SQL fidelity validator

Code: `backend/insightflow/plan/fidelity.py`

Called by the orchestrator between SQL validation and execution (`backend/insightflow/orchestrator.py` around the "5a. Plan → SQL fidelity check" comment). Per-check breakdown produced as `FidelityReport.checks: List[FidelityCheck]`. Current checks:

- `table_referenced` — plan.table appears in the SQL
- `measure_formula:<kpi_id>` — each measure's catalog formula literally appears in the SQL
- `group_by_present` — SQL has GROUP BY when the plan has dims
- `dim_referenced:<col>` — each dim/time-bucket column appears
- `top_n_limit` + `top_n_order_by` — LIMIT and ORDER BY present when `plan.top_n` is set
- `share_of_total_denominator` — window SUM/OVER or subquery divide present
- `comparison_base_period`, `comparison_target_period`, `comparison_two_rows` — both periods + UNION present
- `contribution_delta_expr`, `contribution_period_ctes` — base/targ CTEs + delta column
- `filter_time_range:<...>`, `filter_metric_lt:<...>`, `filter_eq:<...>` — each plan filter rendered
- `rel_stat_agg_cte`, `rel_stat_entity`, `rel_stat_stat_op` — relative-to-stat shape
- `avg_at_grain_shape` — AVG of grouped SUM

`σ_fid` = `passed_checks / total_checks` (field `FidelityReport.score`). `ok = all(c.passed)`.

## 8. Result validator

Code: `backend/insightflow/reliability/result_validator.py`

- share_of_total: shares sum within 0.98–1.02 → warning if outside
- top_n: result row count ≤ N; values sorted DESC (TOP_N) or ASC (BOTTOM_N)
- comparison: exactly 2 rows, periods match plan.comparison.base_period/target_period
- contribution: non-empty rows + `delta` column present
- ratio KPI (unit=="ratio"): all values in [0, 1] → warning if outside
- Empty result on a non-filter question → warning (not error)

Errors drop fidelity to 0.0; warnings scale it as `max(0.4, 1.0 − 0.15·|warnings|)`.

## 9. Evidence record

Code: `backend/insightflow/reliability/evidence.py` + `backend/insightflow/orchestrator.py::_diagnostics`

Fields in each response:
- question, sql, kpi (headline KPI name)
- decision { action, reason }
- confidence { score, signals{sql_validity, schema_match, kpi_match, context_consistency, data_completeness, evidence_strength, result_consistency, intent_coverage, plan_fidelity} }
- plan_trace (full AnalyticalPlan as JSON)
- diagnostics { dataset, plan, plan_validation, sql, sql_validation, fidelity (per-check), execution, result_validation, kpi_validation, confidence, decision, failure_category }
- evidence { chain: [{step, value}], sample_rows[], row_count }
- notes[] (free-text annotations like dropped-compound-suffix)
- failure_category (NONE / AMBIGUITY / UNSUPPORTED_DATA / PLAN_SQL_FIDELITY_ERROR / RESULT_VALIDATION_ERROR / …)

## 10. MCP layer

Code: `backend/mcp_servers/*.py`, `backend/insightflow/mcp_integration/`, `backend/mcp_config.yaml`.

**MCP SDK version:** `mcp 2.3.0` (verified via `pip show mcp`).

**Four servers, 23 tools total:**

| Server | Tool count | Tools |
|---|---:|---|
| db | 7 | list_schemas, list_tables, describe_table, get_column_metadata, get_relationships, execute_readonly_query, get_data_freshness |
| analytics | 7 | calculate_kpi, compare_periods, analyze_trend, analyze_metric_breakdown, detect_anomalies, evaluate_forecast, get_business_metric_definition |
| data_quality | 6 | profile_table, check_missing_values, check_duplicate_records, validate_metric_definition, check_query_policy, get_data_quality_summary |
| reporting | 3 | generate_summary_report, export_query_results, generate_metric_report |

**Policy guard** (`backend/insightflow/mcp_integration/policy.py`):
- SQL verb allow-list `["select", "with"]`
- Deny-list of mutating keywords
- Single-statement enforcement
- Table-prefix allow-list from `mcp_config.yaml` (orders, customers, products, regions, dataset_, _datasets)
- Response-size cap (default 200_000 chars)
- Server-side guards remain active as defence in depth.

## 11. LLM path

Code: `backend/insightflow/llm.py`. Default provider `offline` (env `LLM_PROVIDER=offline`). When set to `openai` with `OPENAI_API_KEY`, an optional LLM-SQL path runs before the rule-based planner. **Off by default**; every test in this evidence pack runs the rule-based plan pipeline.
## 12. Demo database — live counts

Measured against the DB file `backend/data/insightflow.db` after `python data/seed.py`.

| table | row count |
|---|---:|
| orders | 2037 |
| regions | 4 |
| products | 12 |
| customers | 60 |
| _datasets | 1 |

- Date range (orders.order_date): **2026-01-01** to **2026-09-30**
- Distinct categories in products: **4**
- Rows in regions: **4**

### Column lists
- **orders**: order_id, customer_id, product_id, region_id, order_date, quantity, revenue, cost, discount
- **regions**: region_id, region_name
- **products**: product_id, product_name, category
- **customers**: customer_id, customer_name, region_id, segment

### How the July 2026 dip is engineered

3-Deterministic: uses random.Random(42). Generates ~220 orders per month for
4:Jan-Sep 2026, scaled by a monthly factor that engineers a clear revenue dip
5:in July 2026 concentrated in the East region and Furniture category.
6-
--
40-
41:# Monthly demand factor (2026). July engineered to drop — driven mostly
42-# by heavy targeted suppression of Furniture + East (see loop below).
--
44-    1: 1.00, 2: 0.95, 3: 1.05, 4: 1.10, 5: 1.15,
45:    6: 1.20, 7: 0.90,  # <-- flat July effect is mild; the targeted drops do the work
46-    8: 1.15, 9: 1.10,
--
112-
113:            # In July, extra-suppress Furniture and East region orders
114-            customer_id = rng.choice(customer_ids)

## 13. Legacy baseline (B0) availability

The pre-plan-pipeline rule-based generator still exists in-tree as the legacy fallback in `backend/insightflow/nlsql/generator.py` (used by `orchestrator._legacy_ask`). It is reachable today only when the active dataset is `demo` AND the plan comes back AMBIGUOUS — otherwise the plan-based path owns execution.

Historical git tags:
57ad7c7 Root-cause fix: uploads become real active datasets; NL→SQL is now schema-adaptive
c67ad59 Broaden safety: every question either answers correctly or clarifies
c8fec08 Fix over-confident wrong answers via intent extraction + coverage signal
5ee79e1 Add web product: FastAPI backend, Next.js landing + app, live realtime dashboard
