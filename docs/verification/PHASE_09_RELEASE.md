# Phase 9 — Release stabilization

## Release-candidate checklist

| Item | Status | Notes |
|---|---|---|
| All backend tests pass | ✅ | 264 passed / 0 failed / 0 skipped |
| Web `tsc --noEmit` clean | ✅ | after `npm install` |
| No secrets committed | ✅ | `.env.example` only; no `.env` tracked |
| Historical research artefacts preserved | ✅ | `paper_evidence/*` and `evaluation/dataset/reliability_benchmark_v1.jsonl.archive` unchanged |
| No destructive git operations | ✅ | only normal commits + regular pushes |
| Windows PowerShell setup documented | ✅ | README + per-phase docs |
| Dependency versions pinned | ✅ (backend) / ⚠️ (web uses `^` ranges in package.json) |
| Environment variables documented | ✅ | `INSIGHTFLOW_REF_DATE`, `DATABASE_URL`, `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_STRICT_MODE`, `INSIGHTFLOW_SEED_DB_PATH`, `MAX_ROWS` |
| Read-only SQL enforcement | ✅ | `validate_sql` + dialect validator + destructive pre-gate |

## Reproduction steps (Windows PowerShell)

```powershell
# Clone + branch
git clone https://github.com/jagan1344/insightflow-ai.git
cd insightflow-ai
git checkout claude/insightflow-ai-build-2neph7

# Backend
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python data\seed.py
$env:DATABASE_URL = "sqlite:///$PWD\data\insightflow.db"
$env:INSIGHTFLOW_REF_DATE = "2026-10-21"
python -m pytest tests -q        # 264 passed
uvicorn api.main:app --reload --port 8000

# Frontend (new PowerShell)
cd ..\web
npm install
npm run dev
```

Open `http://localhost:3000/app` for the dashboard shell.

## What was NOT changed in this round

- `paper_evidence/*`
- `evaluation/dataset/*.jsonl` (except the opt-in v2 regen already
  staged)
- `evaluation/oracle.py`
- Any manuscript file (no .docx present in the checkout)

## Commits in this round

Will be shown in the final commit log after Phase 12.
