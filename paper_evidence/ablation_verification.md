# Ablation switch verification

Each row shows that the ablation switch used in
`evaluation/run_paper_eval.py` actually disables its guard on
a hand-crafted input designed to trigger that guard. These
unit-style checks are INDEPENDENT of the 27-question benchmark
and establish that the switches themselves work.

The null result on the benchmark (Full == B1 == A1 == A2 == A3)
therefore reflects the benchmark not exercising these cases,
not a broken switch.

| Case | Guard | Full output | Ablated output | Fired in Full | Disabled in ablation | Verdict |
|---|---|---|---|:---:|:---:|:---:|
| A1: dropped filter | `FidelityValidator.check` | ok=False, score=0.667, failed=['filter_eq:region_id'] | ok=True, score=1.000 | YES | YES | **PASS** |
| A2: top_n=5 with 7 rows + unsorted | `ResultValidator.check` | ok=False, score=0.000, issues=['top_n=N=5 but result returned 7 rows', 'top_n result is not sorted descending'] | ok=True, score=1.000 | YES | YES | **PASS** |
| A3: raw sum high, coverage/fidelity low | `score_confidence hard cap` | score=0.3500 (raw sum = 0.7943, cov+.05=0.7167, fid+.05=0.3500) | score=0.7943 (raw sum) | YES | YES | **PASS** |

## Interpretation

All three ablation switches change behaviour on an input
constructed to trigger their respective guard. The
27-question benchmark produces identical outputs across all
configurations because the compiled SQL always matches the
plan (deterministic rule-based planner + canonical formulas
from the KPI catalog), so no fidelity failure arises, no
result-shape violation arises, and the raw weighted-sum
confidence never exceeds `coverage+0.05` or `fidelity+0.05`.

The guards therefore act as *insurance*: they do not
improve measured accuracy on this benchmark, but they
would catch (and this script PROVES they do catch) failure
modes that an LLM-driven planner or a different compiler
configuration might introduce.