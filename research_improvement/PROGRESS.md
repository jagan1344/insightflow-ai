# PROGRESS ledger

| phase | status | key output |
|---|---|---|
| 0 audit | done | `00_initial_audit.md` |
| 1 semantic fixes | done | `01_semantic_capability_matrix.md` |
| 2 regression tests | done | `02_regression_results.md`; full suite 526 passed / 0 failed / 3 warnings |
| 3 freeze | done | `freeze/FREEZE_MANIFEST.json`; commit `38b60d1`, tree `00db6e2` |
| 4 new evaluation data | done (agent-generated, not human-adjudicated) | `evaluation/v5_provisional/`, `eval/V5_PROTOCOL.md`, manifest `1550b59` |
| 5 frozen first run | done | `eval/results/v5_A0_first_run.json` (`4bbba9c`), summary |
| 6 ablations | done | `03_ablation_results.csv`, `04_ablation_analysis.md` |
| 7 confidence / error analysis | done | `05_confidence_analysis.md`, `06_error_analysis.md` |
| 8 external baseline | not feasible, documented | `07_external_baseline.md` |
| 9 figures | done | `figures/` (7 figures, PDF + SVG) |
| 10 paper | draft done; LaTeX not compiled (no toolchain); original manuscript absent | `../paper/` |
| 11 package | done | `README.md`, `FINAL_RESEARCH_REPORT.md` |
| 12 audit | done | `audit_claims.py` 37/37; K1/K3/historical unchanged; A0 re-run identical 105/105; final suite 526 passed |

Rules kept: no push; K1/K3, historical v2 and paper_evidence byte-unchanged since `b11793b`; first-run file never overwritten.
