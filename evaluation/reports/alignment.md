# BIRD → InsightFlow alignment (what carries over, what does not)

The single most useful framing of this evaluation:

> **BIRD** measures *"can the system produce the correct SQL?"*
> **InsightFlow** additionally measures *"does the system know when it's right,
> and does it abstain when it isn't?"*

BIRD supplies the standardised Text-to-SQL substrate, the Execution-Accuracy
metric, and the external-knowledge concept. InsightFlow's evaluated
contribution is the **reliability-to-decision layer** (7-signal confidence
→ Answer/Warn/Clarify/Abstain), tested for calibration and safe abstention.

## Legitimately adaptable from BIRD

| BIRD element | How InsightFlow reuses it |
|---|---|
| **Execution Accuracy (EX)** — result-set equality between predicted and gold SQL | Adopted verbatim as the SQL correctness metric on the InsightFlow Reliability Benchmark (project-generated). Set-equality via ordered `SELECT`s + multiset comparison, matching BIRD's rule (order-sensitive only when the query has `ORDER BY`). |
| **SQL Validity Rate** (implicit in BIRD, part of EX) | Reported separately here to isolate parser errors from wrong-but-parsable SQL. |
| **Difficulty tiers** — simple / moderate / challenging | Adopted for the reliability benchmark so results can be stratified the same way. |
| **Question taxonomy** — match-based, comparison, counting, aggregation, ranking, value-illustration, domain-knowledge | Used to structure the benchmark categories. |
| **External knowledge sentence** — a piece of domain knowledge grounding SQL | Conceptually maps to InsightFlow's **KPI / business semantic layer** (`insightflow/knowledge/kpi.py`). This mapping is a defensible connection; it is *not* a claim to reproduce BIRD's evidence format. |
| **Two-tier "with-KG" vs "without-KG" ablation** | Motivates one arm of InsightFlow's ablation (SQL-only vs SQL + schema/KPI vs Full). |

### Optional (with honesty flags)

- **VES (Valid Efficiency Score).** Only report if the benchmark actually times
  runs (100×, outlier drop). If not measured, do **not** invent a number — mark
  `NOT RUN`.
- **BIRD dev subset (external check).** A small dev subset (e.g. 100–200
  questions) can serve as an external Text-to-SQL sanity check, provided:
  - the SQLite DB and gold SQL can be downloaded, AND
  - InsightFlow's **LLM NL→SQL path** is available (an API key, or a local
    OpenAI-compatible endpoint). InsightFlow's rule-based generator is
    tuned to the demo business schema and will not translate general
    BIRD-domain queries.
  - Otherwise: mark BIRD external evaluation `NOT RUN`, state the reason,
    and rely on the reliability benchmark alone.

## What must NOT be claimed

- ❌ **"InsightFlow reproduces BIRD."** It does not. This work does not run
  the full 12,751-question benchmark and does not compete on the BIRD
  leaderboard.
- ❌ **"InsightFlow beats GPT-4 / DIN-SQL on Text-to-SQL."** BIRD's test set
  is hidden and InsightFlow was not tuned for it. At most, a dev-subset
  number can be reported *if it is actually run*.
- ❌ **"InsightFlow is a Text-to-SQL SOTA system."** The rule-based generator
  targets the project's demo business schema. Any cross-domain claim
  requires the LLM path, and its performance is bounded by the underlying
  model — not by InsightFlow's design contribution.
- ❌ **Reliability/decision comparison with BIRD.** BIRD has no
  confidence, no abstention, and no decision-policy metric. Those are
  evaluated **on the InsightFlow Reliability Benchmark**, not "vs BIRD".

## What InsightFlow *does* evaluate (and BIRD does not)

Measured on the InsightFlow Reliability Benchmark (§4a of the plan):

- **Business-answer correctness** on KPI-grounded questions.
- **Confidence calibration** — reliability curve, ECE, Brier.
- **Decision quality** — Answer / Warn / Clarify / Abstain rates and
  correctness against a ground-truth decision label.
- **High-confidence error rate** — the rate of confidently-wrong answers,
  i.e. the safety-critical quantity for BI.
- **Reliability-layer ablation** — SQL-only vs SQL + schema/KPI vs Full
  seven-signal, to test whether the extra signals earn their place.

Whether they earn their place is what the experiment decides; this document
does not assume they do.
