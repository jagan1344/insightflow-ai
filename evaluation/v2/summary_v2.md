# Benchmark v2 — summary

- **Commit:** `27f683fc2a6678ff6aff62ee06371cd5259c8f0e`
- **Questions:** 27
- **Action match:** 27 / 27 = 100.0%

## Per category

| Category | n | ok | rate |
|---|---:|---:|---:|
| ambiguous | 1 | 1 | 100.0% |
| breakdown | 2 | 2 | 100.0% |
| count_distinct | 1 | 1 | 100.0% |
| destructive | 1 | 1 | 100.0% |
| diagnostic | 1 | 1 | 100.0% |
| direct_kpi | 3 | 3 | 100.0% |
| extremum | 1 | 1 | 100.0% |
| forecast | 1 | 1 | 100.0% |
| having_threshold | 1 | 1 | 100.0% |
| multi_metric_breakdown | 1 | 1 | 100.0% |
| out_of_scope | 1 | 1 | 100.0% |
| period_filter | 1 | 1 | 100.0% |
| range_trend | 1 | 1 | 100.0% |
| rank_within_group | 1 | 1 | 100.0% |
| relative_period | 1 | 1 | 100.0% |
| relative_period_out_of_range | 1 | 1 | 100.0% |
| relative_to_stat | 1 | 1 | 100.0% |
| sliding_window | 1 | 1 | 100.0% |
| stat_median | 1 | 0 | 0.0% |
| stat_percentile | 1 | 0 | 0.0% |
| stat_stddev | 1 | 0 | 0.0% |
| top_n | 1 | 1 | 100.0% |
| top_n_per_group | 1 | 1 | 100.0% |
| unsupported_duplicates | 1 | 1 | 100.0% |

## Per question

| id | category | expected | observed | action ok | numeric ok |
|---|---|---|---|:---:|:---:|
| V2-A01 | direct_kpi | ANSWER | ANSWER | ✅ | ✅ |
| V2-A02 | direct_kpi | ANSWER | ANSWER | ✅ | ✅ |
| V2-A03 | direct_kpi | ANSWER | ANSWER | ✅ | ✅ |
| V2-B01 | breakdown | ANSWER | ANSWER | ✅ | ✅ |
| V2-B02 | breakdown | ANSWER | ANSWER | ✅ | ✅ |
| V2-B03 | multi_metric_breakdown | ANSWER | ANSWER | ✅ | ✅ |
| V2-C01 | period_filter | ANSWER | ANSWER | ✅ | ✅ |
| V2-C02 | range_trend | ANSWER | ANSWER | ✅ | ✅ |
| V2-C03 | relative_period_out_of_range | CLARIFY | CLARIFY | ✅ | ✅ |
| V2-C04 | relative_period | ANSWER | ANSWER | ✅ | ✅ |
| V2-C05 | sliding_window | ANSWER | ANSWER | ✅ | ✅ |
| V2-D01 | top_n | ANSWER | ANSWER | ✅ | ✅ |
| V2-D02 | top_n_per_group | ANSWER | ANSWER | ✅ | ✅ |
| V2-D03 | having_threshold | ANSWER | ANSWER | ✅ | ✅ |
| V2-E01 | diagnostic | ANSWER | ANSWER | ✅ | ✅ |
| V2-F01 | relative_to_stat | ANSWER | ANSWER | ✅ | ✅ |
| V2-G01 | stat_median | ANSWER | ANSWER | ✅ | ❌ |
| V2-G02 | stat_percentile | ANSWER | ANSWER | ✅ | ❌ |
| V2-G03 | stat_stddev | ANSWER | ANSWER | ✅ | ❌ |
| V2-H01 | count_distinct | ANSWER | ANSWER | ✅ | ✅ |
| V2-H02 | extremum | ANSWER | ANSWER | ✅ | ✅ |
| V2-I01 | destructive | ABSTAIN | ABSTAIN | ✅ | ✅ |
| V2-I02 | forecast | CLARIFY | CLARIFY | ✅ | ✅ |
| V2-I03 | out_of_scope | CLARIFY | CLARIFY | ✅ | ✅ |
| V2-I04 | ambiguous | CLARIFY | CLARIFY | ✅ | ✅ |
| V2-I05 | rank_within_group | ANSWER | ANSWER | ✅ | ✅ |
| V2-I06 | unsupported_duplicates | CLARIFY | CLARIFY | ✅ | ✅ |