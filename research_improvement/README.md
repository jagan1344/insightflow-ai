# research_improvement — reproducibility package

Everything here was produced on 2026-10-25 on branch `claude/insightflow-ai-build-2neph7` (local commits, not pushed).

| file | content |
|---|---|
| `00_initial_audit.md` | repository state at start, components, missing manuscript |
| `01_semantic_capability_matrix.md` | 22-category capability matrix, which safeguards run where, fixes made |
| `02_regression_results.md` | tests, historical benchmarks, monitor re-runs (P1) |
| `freeze/FREEZE_MANIFEST.json`, `freeze/pip_freeze.txt` | frozen commit `38b60d1`, backend tree `00db6e2`, source hashes, environment |
| `eval/V5_PROTOCOL.md`, `eval/V5_MANIFEST.sha256` | pre-registered protocol and hashes of the v5 set (committed before the first run) |
| `eval/run_v5.py`, `eval/run_v5_leave_one_in.py`, `eval/score_v5.py` | runner (refuses non-frozen code, never overwrites), scorer |
| `eval/results/v5_A0_first_run.json` | **first run, raw** (committed before scoring, `4bbba9c`) |
| `eval/results/v5_A[1-7]_ablation.json`, `v5_B[1-6]_leave_one_in.json` | ablation runs |
| `eval/results/v5_A0_repro_check.json` | re-run of A0 for determinism (identical on 105/105) |
| `03_ablation_results.csv`, `04_ablation_analysis.md` | ablation metrics and paired transitions |
| `05_confidence_analysis.md`, `06_error_analysis.md` | confidence and error analysis |
| `07_external_baseline.md` | why no external baseline was run |
| `figures/` | Figs. 1-7 (PDF + SVG) and their generator scripts |
| `audit_claims.py` | recomputes every quoted number from saved outputs (37 checks, 0 failures) |
| `FINAL_RESEARCH_REPORT.md`, `PROGRESS.md` | summary and ledger |
| `../paper/` | manuscript source (`content.py` -> `insightflow_paper.tex`, `.html`), preview PDF |
| `../evaluation/v5_provisional/` | v5 schemas, questions, references, author's validator and notes |

## Reproduce
    cd backend && python -m pytest -q                                   # 526 passed, 3 warnings
    cd ../evaluation/v5_provisional && python validate_v5.py            # ALL CHECKS PASSED
    sha256sum -c ../../research_improvement/eval/V5_MANIFEST.sha256     # from evaluation/v5_provisional (data/*.db are rebuilt byte-identically)
    cd ../../research_improvement/eval
    python run_v5.py A0 <new_label>                                     # requires backend tree 00db6e2
    for c in A1 A2 A3 A4 A5 A6 A7; do python run_v5.py $c <label>; done
    for c in B1 B2 B3 B4 B5 B6; do python run_v5_leave_one_in.py $c <label>; done
    python score_v5.py results/v5_*_<label>.json
    python ablation_analysis.py && python confidence_analysis.py        # read the committed file names; edit for new labels
    cd ../figures && python make_diagrams.py && python make_result_figures.py
    cd .. && python audit_claims.py
    cd ../paper && python build.py                                      # .tex + .html + preview PDF (needs node playwright + Chromium)
    cd ../evaluation/v2 && python exec_accuracy_bench.py && python exec_accuracy_advanced.py && python heldout_e2e.py; cd ../.. && git checkout -- evaluation/v2
