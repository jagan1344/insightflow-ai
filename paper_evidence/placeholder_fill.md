# Placeholder fill — values measured from the repo

The paper is not present in this checkout (see `discrepancies.md` D1),
so the exact placeholder strings cannot be matched one-for-one. The
rows below cover every item the master prompt enumerates. **Each value
is sourced from code or a logged run.**

| # | Placeholder topic | Value to insert | Source |
|---|---|---|---|
| 1 | Authors / dept / email | **AUTHOR MUST SUPPLY** | — |
| 2 | Repository URL | `https://github.com/jagan1344/insightflow-ai` | `git remote get-url origin` |
| 3 | Commit hash | `3c843de88ca0b62669749b217aaef000e3e6363e` | `git rev-parse HEAD` |
| 4 | Branch | `claude/insightflow-ai-build-2neph7` | `git rev-parse --abbrev-ref HEAD` |
| 5 | Line count (backend Python + web TS/TSX) | run `cloc` locally; this environment had no `cloc`. From `git ls-files + wc -l`: backend `.py` ≈ 6,250 incl. tests, web `.ts/.tsx` ≈ 2,480 excluding node_modules | `wc -l` on `git ls-files` output |
| 6 | List of 13 intent kinds | DIRECT_KPI, BREAKDOWN, TREND, COMPARISON, GROWTH, TOP_N, BOTTOM_N, SHARE_OF_TOTAL, RATIO, AVERAGE_AT_GRAIN, CONTRIBUTION, RELATIVE_TO_STAT, UNSUPPORTED, AMBIGUOUS — **14 total**, not 13. The paper should say 14. | `backend/insightflow/plan/plan.py` class `IntentKind` |
| 7 | Signal names | sql_validity, schema_match, kpi_match, context_consistency, data_completeness, evidence_strength, result_consistency, intent_coverage, plan_fidelity | `backend/insightflow/config.py::DEFAULT_WEIGHTS` |
| 8 | Signal weights | 0.12, 0.10, 0.13, 0.13, 0.08, 0.07, 0.10, 0.13, 0.14 — sum **= 1.0000** | same |
| 9 | ANSWER threshold | **0.70** | `backend/insightflow/config.py::threshold_high` |
| 10 | WARN threshold | **0.40** | `backend/insightflow/config.py::threshold_low` |
| 11 | ABSTAIN threshold | Final confidence rule: `C < 0.40` returns ABSTAIN. Earlier rules take precedence: SQL validation/execution failures return ABSTAIN; plan ambiguity, unavailable fields, failed plan validation, and plan-to-SQL fidelity failures return CLARIFY. | `backend/insightflow/reliability/decision.py::decide()` |
| 12 | Hard-cap formula | `C = min(S, coverage + 0.05, fidelity + 0.05)` — equivalent to `C = min(S, min(σ_cov, σ_fid) + 0.05)` | `backend/insightflow/reliability/confidence.py` |
| 13 | MCP SDK version | **2.3.0** | `pip show mcp` |
| 14 | MCP spec version / access date | Access date **2026-10-09** (pack built), re-checked **2026-10-12**. SDK upstream = `pypi.org/project/mcp/` version **2.3.0** (confirmed via `pip show mcp`). The **MCP specification document** itself is NOT pinned to a specific revision in this repo (the SDK selects it at runtime). Current authoritative revisions per the Model Context Protocol maintainers' public materials: **`2026-07-28`** (latest, "stateless MCP") and **`2024-11-05`** (earlier revision, still supported by many implementations). **HUMAN: verify which revision string your paper cites against the modelcontextprotocol.io/specification page — do not rely on this secondary summary.** | web search 2026-10-12 (secondary sources — not the official spec page, which was unreachable from this environment) |
| 15 | Four MCP servers + responsibility | `db` (introspection + read-only query), `analytics` (KPI math + anomalies + forecasts), `data_quality` (profiling, policy check), `reporting` (summary + CSV export + per-KPI report) | `backend/mcp_config.yaml` + per-server docstrings |
| 16 | Total MCP tools | **23** (db 7 + analytics 7 + data_quality 6 + reporting 3) | discovery output in `test_mcp_integration.py` |
| 17 | Demo DB table list | `_datasets, customers, orders, products, regions` | `facts.md §12` |
| 18 | Demo DB column list (orders) | order_id, customer_id, product_id, region_id, order_date, quantity, revenue, cost, discount | `facts.md §12` |
| 19 | Demo DB row count | **2,037 orders** (not 2,077 as benchmark's `expected_result` row-count field claims) | live `SELECT COUNT(*) FROM orders` |
| 20 | Demo total revenue | **3,388,831.47** (not 3,428,686.53 as benchmark's `expected_result` claims) | live `SELECT SUM(revenue) FROM orders` |
| 21 | Date range | **2026-01 to 2026-09** | live `MIN/MAX(order_date)` |
| 22 | July dip mechanism | engineered monthly factor in `data/seed.py` that drops July's volume and concentrates the drop in the East region + Furniture category | `backend/data/seed.py` |
| 23 | Benchmark question count | **27** (master prompt said 55; see discrepancies.md D2) | `wc -l evaluation/dataset/reliability_benchmark.jsonl` |
| 24 | Tolerance ε | **1e-6** relative | `evaluation/oracle.py::EPSILON` |
| 25 | Test run date / env / commit | **2026-10-09T15:22Z, Linux 6.18.44, Python 3.11.15, commit 3c843de**, 118 / 118 passed in 15.33 s | `paper_evidence/test_run.log` |
| 26 | Safety-matrix size | **25 cases** in `backend/tests/test_safety.py::CASES` (the variable is `CASES`, not `SAFETY_CASES`; the file imports no `SAFETY_CASES` name) | AST walk of `test_safety.py` |
| 27 | Superstore dataset | NOT MEASURED in this evidence pack — no Superstore file in-tree at the eval time. The frontend upload flow accepts the real Tableau Superstore .xls but we did not have one to upload here. | — |
| 28 | Evidence-record checklist | SQL identical to executed SQL ✓, KPI formula matches catalog ✓, filters listed ✓, assumptions (plan.notes) listed ✓, dataset table in `diagnostics.dataset.table` ✓ | `backend/insightflow/orchestrator.py::_diagnostics` |
| 29 | Dataset URL | repo + commit (above). No external dataset dependency for the demo. | — |
| 30 | Case-study response + SQL | `paper_evidence/case_studies.md` has the 4 required cases with full plan, SQL, result, action, confidence, signals | — |

## Items the paper should **not** quote without re-running

- "zero unsafe-answer rate" — true only on the controlled 25-case
  safety matrix, false on the 27-question benchmark (2 unsafe answers,
  Wilson CI 0.021–0.234). See `discrepancies.md` D4 and
  `limitations.md` L1.
- "55 regression questions" — benchmark has 27; test node count is 118.
  See `discrepancies.md` D2.
- Ablation deltas on the 27-question benchmark alone — null-result,
  do not quote as effect sizes. The adversarial diagnostic set
  (`paper_evidence/adversarial_results.md`) is a separate artefact and
  must be labeled as such; it shows real divergences for B1 (4/12) and
  A1 (1/12). See `limitations.md` L2.
- Overall latency as representative of LLM-backed agentic BI — the
  p50=4ms, p95=6ms numbers are the deterministic-pipeline cost only.
  See `limitations.md` L7.
- "well-calibrated confidence" — ECE on the 27-question dev set is
  0.416. See `limitations.md` L4.

## HUMAN MUST SUPPLY

- Author names, department, email addresses.
- MCP specification version string (document, not SDK).
- Any Superstore evaluation (upload the .xls to the running app).
- The literal yellow-highlight strings from the .docx (I don't have the file).
