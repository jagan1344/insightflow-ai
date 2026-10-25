# Evidence map for the manuscript draft
| claim | source |
|---|---|
| v5 first-run figures, CIs, latency, borderline sensitivity | `research_improvement/eval/results/v5_A0_first_run.json` + `score_v5.py` |
| ablation table, transitions | `research_improvement/03_ablation_results.csv`, `eval/results/ablation_transitions.json` |
| confidence numbers | `research_improvement/eval/results/confidence_analysis.json` |
| K1, K3, earlier first runs | `evaluation/v3/results/*_first_and_only.json`, `final6_K3_posthoc_not_heldout.json` |
| post-hoc 54/54 | `evaluation/v3/results/final6_P1_posthoc_not_heldout.json` |
| 526 tests | `research_improvement/freeze/FREEZE_MANIFEST.json` and the final run |
| 21 intent kinds, thresholds, signals | `backend/insightflow/plan/plan.py`, `config.py`, `reliability/confidence.py` |
All checked by `research_improvement/audit_claims.py`.
