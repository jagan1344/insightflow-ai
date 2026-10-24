# Phase 8 — Test report

## Backend

**Command:**
```sh
INSIGHTFLOW_REF_DATE="2026-10-21" \
  DATABASE_URL="sqlite:///$(pwd)/backend/data/insightflow.db" \
  python -m pytest backend/tests -q
```

**Result:** `264 passed / 0 failed / 0 skipped` in 41.53 s, 2 FastAPI
deprecation warnings (pre-existing `@app.on_event` → lifespan).

**Trajectory this round:**

| Phase | Tests before | Tests after | Net |
|---|---:|---:|---:|
| 1 — baseline | 251 | 251 | 0 |
| 2 — audit (docs only) | 251 | 251 | 0 |
| 3 — architecture (docs only) | 251 | 251 | 0 |
| 4 — median/percentile/stddev/variance | 251 | 252 | +1 (6 refusal tests moved into 4 oracle-matched tests + 1 orchestrator interception path = net +1 after rewriting fixtures) |
| 5 — follow-up resolver | 252 | 264 | +12 (7 resolver unit + 5 integration) |

## Scope of regression coverage

- **Unit:** dialect validator (12 cases), semantic fulfilment (5 cases),
  resolver (7 cases), stats (4 oracle-matched values).
- **Integration:** 20+ end-to-end questions through the orchestrator,
  including the originally reported Cases 1–3, the Phase 2 reruns, and
  Phase 5 follow-ups.
- **Property / metamorphic / invariant:**
  - adding a time filter never broadens
  - year-filter never includes other years
  - equivalent paraphrases produce equivalent SQL
  - dataset reseed is deterministic
  - semantic failure never produces high-confidence ANSWER
  - plan_trace carries intent + filters
- **Oracle-matched:** 11 Phase 2 capabilities + 4 Phase 4 statistical
  capabilities compared against stdlib `sqlite3` / `statistics`.

## Frontend

**Command:**
```sh
cd web && npx tsc --noEmit
```

**Result:** clean after `npm install` (deps are not pre-installed in
a fresh clone).

**Not run in this round** (deliberate scope limits):
- `npm run build` (prod build) — not executed; `.next` not available.
- `npm run lint` — not configured as a required CI step in this repo.
- Playwright / Cypress — none configured.

## Known failing tests

None.

## Reproduction

See `docs/verification/PHASE_01_BASELINE.md` for exact environment,
and the "Reproduction" section at the bottom of each per-phase doc.
