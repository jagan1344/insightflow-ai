# InsightFlow AI

**A confidence-aware, explainable, agentic AI platform for conversational business intelligence.**

Ask a natural-language business question — *"Why did revenue decrease in July?"* —
and InsightFlow will plan the query, generate SQL, validate it, execute it,
analyse the result (including root-cause contributor analysis for "why"
questions), assemble an **evidence chain**, score its own **confidence** on
seven signals, and then apply a decision policy — **Answer / Warn / Clarify /
Abstain** — instead of always answering. The core principle: *a fluent answer is
not necessarily a correct one*.

The whole system runs **fully offline with no API key** using SQLite plus a
deterministic rule-based NL-to-SQL path. An LLM (OpenAI or any
OpenAI-compatible endpoint like Ollama / vLLM / LM Studio) is optional and
pluggable.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Orchestrator                                │
│   question → generate → validate → execute → analyse → evidence →        │
│              confidence → decision → explain + recommend                 │
└─────────────────────────────────────────────────────────────────────────┘
      │            │            │           │           │           │
      ▼            ▼            ▼           ▼           ▼           ▼
   NL→SQL      SQL rules     Read-only    Root-cause  Evidence   7-signal
   (rule|LLM)  + schema      SQLAlchemy   contribs    chain      confidence
                             (row-cap)                            +policy

   Knowledge:  Schema introspection + KPI/business definitions (semantic layer)
```

Key modules:

| module | responsibility |
| --- | --- |
| `insightflow/nlsql/generator.py` | rule-based + optional LLM NL→SQL, out-of-scope detection |
| `insightflow/knowledge/kpi.py`   | KPI registry (revenue, orders, units, AOV, margin, discount rate) + synonyms |
| `insightflow/validation/`        | SQL syntax/safety and KPI business-rule checks |
| `insightflow/execution/`         | SQLAlchemy read-only executor, row-capped |
| `insightflow/analysis/`          | summary + diagnostic contributor analysis, chart-spec |
| `insightflow/reliability/`       | evidence chain, 7-signal confidence, decision policy |
| `insightflow/explain/`           | evidence-grounded explanation + recommendation |
| `insightflow/orchestrator.py`    | ties it all together, returns `InsightResponse` |

> The orchestrator is a dependency-free ~150-line module. You can swap it for
> **LangGraph** later without touching any other component.

---

## Quick start

```bash
# 1. venv + install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. seed the demo database (SQLite, deterministic, ~9 months of orders)
python data/seed.py

# 3. run the CLI demo — offline, no API keys
python run_demo.py

# 4. launch the Streamlit chat UI
streamlit run app.py
```

Then open http://localhost:8501.

---

## Try these questions

- `What is the total revenue?`
- `Show revenue by region`
- `What is the revenue by month?`
- `Why did revenue decrease in July?`   ← diagnostic; expect Furniture / East as root cause
- `What is the gross margin by category?`
- `Top products by revenue`
- `What is the average order value in August?`
- `What is the meaning of life?`        ← should **clarify**, not answer

---

## Enabling an LLM (optional)

Copy `.env.example` to `.env` and set one of:

```env
# Hosted OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini

# Any OpenAI-compatible local endpoint (Ollama, vLLM, LM Studio)
LLM_PROVIDER=local
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3
```

The LLM is used for narration and (optionally) NL→SQL. **The rule-based path
and validators still run** — anything the LLM produces is validated the same
way. If the LLM is unavailable, InsightFlow silently degrades to offline mode.

---

## Using PostgreSQL

Point `DATABASE_URL` at your database:

```env
DATABASE_URL=postgresql+psycopg2://readonly_user:pass@localhost:5432/insightflow
```

For production, run InsightFlow with a **read-only DB role**. The SQL
validator already forbids all mutating and DDL statements, but a read-only
role is defense-in-depth.

---

## Running tests

```bash
pytest -q
```

The tests verify:

1. Total-revenue question returns `ANSWER` with confidence ≥ 0.7.
2. "Why did revenue decrease in July?" identifies Furniture or East as the
   biggest negative contributor.
3. "What is the meaning of life?" returns `CLARIFY` (not `ANSWER`).
4. The SQL validator rejects `DROP TABLE`, `UPDATE`, and other non-SELECT
   statements.
5. `gross_margin` values fall within `[0,1]` and pass KPI validation.

---

## Docker

```bash
docker compose build
docker compose up
```

The image seeds the demo database at build time and serves the Streamlit UI
on port 8501. The `postgres` service is behind the `pg` profile —
`docker compose --profile pg up` starts it too.

---

## Design notes

- **Semantic layer first.** Every KPI is defined once in `insightflow/knowledge/kpi.py`
  with its SQL expression, unit, and business rules. Synonyms
  ("sales", "turnover", "aov", …) resolve to canonical KPIs. This is what
  makes answers business-correct rather than just SQL-correct.
- **Confidence is a vector, not a slogan.** Seven signals (`sql_validity`,
  `schema_match`, `kpi_match`, `context_consistency`, `data_completeness`,
  `evidence_strength`, `result_consistency`) are combined by weight — and
  out-of-scope questions are hard-capped at 0.30.
- **Decision policy, not just an answer.** Above 0.70 → **Answer**; between
  0.40 and 0.70 → **Warn** (or **Clarify** if ambiguous); below → **Abstain**.
  Execution failures always abstain.
- **Every answer is evidence-grounded.** The evidence chain
  (`question → SQL → KPI → filters → rows`) is surfaced in the UI so you can
  audit any claim.
