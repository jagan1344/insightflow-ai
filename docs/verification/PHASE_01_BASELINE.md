# Phase 1 — Baseline

## Repository

- **Remote:** https://github.com/jagan1344/insightflow-ai
- **Branch:** `claude/insightflow-ai-build-2neph7`
- **HEAD at start of this phase:** `27f683f`
- **Working tree:** clean (`git status --short` → empty).

## Reported baseline vs. verified baseline

| Claim | Reported | Verified |
|---|---|---|
| Backend tests passing | 253 | **251 passed / 0 failed / 0 skipped** |
| Frontend `tsc --noEmit` | pass | pass (after `npm install`) |
| Capability gate exists | yes | yes — `backend/insightflow/safety/capability_check.py` |
| MTD / QTD / multi-quarter comparison | implemented | implemented (planner.py `_find_relative_period`, `_find_two_months`) |
| Historical benchmark preserved | yes | `evaluation/dataset/reliability_benchmark_v1.jsonl.archive` intact |

Reported "253" vs. verified "251" is a minor drift: in Phase 2 of this
work (commit `27f683f`) 11 refusal assertions were replaced by 11
ANSWER + oracle regressions and the net count differs from
the pre-replacement total. All assertions were strengthened, none
weakened.

## Runtime

- Python: `/usr/local/bin/python3` → **Python 3.11.15**
- Pytest: 9.1.1
- SQLite: **3.45.1** (window functions ✓, no native median/percentile/stddev)
- Node: available via `npx` (version shown by `node -v` not required here)
- OS: Linux 6.18.44-fc-v153 (containerised)

## Exact commands run

```sh
cd /home/user/insightflow-ai
git log --oneline -3
git status --short
python3 backend/data/seed.py
INSIGHTFLOW_REF_DATE="2026-10-21" \
  DATABASE_URL="sqlite:///$(pwd)/backend/data/insightflow.db" \
  python3 -m pytest backend/tests -q
cd web && npx tsc --noEmit
```

## Test output (snapshot)

```
251 passed, 2 warnings in 35.60s
```

Two warnings are pre-existing FastAPI deprecations
(`on_event` → lifespan). They do not represent correctness issues.

## Supported adapters (verified from code)

- **Database engines:** SQLite (default; `sqlalchemy` + stdlib `sqlite3`
  for the oracle). Postgres path is present via `DATABASE_URL`
  (`postgresql+psycopg2://…`) but is **not** exercised by the test suite.
- **Dataset formats:** CSV, XLSX, XLS via `/api/upload/orders`.
- **Supported SQL dialect for generated SQL:** SQLite only. The
  dialect validator (`backend/insightflow/validation/dialect_validator.py`)
  rejects Postgres/MSSQL/MySQL idioms before execution.

## Known limitations (carried forward)

- SQLite 3.45 has no native `median()`, `percentile()`, `stddev()`,
  `variance()`. These are refused by the capability gate; Phase 4 of
  this work implements median + percentile via Python-side
  post-aggregation.
- Stateful follow-ups ("that month", "now by region") are treated as
  fresh questions. Phase 5 of this work adds a minimal resolver.
- The IEEE manuscript file (`paper/InsightFlow_AI_IEEE_Paper.docx`) is
  not in this checkout (see `paper_evidence/discrepancies.md` D1).
  Phase 11 of this work can produce a text draft but cannot edit a
  `.docx` that does not exist in the repo.

## Preserved assets (not modified by this work)

- `paper_evidence/*` — the frozen research pack
- `evaluation/dataset/reliability_benchmark.jsonl` — the 27-question
  dev benchmark (original)
- `evaluation/dataset/reliability_benchmark_v1.jsonl.archive`
- `backend/data/insightflow.db` — the demo DB (seeded by
  `backend/data/seed.py` with `random.Random(42)`)

## Acceptance

Baseline is reproducible. User work is preserved.
