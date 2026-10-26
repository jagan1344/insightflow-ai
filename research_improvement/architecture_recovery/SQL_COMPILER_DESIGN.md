# SQL compiler and execution

Code: `backend/insightflow/engine/compiler.py`, `backend/insightflow/engine/engine.py`.

## Guarantees

| Property | How |
|---|---|
| Read-only | executed on `sqlite3.connect("file:...?mode=ro", uri=True)`; only SELECT is ever generated |
| No injection through values | every literal is a `?` parameter; the display SQL is produced separately by `inline()` |
| No injection through names | identifiers come from the schema model only; `_qi` rejects quotes and NUL; unknown columns fail before SQL |
| No fan-out | many-to-one steps are LEFT JOINs along the recorded path, one alias per (path prefix); one-to-many steps appear only inside `EXISTS (SELECT 1 …)` subqueries; a fan-out column outside EXISTS is refused by the verifier and again by the compiler (`_up_alias` raises on a down step) |
| Division safety | `a / b` compiles to `((a) * 1.0 / NULLIF((b), 0))` |
| Conditional aggregates | `AGG(CASE WHEN pred THEN arg END)` (COUNT uses `THEN 1`) |
| Share of total | `(e) * 100.0 / NULLIF(SUM(e) OVER (), 0)`; `e` is regenerated so its parameters stay in order |
| Time buckets | substr on ISO text (month, year, day, quarter) or strftime (week) |
| Ranking | `ORDER BY <measure> DESC/ASC LIMIT ?` |
| Timeouts | a progress handler aborts statements after `timeout_s` (default from `settings.query_timeout_s`) |
| Row cap | `fetchmany(max_rows + 1)`; truncation is reported |

## Evidence chain (per answer)

`EngineResult.trace()` gives the status and message; the display SQL (with parameters inlined for reading); the
per-span evidence; assumptions, ambiguities, unresolved and unsupported items; and the reliability components.

The orchestrator adds this, together with `sql_params` and latency, to `InsightResponse.diagnostics` and
`plan_trace`.

## Decision and reliability (orchestrator `_typed_engine_response`)

The decision follows hard rules, with no tuned threshold:
- **CLARIFY** if anything is unsupported, ambiguous or unresolved, if verification fails, or on an internal error. The
  message names the specific problem.
- **WARN** if the plan executed but rests on stated assumptions (summing without an aggregation word, an inferred join,
  an empty result, the treatment of missing values in a difference).
- **ANSWER** otherwise: every word grounded, the plan verified, the query executed.

The reliability components are reported separately:
- grounding complete/incomplete;
- number of ambiguities and unresolved items;
- plan violations;
- executed;
- empty result;
- number of assumptions;
- whether a join was inferred.

They are explicitly labelled *not a calibrated probability*. `Confidence.score` is a coarse ordinal level (0.9 /
0.6 / 0.0) kept for API compatibility, and its signals carry `uncalibrated = 1`. No threshold was tuned on any
evaluation set.
