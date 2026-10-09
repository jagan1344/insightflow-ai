# Case studies — 4 questions on Full vs B1

Each question run on both configurations against the demo DB
(2 037 orders, 2026-01 to 2026-09). Full = default orchestrator;
B1 = same pipeline but every executed SQL is forced to ANSWER.

## 1. Which region contributed most to the decline from June to July?

### Full

- action: **ANSWER**  (reason: confidence 0.85 ≥ 0.70)
- confidence: 0.852
- plan.intent_kind: contribution
- measures: ['total_revenue'] · dims: ['region_name']
- failure_category: NONE



Result rows:

| region | base_value | target_value | delta |
|---|---|---|---|
| East | 156850.94 | 30479.76 | -126371.18000000001 |
| North | 124899.54000000001 | 47207.72 | -77691.82 |
| West | 72123.66 | 32535.24 | -39588.42 |
| South | 101120.27 | 92313.93 | -8806.340000000011 |

Confidence signals:
- sql_validity: 1.0
- schema_match: 1.0
- kpi_match: 0.4
- context_consistency: 1.0
- data_completeness: 1.0
- evidence_strength: 1.0
- result_consistency: 0.3
- intent_coverage: 1.0
- plan_fidelity: 1.0

### B1

- action: **ANSWER**  (reason: B1-forced (was ANSWER))
- confidence: 0.852
- plan.intent_kind: contribution
- measures: ['total_revenue'] · dims: ['region_name']
- failure_category: NONE



Result rows:

| region | base_value | target_value | delta |
|---|---|---|---|
| East | 156850.94 | 30479.76 | -126371.18000000001 |
| North | 124899.54000000001 | 47207.72 | -77691.82 |
| West | 72123.66 | 32535.24 | -39588.42 |
| South | 101120.27 | 92313.93 | -8806.340000000011 |

Confidence signals:
- sql_validity: 1.0
- schema_match: 1.0
- kpi_match: 0.4
- context_consistency: 1.0
- data_completeness: 1.0
- evidence_strength: 1.0
- result_consistency: 0.3
- intent_coverage: 1.0
- plan_fidelity: 1.0

---

## 2. Which customers have revenue above average but profit below average?

### Full

- action: **ANSWER**  (reason: confidence 0.99 ≥ 0.70)
- confidence: 0.993
- plan.intent_kind: relative_to_stat
- measures: ['total_revenue', 'profit'] · dims: ['customer_name']
- failure_category: NONE



Result rows:

| customer | m1 | m2 |
|---|---|---|
| Customer 030 | 63300.29 | 20754.08 |
| Customer 028 | 57410.07 | 21170.4 |
| Customer 021 | 57231.62 | 20587.51 |

Confidence signals:
- sql_validity: 1.0
- schema_match: 1.0
- kpi_match: 1.0
- context_consistency: 1.0
- data_completeness: 1.0
- evidence_strength: 0.9
- result_consistency: 1.0
- intent_coverage: 1.0
- plan_fidelity: 1.0

### B1

- action: **ANSWER**  (reason: B1-forced (was ANSWER))
- confidence: 0.993
- plan.intent_kind: relative_to_stat
- measures: ['total_revenue', 'profit'] · dims: ['customer_name']
- failure_category: NONE



Result rows:

| customer | m1 | m2 |
|---|---|---|
| Customer 030 | 63300.29 | 20754.08 |
| Customer 028 | 57410.07 | 21170.4 |
| Customer 021 | 57231.62 | 20587.51 |

Confidence signals:
- sql_validity: 1.0
- schema_match: 1.0
- kpi_match: 1.0
- context_consistency: 1.0
- data_completeness: 1.0
- evidence_strength: 0.9
- result_consistency: 1.0
- intent_coverage: 1.0
- plan_fidelity: 1.0

---

## 3. What is customer retention?

### Full

- action: **CLARIFY**  (reason: question is too vague to plan)
- confidence: 0.05
- plan.intent_kind: ambiguous
- measures: [] · dims: []
- failure_category: AMBIGUITY



Result rows:

| customer |
|---|
| Customer 001 |
| Customer 002 |
| Customer 003 |
| Customer 004 |
| Customer 005 |

Confidence signals:
- sql_validity: 1.0
- schema_match: 1.0
- kpi_match: 1.0
- context_consistency: 0.3
- data_completeness: 1.0
- evidence_strength: 1.0
- result_consistency: 1.0
- intent_coverage: 1.0
- plan_fidelity: 0.0

### B1

- action: **ANSWER**  (reason: B1-forced (was CLARIFY))
- confidence: 0.05
- plan.intent_kind: ambiguous
- measures: [] · dims: []
- failure_category: AMBIGUITY



Result rows:

| customer |
|---|
| Customer 001 |
| Customer 002 |
| Customer 003 |
| Customer 004 |
| Customer 005 |

Confidence signals:
- sql_validity: 1.0
- schema_match: 1.0
- kpi_match: 1.0
- context_consistency: 0.3
- data_completeness: 1.0
- evidence_strength: 1.0
- result_consistency: 1.0
- intent_coverage: 1.0
- plan_fidelity: 0.0

---

## 4. Top 5 products by profit in Q2 2026, revenue in H1

### Full

- action: **ANSWER**  (reason: confidence 1.00 ≥ 0.70)
- confidence: 1.0
- plan.intent_kind: top_n
- measures: ['profit', 'total_revenue'] · dims: ['product_name']
- failure_category: NONE



Result rows:

| product | profit | total_revenue |
|---|---|---|
| Monitor | 76857.33 | 257987.11000000002 |
| Laptop | 69056.76 | 231218.38 |
| Headphones | 67237.74 | 227262.35 |
| Chair | 45463.71 | 130030.06 |
| Office Suite | 45023.39 | 69151.65 |

Confidence signals:
- sql_validity: 1.0
- schema_match: 1.0
- kpi_match: 1.0
- context_consistency: 1.0
- data_completeness: 1.0
- evidence_strength: 1.0
- result_consistency: 1.0
- intent_coverage: 1.0
- plan_fidelity: 1.0

### B1

- action: **ANSWER**  (reason: B1-forced (was ANSWER))
- confidence: 1.0
- plan.intent_kind: top_n
- measures: ['profit', 'total_revenue'] · dims: ['product_name']
- failure_category: NONE



Result rows:

| product | profit | total_revenue |
|---|---|---|
| Monitor | 76857.33 | 257987.11000000002 |
| Laptop | 69056.76 | 231218.38 |
| Headphones | 67237.74 | 227262.35 |
| Chair | 45463.71 | 130030.06 |
| Office Suite | 45023.39 | 69151.65 |

Confidence signals:
- sql_validity: 1.0
- schema_match: 1.0
- kpi_match: 1.0
- context_consistency: 1.0
- data_completeness: 1.0
- evidence_strength: 1.0
- result_consistency: 1.0
- intent_coverage: 1.0
- plan_fidelity: 1.0

---
