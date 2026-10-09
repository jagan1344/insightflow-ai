## git state
- commit: 3c843de88ca0b62669749b217aaef000e3e6363e
- branch: claude/insightflow-ai-build-2neph7
- remote: https://github.com/jagan1344/insightflow-ai
- status:
  ?? paper_evidence/

## system
- os: Linux vm 6.18.44-fc-v80 #1 SMP PREEMPT_DYNAMIC @0 x86_64 x86_64 x86_64 GNU/Linux
- python: Python 3.11.15
- node: v22.22.2
- date: 2026-10-09T15:21:59Z

## key python packages
- Name: mcp Version: 2.3.0
- Name: fastapi Version: 0.141.1
- Name: SQLAlchemy Version: 2.0.54
- Name: uvicorn Version: 0.54.0
- Name: pydantic Version: 2.13.5

## database
- configured DATABASE_URL: (unset — defaults to sqlite:///data/insightflow.db relative to CWD)
- actual demo db file: backend/data/insightflow.db (262144 bytes)

## line counts (git ls-files + wc -l)
- backend Python: 13032
- backend tests:  2202
- web TS/TSX:     3643

## startup commands
- backend: uvicorn api.main:app --reload --port 8000  (CWD=backend)
- frontend: npm run dev                               (CWD=web, port 3000)
- mcp servers spawned on demand per backend/mcp_config.yaml
