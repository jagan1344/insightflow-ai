# Architecture audit (start of the recovery mission)

Verified starting state: branch `claude/insightflow-ai-build-2neph7`, HEAD `c4c6087`, clean tree.
Frozen builds `38b60d1` (tree `00db6e2`) and `da925ad` (tree `d760e82`). Recomputed from saved runs:
R7 first run 14/74 correct, 7/105 wrong; R7 post-hoc 63/74, 2/105; R8 blind first run 5/73, 10/106.
Backend: 15,786 lines of Python under `backend/insightflow`.

## Execution path (question -> response), as implemented at `da925ad`
| concern | where | mechanism |
|---|---|---|
| follow-ups, safety | `conversation`, `safety` | regex rewrite / refusal |
| wording normalisation | `knowledge/vocabulary.py` | rule-based text rewrites |
| composites | `composite.py` | regex templates -> two sub-questions |
| entity / value resolution | `plan/planner.py::_value_index`, `_value_mentions`, `_classified_mentions` | substring search of distinct values over flattened dimension columns |
| metric identification | `planner._bind_kpis` + `kpi_catalog` aliases | longest alias substring wins; fallback `row_count` / `total_revenue` |
| term -> column | `_bind_dim_column`, `_find_dim_mentions`, alias tables | token / prefix similarity, regex cue words ("by", "per", "each", "which") |
| aggregation | KPI alias choice + `_detect_intent_kind` | keyword triggers ("average", "how many", "top", "monthly") |
| joins | `knowledge/relational.py`, `rel_context.py` | declared + inferred FKs; flattened "sources" per anchor |
| dates | `_bind_time_filter`, `_mentioned_date_col`, `_ambiguous_date_columns` | regex time phrases; date role by word stems; ambiguity -> execute all readings |
| Boolean / negation | `_find_flag_filters`, `_NEG_BEFORE`, `_find_null_state_filters` | windowed regex around matches |
| expressions | none as a structure | only catalog formulas (SUM/AVG/COUNT of one column) |
| SQL generation | `plan/compiler.py` | string assembly from an intent-kind-specific plan; literals inlined |
| semantic checks | `semantics/*`, `verification/intent_audit.py`, `reliability/mention_coverage.py` | post-hoc comparisons of wording with SQL |
| confidence | `reliability/confidence.py` | 9 weighted heuristics |
| decision | `reliability/decision.py` + vetoes in `orchestrator.py` | thresholds 0.70/0.40, vetoes cap 0.30 |

There is no explicit structure that records which phrase of the question was grounded to which schema element.
The plan (`AnalyticalPlan`) holds an intent kind, measures from a catalog, dimension names and filter records;
grounding evidence lives only implicitly in which regex fired.

## Confirmed failure causes (from traces; `stage_split.py`, `v6_wrong_sql_detail.txt`)
On the R8 blind set (73 answerable): the planner produced correct SQL for 9, wrong SQL for 40 (34 then refused,
6 answered), no SQL for 24. On R7 (frozen 38b60d1): correct SQL 20, wrong 32, none 22. The dominant failure is
the planner, not the vetoes; vetoes mostly refused wrong SQL.

Confirmed classes, each with at least one recorded trace:
1. **Keyword-triggered intents**: a time-unit word inside a column name ("monthly rent") triggers a trend and buckets
   a numeric column as a month (LS01, LS07, LS09; LS01 answered at confidence 1.0).
2. **Partial-token column matching**: "units" bound to `unit_cost` / `unit_wt_kg` (WH02, WH03, WH12, WH17);
   "average star rating customers give" -> COUNT (FD07).
3. **Spurious FK inference**: `orders.cust_rating -> customers` inferred from the prefix "cust" plus value
   containment of small integers (FD08 path ambiguity).
4. **Value-versus-word alternative**: an exact status value used as an adjective ("delivered orders") is treated as
   possibly ordinary wording and executed both ways -> clarification on 6 food questions (FD01, FD03, FD06, FD10, FD13, FD16).
5. **Role phrases not grounded**: "leasing agent", "property manager", "receiving location", "storage location" are
   not matched to role FK columns (LS06, LS07, WH05, WH06).
6. **Negation/null phrasing coverage**: "don't have a cuisine on file" (IS NOT NULL exclusion), "never got a courier
   assigned", "didn't use the SAVE10 promo" (FD02, FD14, FD09).
7. **No expression structure**: products ("quantity times unit cost", WH08 answered as two sums), percentages of
   rows with conditions on several columns, grouped shares, period comparisons (FD15, FD16, FD17, TC15, TC16, WH16-18).
8. **Abbreviated wording**: "avg tkt size", "sec dep", "XFERs", "custs", "mins" (FD08, LS08, WH09, TC18).
9. **Measure fallback**: when no measure binds, `row_count` / the first alias is used (FD07, WH13).
10. **Development overfitting**: R7-specific vocabulary rules raised R7 post-hoc to 63/74 and left R8 at 5/73.
11. **Confidence**: no discrimination on blind data (AUROC 0.45); vetoes, not the score, provide protection.

## Hypotheses (not yet confirmed)
- A grounding step that must account for every content word, with type-aware candidates and preserved
  ambiguity, will remove classes 1, 2, 4 and 9 without loosening safety.
- Typed expressions (CASE-filtered aggregates, products, ratios, window shares) will cover class 7.
- Strict FK inference (id-like child names only) removes class 3 without losing the role-playing joins.
- Latency will drop if grounding is a single pass over a cached schema model rather than repeated value-index
  scans and sub-question pipelines.
