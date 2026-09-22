# Base-paper comparison — BIRD vs InsightFlow AI

*Grounded in `basepaper_analysis.md` and `alignment.md`. All InsightFlow
numbers are [Measured] on the InsightFlow Reliability Benchmark
(n=27) — see `evaluation/results/`. All BIRD numbers are
[Base-Paper] and copied from the published paper.*

| Aspect | Base paper (BIRD) | InsightFlow AI | Similarity | Difference |
|---|---|---|---|---|
| **Problem** | Text-to-SQL for large enterprise DBs. | Confidence-aware conversational BI: NL question → SQL → analysis → **evidence + decision policy**. | Both start from NL → SQL. | InsightFlow adds analysis, evidence chain, confidence, and Answer/Warn/Clarify/Abstain policy — BIRD stops at SQL. |
| **Dataset** | 12,751 pairs, 95 DBs, 33.4 GB, 37 domains. Public. | InsightFlow Reliability Benchmark: 27 questions on one demo DB, project-generated, **evaluation-only**. | Both use gold SQL + result-set truth. | InsightFlow benchmark is small, single-domain, and adds ambiguous / out-of-scope / diagnostic categories that BIRD does not cover. |
| **Architecture** | LLM (or fine-tuned T5) → SQL. | Rule-based OR LLM NL→SQL, then schema/KPI validation, execution, contributor analysis, seven-signal reliability, decision policy, explanation, recommendation. | Both split "generate" from "execute". | InsightFlow is an agentic pipeline; BIRD's benchmark evaluates only the generator. |
| **SQL generation** | Prompted LLMs (Codex, ChatGPT, GPT-4, Claude-2, PaLM-2) + T5 fine-tuning. | Deterministic rule-based parser (default/offline) that recognises KPIs, dimensions, months, top/bottom, diagnostic intent; optional LLM path with same validation. | Both target executable SQL. | InsightFlow's rule path is domain-specific to the demo schema — it does not generalise across BIRD's 95 DBs. Any cross-domain use of InsightFlow requires the LLM path. |
| **Validation** | None (evaluated only by EX / VES). | SQL validator (single SELECT, no DDL/mutations, schema-aware) + KPI validator (non-negative, [0,1] ratio). | — | InsightFlow validates BEFORE it answers; BIRD does not. |
| **Business semantics** | None in the benchmark. | KPI semantic layer (`insightflow/knowledge/kpi.py`) with SQL expression, unit, business rules and synonym resolution. | BIRD's "external knowledge sentence" is conceptually analogous. | InsightFlow's semantics are structured (KPI registry), not free-text; they are also used at runtime, not just as evaluation help. |
| **Confidence** | Not defined. | 7-signal weighted score, hard-capped at 0.30 for out-of-scope. | — | This is the primary axis on which InsightFlow is evaluated; BIRD has no metric for it. |
| **Evidence** | External-knowledge sentence per question. | Provenance chain per answer (question → SQL → KPI def → filters → row-count → sample rows). | Both use domain knowledge to justify SQL. | InsightFlow builds a runtime, per-answer evidence chain rendered in the UI; BIRD's evidence is a static annotation aid. |
| **Abstention** | Not part of the benchmark. | Explicit Answer / Warn / Clarify / Abstain decision policy driven by confidence and out-of-scope detection. | — | BIRD assumes the system always answers; InsightFlow is judged on when it does *not*. |
| **Explainability** | Not evaluated. | Evidence chain + optional LLM narration + recommendation (diagnostic only). | — | Explainability is a shipped feature and is inspected in the qualitative decision analysis. |
| **Evaluation** | EX + VES on 12,751 questions, 3 splits. | EX (BIRD-style set equality) + KPI match + evidence support + calibration (ECE, Brier) + decision correctness + high-confidence error rate + reliability-layer ablation, on 27 questions, evaluation-only. | Both use result-set-equality EX. | Different scale, different scope, and InsightFlow adds reliability and decision metrics BIRD does not have. |
| **Metrics reported here** | EX (test) up to **55.90 %** (DIN-SQL+GPT-4); GPT-4 alone 54.89 %; human 92.96 % — all [Base-Paper] on BIRD test. | EX = **94.1 %** on the reliability benchmark's 17 SQL-scored items [Measured]. | Both are result-set EX. | **The numbers are not comparable.** BIRD is 12,751 questions across 95 unfamiliar databases; InsightFlow's 27-question benchmark is on a single demo DB the rule generator was designed for. No claim of superiority follows from the raw numbers. |

## What the comparison actually says

- BIRD tests **whether the system can produce correct SQL** across many
  unfamiliar databases. That is not what this evaluation measures.
- This evaluation tests **whether the system knows when it is right and
  abstains when it isn't**, on a benchmark that spans answerable /
  ambiguous / out-of-scope / diagnostic questions. BIRD does not measure
  these.
- The BIRD numbers here are context, not a target. See `alignment.md` for
  the honest framing and `research_evaluation.md` for the measured
  InsightFlow results.
