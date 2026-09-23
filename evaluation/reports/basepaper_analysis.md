# Base paper analysis — BIRD

> **Paper.** Li et al., *Can LLM Already Serve as a Database Interface? A BIg Bench
> for Large-Scale Database Grounded Text-to-SQLs* (BIRD). NeurIPS 2023 Datasets &
> Benchmarks. arXiv:2305.03111. Leaderboard `bird-bench.github.io`.
> Data licence: CC BY-NC 4.0 (non-commercial — fine for academic evaluation).

This document is the extracted analysis I work from. Every claim about BIRD in
the rest of this evaluation traces back here.

## 1. Problem

Text-to-SQL — convert a natural-language question + a database into an
executable SQL query that returns the requested information.

## 2. Research gap addressed

Prior benchmarks (Spider, WikiSQL) emphasise database *schema* with only a
handful of database values and clean synthetic data. They ignore three
realities of enterprise data work:

- large, "dirty" real database values,
- the need to ground SQL in external / domain knowledge, and
- execution efficiency of the produced SQL.

BIRD calls this the "academia-vs-real-world" gap.

## 3. Dataset

- **BIRD** — 12,751 natural-language ↔ SQL pairs.
- **95 databases** totalling **33.4 GB** across **37 professional domains**
  (blockchain, healthcare, sport, ...).
- Every pair carries an **external-knowledge "evidence" sentence** in addition
  to the DB schema; every database ships with a description CSV file.

## 4. Size / splits

| Split | Questions | Databases |
|---|---:|---:|
| train | 9,428 | 69 |
| dev   | 1,534 | 11 |
| hidden test | 1,789 | 15 |

- Avg **7.3 tables per DB**, ~**549 K rows per DB**.
- Difficulty tiers: **simple 30 %**, **moderate 60 %**, **challenging 10 %**.

## 5. Dataset structure (per question)

- `question` (NL)
- `external knowledge evidence` sentence
- `db_id` + the database itself
- database description CSV
- `gold SQL`
- (dev/test may lack public gold)

**Question taxonomy.**

- **Fundamental** — match-based 83.9 %, ranking 20.3 %, comparison 16.7 %,
  counting 30.4 %, aggregation 15.7 %.
- **Reasoning** — value-illustration 70.1 %, numeric 24.5 %,
  domain-knowledge 23.6 %, synonym 7.2 %.

(Categories overlap by design; percentages are per-tag, not a partition.)

## 6. Experimental setup

BIRD studies two paradigms:

- **Fine-tuning** — T5-Base, T5-Large, T5-3B on train.
- **In-context learning** — zero-shot, temperature 0.
- Each is run **with and without the external knowledge sentence**
  ("Knowledge Grounded" vs "without KG").

## 7. Baselines

- T5-Base / T5-Large / T5-3B (fine-tuned).
- Prompted LLMs: **Codex**, **ChatGPT (gpt-3.5-turbo)**, ChatGPT + CoT,
  Claude-2, PaLM-2, **GPT-4 (gpt-4-32k)**.
- **DIN-SQL + GPT-4** (state of the art at time of publication).

## 8. Evaluation metrics

- **Execution Accuracy (EX)** — fraction of predictions whose result set on the
  DB matches the gold SQL's result set. Comparison is **order-insensitive**
  (multiset equality) except when the query contains explicit `ORDER BY`.
- **Valid Efficiency Score (VES)** — EX weighted by relative runtime
  efficiency of the predicted SQL vs the gold SQL. Each query is timed 100×,
  outliers dropped, ratio taken as √(gold_time / pred_time) capped ≥ 0 and
  multiplied by 0/1 correctness.

## 9. Test methodology

- Execute predicted SQL and gold SQL against the same SQLite DB, compare
  result sets → EX.
- Time the same execution 100× → VES.

## 10. Headline results

Reported by the paper (test split unless stated). BIRD is deliberately hard.

| System | EX (dev, w/ knowledge) | EX (test, w/ knowledge) |
|---|---:|---:|
| Human performance | — | **92.96 %** |
| DIN-SQL + GPT-4   | 50.72 % | **55.90 %** |
| GPT-4 (gpt-4-32k) | **46.35 %** | 54.89 % |
| Claude-2          | 42.70 % | 49.02 % |
| ChatGPT + CoT     | 36.64 % | 40.08 % |
| ChatGPT           | 37.22 % | 39.30 % |
| T5-3B (fine-tuned)| 23.34 % | 24.05 % |

- External knowledge sentences add roughly **+10 to +20 EX points** across
  models — the paper's central quantitative finding.
- VES orderings track EX orderings.

## 11. Ablation / analysis

- **Knowledge-grounded vs not** (every model, both splits).
- **Difficulty stratification** — EX per simple / moderate / challenging.
- **Fine-grained category analysis** — EX per question-taxonomy tag.
- **Two-stage efficiency optimisation** — ~ **77.75 %** execution time saved
  on generated SQL by post-processing.
- **"Chat-with-Database"** case study.

## 12. Error analysis

Sample of **500 ChatGPT errors**:

| Bucket | Share |
|---|---:|
| Wrong Schema Linking | **41.6 %** |
| Misunderstanding DB Content | **40.8 %** |
| Misunderstanding Knowledge Evidence | **17.6 %** |
| Syntax Error | **3.0 %** |

Schema linking + database-value understanding dominate.

## 13. Limitations

- Annotation is expensive; the paper is explicit that scaling annotation
  further is the main cost.
- Benchmark ships as **SQLite** only — the authors note that exact query plans
  are hard to get in SQLite and PostgreSQL / MySQL variants are future work.

## 14. Contribution (author-stated)

The first **large-scale, cross-domain, big-database** Text-to-SQL benchmark
centred on:

1. large, real database **values** (not only schema),
2. **external knowledge grounding**, and
3. execution **efficiency** (VES),

together with a **human-performance baseline** for calibration.
