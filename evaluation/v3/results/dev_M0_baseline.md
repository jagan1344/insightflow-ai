# dev / M0_baseline

- correct answers: 2/25 answerable
- answered answerable: 4/25
- silent wrong (answered, wrong; incl. answered-when-should-clarify): 4/31
- of which confidence >= 0.70: 4
- abstained on answerable: 21
- correct clarifications: 4/6
- errors: 0

| id | family | outcome | action | conf | question |
|---|---|---|---|---|---|
| A01 | single | abstained | CLARIFY | 0.05 | What is the total fee across all visits? |
| A02 | single | abstained | CLARIFY | 0.05 | How many visits were there? |
| A03 | grouped | abstained | CLARIFY | 0.05 | Total fee by specialty |
| A04 | nulls | abstained | CLARIFY | 0.05 | Total fee by insurer |
| A05 | join_filter | silent_wrong | ANSWER | 0.979 | Total fee for Cardiology doctors |
| A06 | distinct | abstained | CLARIFY | 0.05 | How many distinct patients visited in March 2025? |
| A07 | join_filter | abstained | CLARIFY | 0.05 | Total fee for patients insured by Medicaid (State) |
| A08 | ambiguous | silent_wrong | ANSWER | 0.979 | Total fee at Saint Mary's Clinic |
| A09 | fanout | silent_wrong | ANSWER | 0.979 | Total fee for visits with an Imaging procedure |
| A10 | fanout | abstained | CLARIFY | 0.05 | How many visits included an MRI? |
| A11 | zero_fact | abstained | CLARIFY | 0.05 | Total fee for patients insured by Pacific Mutual |
| A12 | unknown | correct_clarify | CLARIFY | 0.05 | Total fee for patients insured by Cigna |
| A13 | topn | abstained | CLARIFY | 0.05 | Top 3 doctors by total fee |
| A14 | nulls | correct | ANSWER | 0.979 | What is the average copay? |
| A15 | time | correct | ANSWER | 0.979 | Total fee in June 2025 |
| A16 | ambiguous | silent_wrong | ANSWER | 1.0 | Total fee by month |
| B01 | single | abstained | CLARIFY | 0.05 | What is the total freight cost? |
| B02 | single | abstained | CLARIFY | 0.05 | How many shipments were there? |
| B03 | nulls | abstained | CLARIFY | 0.05 | Total freight cost by carrier |
| B04 | join_filter | abstained | CLARIFY | 0.05 | Total freight cost for carrier O'Brien & Sons |
| B05 | join_filter | abstained | CLARIFY | 0.05 | Total freight cost for Gold tier customers |
| B06 | grouped | abstained | CLARIFY | 0.05 | Total freight cost by origin hub |
| B07 | ambiguous | correct_clarify | CLARIFY | 0.05 | Total freight cost for Port of Rotterdam |
| B08 | join_filter | abstained | CLARIFY | 0.05 | How many parcels were shipped by Blue Jay Freight? |
| B09 | fanout | abstained | CLARIFY | 0.05 | Total freight cost for shipments tagged Fragile |
| B10 | distinct | abstained | CLARIFY | 0.05 | How many distinct customers shipped in July 2025? |
| B11 | zero_fact | abstained | CLARIFY | 0.05 | Total freight cost for carrier Dormant Haulage |
| B12 | unknown | correct_clarify | CLARIFY | 0.05 | Total freight cost for carrier Fedex |
| B13 | topn | abstained | CLARIFY | 0.05 | Top 2 carriers by total freight cost |
| B14 | nulls | abstained | CLARIFY | 0.05 | What is the average insured value? |
| B15 | ambiguous | correct_clarify | CLARIFY | 0.05 | Total freight cost by region code |
