# Phase 3 — Shared semantic architecture

## Shared representation

The `AnalyticalPlan` IR (`backend/insightflow/plan/plan.py`) is the
single source of truth for every intent in the pipeline. All layers
(planner, compiler, validators, decision policy, explainer) consume
the same dataclass; no layer re-interprets the raw question.

Fields the IR carries end-to-end:

| Field | Captures |
|---|---|
| `intent_kind` | one of 21 enumerated intents (DIRECT_KPI, BREAKDOWN, TREND, COMPARISON, GROWTH, TOP_N, BOTTOM_N, SHARE_OF_TOTAL, RATIO, AVERAGE_AT_GRAIN, CONTRIBUTION, RELATIVE_TO_STAT, EXTREMUM, DISTINCT_COUNT, NULL_COUNT, ROLLING_AVG, TOP_N_PER_GROUP, THRESHOLD_GROUPED, POST_AGG_STAT, UNSUPPORTED, AMBIGUOUS) |
| `measures: list[MeasureRef]` | KPI id, display name, formula, aggregation, unit |
| `dims: list[DimRef]` | grouping dimensions (physical column + time grain) |
| `filters: list[FilterExpr]` | typed filters: `eq`, `in`, `range`, `time_range`, `metric_lt`, `metric_gt`, `null`, `not_null`, `metric_(gt\|lt)_grouped` |
| `grain: Optional[Grain]` | time-grain spec (unit + column) |
| `comparison`, `contribution`, `relative_stat` | typed specs for the respective intents |
| `top_n: Optional[int]` | ranking limit (interpreted as per-partition for TOP_N_PER_GROUP) |
| `share_of_total: bool` | share-of-total flag |
| `order_by`, `unavailable`, `notes`, `question`, `table` | preservation of user intent + planner audit trail |

## Pipeline contract

`Interpret → Validate → Plan → Execute → Transform → Verify → Decide → Render.`

| Stage | Code location | Function |
|---|---|---|
| Interpret / Validate | `insightflow/safety/*` | destructive, forecast, capability-unsupported pre-gates (BEFORE SQL) |
| Follow-up resolve (Phase 5) | `insightflow/conversation/__init__.py` | rewrite references against last anchor |
| Plan | `insightflow/plan/planner.py::Planner.plan` | NL → AnalyticalPlan |
| Plan validate | `insightflow/plan/validator.py::PlanValidator.validate` | semantic plan-level checks |
| Compile | `insightflow/plan/compiler.py::SQLCompiler.compile` | plan → SQLite SQL |
| Fidelity | `insightflow/plan/fidelity.py::FidelityValidator.check` | plan ↔ SQL static alignment |
| SQL validate | `insightflow/validation/sql_validator.py::validate_sql` | structural + read-only enforcement |
| Dialect validate | `insightflow/validation/dialect_validator.py::validate_dialect` | reject Postgres/MSSQL/MySQL idioms |
| Execute | `insightflow/execution/executor.py::run_sql` | SQLAlchemy, row-capped |
| Transform (Phase 4) | `insightflow/orchestrator.py` + `insightflow/analysis/stats.py` | post-aggregation stats (median / percentile / stddev / variance) |
| Result validate | `insightflow/reliability/result_validator.py::ResultValidator.check` | post-exec shape checks |
| Semantic fulfilment | `insightflow/validation/semantic_fulfilment.py::validate_fulfilment` | result ↔ plan intent check |
| KPI validate | `insightflow/validation/kpi_validator.py::validate_kpi` | ratio bounds, non-negativity |
| Confidence | `insightflow/reliability/confidence.py::score_confidence` | 9 signals |
| Decide | `insightflow/reliability/decision.py::decide` | ANSWER / WARN / CLARIFY / ABSTAIN |
| Explain | `insightflow/explain/explainer.py::explain` | guards against forecast phrasing on non-forecast intents |

## Enforced invariants

1. **No stage can silently undo an earlier guarantee.** Pre-gates run
   BEFORE SQL generation. Dialect, fidelity, result, fulfilment
   validators run BEFORE decision. Each stage reports structured
   results that the decision layer reads.
2. **Semantic failure overrides numerical confidence.** A failed
   fidelity / fulfilment / dialect check demotes a would-be ANSWER to
   WARN (score ≥ 0.4) or CLARIFY (score < 0.4), independent of
   `confidence.score`.
3. **Successful SQL execution is not proof of correctness.** Semantic
   fulfilment compares the executed shape to the plan: trend-single-row
   is flagged; comparison with wrong period count is flagged; direct-kpi
   with all-NULL result on a time filter is flagged.
4. **No stage interpolates user text into SQL.** The compiler only
   references catalog KPI formulas + dataset-introspected columns.
   Literal values are routed through `_sql_escape`.

## Tests

- `backend/tests/test_defect_fixes.py` — the original 7 defects (date
  range, relative periods, forecast, diagnostic, destructive, intent
  coverage, multi-metric).
- `backend/tests/test_system_wide_repair.py` — dialect + fulfilment +
  LLM-path hardening + explanation safety.
- `backend/tests/test_capability_gate_invariants.py` — capability
  gate refusal AND oracle-matched implementations (including Phase 4
  stats).
- `backend/tests/test_followup_resolver.py` — Phase 5 conversation
  rewrites.

## Acceptance

A request whose required operation, filter, date range, dimension, or
result shape has been silently lost cannot reach ANSWER:
- intent-missing → capability gate → CLARIFY
- compiled SQL ≠ plan → fidelity validator → WARN/CLARIFY
- SQL wrong dialect → dialect validator → ABSTAIN
- SQL executes but result shape ≠ plan → fulfilment validator →
  WARN/CLARIFY
- relative period resolved to empty data → orchestrator override →
  CLARIFY
