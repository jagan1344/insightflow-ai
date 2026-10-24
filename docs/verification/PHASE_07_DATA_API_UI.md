# Phase 7 — Dataset, API, frontend

## Dataset handling

- `backend/data/seed.py` — deterministic seed (`random.Random(42)`)
  with the documented July-dip pattern.
- `backend/api/routes_upload.py` — CSV / XLSX / XLS upload,
  per-upload table (not overwrites), schema inference.
- `backend/insightflow/knowledge/dataset_registry.py` — multi-dataset
  registry; `set_active(id)` controls which the planner sees.
- `backend/insightflow/knowledge/kpi_catalog.py` — dataset-derived
  KPI catalog (not hardcoded for the demo).

Verified:
- `test_dataset_switching.py` — swapping active dataset mid-session
  does not leak columns or KPIs across datasets.
- `test_capability_gate_invariants.py::test_invariant_dataset_switch_reseed_isolates` — reseeding produces identical totals.

## API

- `POST /api/ask` — the primary question endpoint.
- `GET /api/dashboard` + WebSocket `/ws` — real-time dashboard.
- `GET /api/upload/sample.csv` + `POST /api/upload/orders` — upload.
- `GET /api/pages/*` — per-page data.
- Response includes: `question`, `sql`, `intent`, `decision.action`,
  `decision.reason`, `confidence.score`, `confidence.signals`,
  `result.columns`, `result.rows`, `explanation`, `evidence`,
  `plan_trace`, `diagnostics`.
- Read-only enforcement: SQL validator rejects mutating keywords;
  destructive requests ABSTAIN BEFORE SQL generation (safety pre-gate).

Verified:
- `test_pipeline.py` — end-to-end API shape.
- `test_safety.py` — 25-case safety matrix (0 unsafe answers in the
  controlled slice).
- `test_system_wide_repair.py::TestLLMPathHardening` — the LLM
  text-to-SQL path (when enabled) is routed through the dialect +
  fulfilment gates.

## Frontend

- `web/app/app/sources/page.tsx` — Data Sources page with the Phase 1
  (prior round) upload panel.
- `web/components/shell/TopBar.tsx` — Upload button on every page.
- `web/components/dashboard/UploadDialog.tsx` — upload UI with
  replace/append modes.
- 10 app pages all go through the same `/api/ask` and `/api/pages/*`
  contract.
- `npx tsc --noEmit` → clean after `npm install`.

## Known limitations

- No automated frontend tests. Manual verification is required for
  rendering correctness.
- No E2E Playwright/Cypress suite in this build.
- Dataset-switching UI does exist (dataset picker in TopBar); its
  end-to-end behaviour is covered by the backend `test_dataset_switching.py`
  tests, not by a frontend test.
