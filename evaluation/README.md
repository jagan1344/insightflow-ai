# InsightFlow AI — research evaluation

Purpose. Turn the shipped InsightFlow AI application into a properly
evaluated research prototype without touching the working system.
Every number here is measured against the real orchestrator; no
manually-authored results.

## Contents

```
evaluation/
├── dataset/    reliability_benchmark.{jsonl,csv} + README   (project-generated)
├── scripts/    prepare_dataset · run_evaluation · calculate_metrics ·
│               run_ablation · generate_figures
├── results/    raw_results.csv · results.json · metrics.json · summary.csv ·
│               ablation.{csv,json}
├── figures/    fig1..fig8 — generated from `results/`
└── reports/
     ├── basepaper_analysis.md      the BIRD paper, extracted
     ├── alignment.md               what carries over to InsightFlow, honestly
     ├── basepaper_comparison.md    BIRD vs InsightFlow, per-aspect
     ├── novelty.md                 defensible claim + non-claims
     └── research_evaluation.md     the final report — read this last
```

## Reproduce end-to-end

```bash
# Backend + DB (once)
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python data/seed.py
cd ..

# Full evaluation
export DATABASE_URL="sqlite:///$(pwd)/backend/data/insightflow.db"
backend/.venv/bin/python evaluation/scripts/prepare_dataset.py
backend/.venv/bin/python evaluation/scripts/run_evaluation.py
backend/.venv/bin/python evaluation/scripts/calculate_metrics.py
backend/.venv/bin/python evaluation/scripts/run_ablation.py
backend/.venv/bin/python evaluation/scripts/generate_figures.py

# Tests (pipeline + new evaluation tests)
cd backend && pytest -q
```

## Base paper

*BIRD* — Li et al., NeurIPS 2023 Datasets & Benchmarks. arXiv:2305.03111.
Data licence CC BY-NC 4.0 (academic use).

InsightFlow **adopts** BIRD's Execution-Accuracy metric and difficulty
taxonomy, and **maps** BIRD's "external knowledge sentence" concept
onto InsightFlow's KPI semantic layer. InsightFlow does **not**
reproduce BIRD's benchmark and does not claim BIRD superiority. See
`reports/alignment.md`.

## In one line

BIRD measures *"can the system produce the correct SQL?"* — InsightFlow
additionally measures *"does the system know when it's right, and does
it abstain when it isn't?"* — the evaluation here is scoped to the
second question.
