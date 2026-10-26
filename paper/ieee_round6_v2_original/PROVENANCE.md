# Figure and table provenance — InsightFlow AI (Round 6 manuscript with figures)

Repository: https://github.com/jagan1344/insightflow-ai (branch `claude/insightflow-ai-build-2neph7`).
Checked read-only; no experimental artifact was modified.

| Item | What it shows | Source code / evidence | Commit(s) | How it was checked |
|---|---|---|---|---|
| Fig. 1 Architecture | Orchestrator stages 1–8, inputs, data, tools | `backend/insightflow/orchestrator.py` module docstring (13 pipeline calls) and step 12b; `evaluation/v3/run_eval.py` calls `Orchestrator().ask(q)` | `78d906b`, `a63cec1`, `b11793b` (stages identical) | Docstring stages, fulfilment checks and step 12b present at all three revisions; frontend, REST API and MCP shown dashed because the harness bypasses them |
| Fig. 2 Semantic workflow | Gate, spec → typecheck → preserve, violation handling, exception handling | `orchestrator.py` step 12b; `semantics/verify.py` (`verify_semantics`) | Gate and fail-open: `78d906b`, `a63cec1`; `ratio` intent kind added `a63cec1`; fail-closed: `b11793b` | Code read at each revision; diff `a63cec1..b11793b` adds the fail-closed branch |
| Fig. 3 K1 vs K3 | Correct, unanswered, silent wrong, clarifications as % of stated denominators | `evaluation/v3/results/final6_K1_first_and_only.json`, `final6_K3_posthoc_not_heldout.json` → `figures/data/round6_k1_k3.csv` | K1 run recorded `7e30dc4` (backend frozen `78d906b`); K3 `a63cec1` | Values extracted programmatically from the `summary` blocks; match the committed `.md` reports |
| Fig. 4 A17 trace | Question, SQL, value, reference, decision, outcome in K1 and K3 | Same two JSON files, entry `A17` (`sql`, `sys_value`, `expected`, `action`, `confidence`, `outcome`) | `78d906b` / `a63cec1` | Copied from the records; SQL abbreviated (identifier quotes and alias removed). The records hold no semantic findings, so none are shown |
| Table I Related work | Contribution and role of each cited work | References [1]–[8] | — | Titles, venues and pages verified earlier ([4] ICLR 2025 re-verified); roles limited to what the paper states |
| Table II Semantic rules | 25 rule codes, what each detects, revision introduced | `semantics/typecheck.py`, `semantics/preserve.py` (`SemanticFinding.severity` default `"violation"`) | `78d906b` (23 codes) vs `a63cec1` (+`polarity_inverted`, `ratio_unsupported`) | Rule codes and detail strings parsed from source at both revisions; only `assumption` is a note |
| Table III Results | Historical, K1, K3 with revisions and denominators | Historical: `paper_evidence/pinned_3c843de/per_question.csv`; K1/K3 JSON summaries | `3c843de`; `78d906b`; `a63cec1` | Historical figures re-verified in earlier audits; K1/K3 from JSON; K3 mean confidence on correct answers (0.977) computed from per-question rows |
| Table IV Error analysis | A17, V07, unanswered families, D01/D02, exceptions, scope, unsupported patterns | K1/K3 JSON (`family`, `outcome`); round-6 limitations doc `docs/SEMANTIC_LAYER_ROUND6_2026-10-25.md`; orchestrator diff | `78d906b`, `a63cec1`, `b11793b` | Family counts computed from rows with outcome `abstained`; limitation list matches the doc |
| Text: 495 tests | Regression suite result | `backend/tests` at `b11793b` | `b11793b` | Run in a temporary worktree: **495 passed, 3 warnings**; stated as implementation checks, not accuracy |

Not verified: that the Round 6 reference SQL was prepared independently of the system (stated in the manuscript).
