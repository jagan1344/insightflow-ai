# InsightFlow AI

**A confidence-aware, explainable, agentic AI platform for conversational business
intelligence — with real-time auto-updating dashboards.**

Ask a business question in natural language and the system plans the query, generates
SQL, validates it against a KPI/business semantic layer, executes it read-only,
analyses the result (with root-cause contributor analysis for "why" questions), builds
an evidence chain, scores its own confidence across seven signals, and applies a
decision policy — **Answer / Warn / Clarify / Abstain** — so it can refuse rather than
fluently mislead. Meanwhile the Live Dashboard subscribes to a WebSocket and
**animates its charts in place whenever the underlying data changes — no page refresh.**

Runs **fully offline with no API key** using SQLite + a deterministic rule-based
NL→SQL path. An OpenAI-compatible LLM (hosted or local) and PostgreSQL are optional
upgrades.

---

## Architecture

```
Browser ── Next.js 14 (landing + app)
   │  REST   /api/ask, /api/dashboard, /api/seed, /api/simulate
   │  WS     /ws   ← pushes dashboard updates when data changes
   ▼
FastAPI backend
   ├── insightflow/         confidence-aware agentic pipeline
   ├── api/realtime.py      change watcher + WebSocket broadcaster + simulator
   └── SQLAlchemy → SQLite (default) | PostgreSQL (DATABASE_URL)
```

### Monorepo layout

```
insightflow-ai/
├── backend/
│   ├── insightflow/                # the pipeline (config, llm, knowledge/, nlsql/,
│   │                                #   validation/, execution/, analysis/, reliability/,
│   │                                #   explain/, memory, orchestrator)
│   ├── api/
│   │   ├── main.py                 # FastAPI app + WebSocket
│   │   ├── schemas.py              # pydantic models
│   │   ├── routes_chat.py          # POST /api/ask
│   │   ├── routes_dashboard.py     # /api/dashboard, /api/seed, /api/simulate
│   │   └── realtime.py             # watcher + broadcaster + simulator
│   ├── data/
│   │   ├── schema.sql
│   │   ├── seed.py                 # deterministic seed (July revenue dip)
│   │   └── simulate_stream.py      # standalone live-data generator
│   ├── tests/test_pipeline.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── web/                            # Next.js 14 (App Router) + TypeScript + Tailwind
│   ├── app/                        # / (landing) + /app (chat + live dashboard)
│   ├── components/
│   │   ├── landing/                # Navbar Hero TrustStrip Features HowItWorks
│   │   │                            #   DashboardPreview CTA Footer
│   │   ├── chat/                   # ChatPanel Message DecisionBadge ConfidenceBars
│   │   │                            #   EvidenceChain ChartInline
│   │   ├── dashboard/              # Dashboard KpiCard RevenueTrend RegionBar
│   │   │                            #   CategoryDonut MarginBar LiveIndicator
│   │   └── ui/                     # Button Card Badge Tabs Skeleton Logo
│   ├── lib/                        # api.ts, useDashboardSocket.ts, types.ts, format.ts
│   ├── package.json, tailwind.config.ts, tsconfig.json, next.config.js
│   └── Dockerfile
├── docker-compose.yml              # backend (8000) + web (3000) [+ optional postgres]
└── README.md
```

---

## Quick start (local dev)

Two terminals — no API keys, no third-party services.

```bash
# 1) Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python data/seed.py
uvicorn api.main:app --reload --port 8000

# 2) Frontend (new terminal)
cd web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) for the landing page and
[http://localhost:3000/app](http://localhost:3000/app) for the chat + dashboard.

### Prove real-time is working

- In the app, click **"Simulate live data"**. The KPI cards, revenue trend, region
  bar, category donut and margin chart update every few seconds while you watch — the
  **Live** pill pulses next to the buttons.
- Or, in a third terminal, run the standalone streamer:

```bash
cd backend && source .venv/bin/activate
python data/simulate_stream.py --rate 2 --batch 3
```

The dashboard, which is subscribed to `/ws`, animates in place with no reload.

### Run the tests

```bash
cd backend && source .venv/bin/activate
pytest -q
```

The 8 tests cover: total revenue happy-path, July diagnostic root-cause,
out-of-scope clarify, SQL validator rejects mutations, gross-margin ratio bounds,
`/api/dashboard` payload shape, the `POST /api/ask` HTTP surface, and the realtime
watcher broadcasting a `dashboard_update` after an INSERT.

---

## Docker

```bash
docker compose build
docker compose up
```

Backend on `http://localhost:8000`, web on `http://localhost:3000`. The web
container proxies `/api/*` and `/ws` to the backend inside the Docker network. To
enable the optional Postgres service:

```bash
docker compose --profile pg up
```

Then set the backend's `DATABASE_URL` env var
(`postgresql+psycopg2://insightflow:insightflow@postgres:5432/insightflow`) — for
production also use a **read-only DB role** as defence-in-depth alongside the
built-in SQL validator.

---

## Enabling an LLM (optional)

Copy `backend/.env.example` to `backend/.env` and set one of:

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

The LLM is used for narration and, optionally, NL→SQL. **All output still passes
through the same validators.** If the LLM is unavailable, InsightFlow silently
degrades to offline mode.

---

## How the real-time mechanism works

`api/realtime.py` runs a lightweight `asyncio` task inside FastAPI that polls a
cheap **data signature** on `orders` every ~2 seconds:

```sql
SELECT COUNT(*), COALESCE(MAX(order_id),0), ROUND(COALESCE(SUM(revenue),0), 2) FROM orders
```

When the signature changes it bumps a version counter, recomputes the dashboard
payload, and broadcasts `{ "type": "dashboard_update", "version": N, "data": {...} }`
to every WebSocket client. The frontend's `useDashboardSocket()` hook connects to
`/ws`, receives the initial snapshot on connect, then patches state on each update.
Recharts' `isAnimationActive` transitions each chart smoothly to the new values.

Polling works portably for SQLite and PostgreSQL. For sub-second push in
production, upgrade to **PostgreSQL `LISTEN/NOTIFY`** via an `AFTER INSERT` trigger
on `orders`, or **SQLite update hooks**, and broadcast on the notification rather
than the poll.

---

## Design notes

- **Semantic layer first.** Every KPI (revenue, orders, units, AOV, margin,
  discount rate) is defined once in `insightflow/knowledge/kpi.py` with its SQL
  expression, unit, and business rules. Synonyms map "sales", "aov",
  "profitability" etc. to canonical KPIs. This is what makes answers
  business-correct rather than only SQL-correct.
- **Confidence is a vector, not a slogan.** Seven signals (`sql_validity`,
  `schema_match`, `kpi_match`, `context_consistency`, `data_completeness`,
  `evidence_strength`, `result_consistency`) are weighted and summed; out-of-scope
  questions are hard-capped at 0.30 so a fluent answer to "what is the meaning of
  life?" is impossible.
- **Decision policy, not just an answer.** Above 0.70 → **Answer**; between 0.40
  and 0.70 → **Warn** (or **Clarify** if ambiguous); below → **Abstain**.
- **Every answer is auditable.** The evidence chain (question → SQL → KPI
  definition → filters → sample rows) is surfaced in the UI.
