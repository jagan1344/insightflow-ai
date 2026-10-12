# Benchmark `expected_result` regeneration

**Source:** `evaluation/dataset/reliability_benchmark.jsonl` (archived verbatim as `reliability_benchmark_v1.jsonl.archive`)
**Output:** `evaluation/dataset/reliability_benchmark_v2.jsonl`

**Database:** `backend/data/insightflow.db` (seeded with `random.Random(42)` in `backend/data/seed.py`).

**Fields changed:** only `expected_result`. All other fields — `natural_language_question`, `gold_sql`, `answerability`, labels, signal gold values — are preserved verbatim.

**Rows total:** 27
**Rows whose `expected_result` changed:** 17

## Changed rows

| QID | Old `expected_result` | New `expected_result` |
|---|---|---|
| A01 | `[[3428686.53]]` | `{"value": 3388831.47}` |
| A02 | `[[2077]]` | `{"value": 2037}` |
| A03 | `[[7264]]` | `{"value": 7164}` |
| A04 | `[[1650.7879]]` | `{"value": 1663.6384241531666}` |
| A05 | `[[0.3772]]` | `{"value": 0.3770863854731613}` |
| A06 | `[[0.0381]]` | `{"value": 0.03812962056555596}` |
| A07 | `[["East", 980575.04], ["South", 979022.41], ["North", 774790.1], ["West", 694298.98]]` | `{"row_count": 4, "columns": 2, "sample_rows": [["East", 969084.07], ["South", 967823.2], ["North", 763684.64], ["West", ` |
| A08 | `[["Electronics", 1850923.65], ["Furniture", 899583.78], ["Software", 600171.94], ["Office", 78007.16]]` | `{"row_count": 4, "columns": 2, "sample_rows": [["Electronics", 1822286.44], ["Furniture", 899583.78], ["Software", 59039` |
| A09 | `[["2026-01", 384755.48], ["2026-02", 344681.6], ["2026-03", 413344.53], ["2026-04", 402345.86], ["2026-05", 453981.34], ` | `{"row_count": 9, "columns": 2, "sample_rows": [["2026-01", 384755.48], ["2026-02", 344681.6], ["2026-03", 413344.53], ["` |
| A10 | `[["Software", 0.6498], ["Office", 0.4505], ["Furniture", 0.351], ["Electronics", 0.2985]]` | `{"row_count": 4, "columns": 2, "sample_rows": [["Software", 0.6499008647525847], ["Office", 0.4504980618628764], ["Furni` |
| A11 | `[["Laptop", 648122.18], ["Headphones", 602992.92], ["Monitor", 599808.55], ["Desk", 316999.59], ["Chair", 306903.69]]` | `{"row_count": 5, "columns": 2, "sample_rows": [["Laptop", 628229.67], ["Headphones", 600572.68], ["Monitor", 593484.09],` |
| A12 | `[[1426.0783]]` | `{"value": 1426.0782936507935}` |
| A13 | `[[202536.65]]` | `{"value": 202536.65}` |
| A14 | `[["SMB", 1477106.12], ["Consumer", 1374981.92], ["Enterprise", 576598.49]]` | `{"row_count": 3, "columns": 2, "sample_rows": [["SMB", 1453892.15], ["Consumer", 1366346.68], ["Enterprise", 568592.64]]` |
| A15 | `[["Software", 1875], ["Office", 1870], ["Electronics", 1848], ["Furniture", 1671]]` | `{"row_count": 4, "columns": 2, "sample_rows": [["Software", 1851], ["Office", 1825], ["Electronics", 1817], ["Furniture"` |
| D01 | `[[202536.65]]` | `{"value": 202536.65}` |
| D02 | `[[202536.65]]` | `{"value": 202536.65}` |

## How to adopt v2

1. Review the diff above.
2. If every change looks correct against the pinned seed:

    ```sh
    mv evaluation/dataset/reliability_benchmark.jsonl \
       evaluation/dataset/reliability_benchmark_v1.jsonl
    mv evaluation/dataset/reliability_benchmark_v2.jsonl \
       evaluation/dataset/reliability_benchmark.jsonl
    ```

3. Rerun `evaluation/run_paper_eval.py` and
   `evaluation/compute_paper_metrics.py` — the
   semantic-accuracy numbers do not depend on
   `expected_result` (the oracle re-executes `gold_sql`)
   but any UI or human reader that trusts
   `expected_result` now has fresh values.