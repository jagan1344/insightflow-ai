# dev / M2_relational

- correct answers: 24/25 answerable
- answered answerable: 24/25
- silent wrong (answered, wrong; incl. answered-when-should-clarify): 0/32
- of which confidence >= 0.70: 0
- abstained on answerable: 1
- correct clarifications: 7/7
- errors: 0

| id | family | outcome | action | conf | question |
|---|---|---|---|---|---|
| A01 | single | correct | ANSWER | 0.979 | What is the total fee across all visits? |
| A02 | single | correct | ANSWER | 0.979 | How many visits were there? |
| A03 | grouped | correct | ANSWER | 1.0 | Total fee by specialty |
| A04 | nulls | correct | ANSWER | 0.992 | Total fee by insurer |
| A05 | join_filter | correct | ANSWER | 0.979 | Total fee for Cardiology doctors |
| A06 | distinct | correct | ANSWER | 0.979 | How many distinct patients visited in March 2025? |
| A07 | join_filter | correct | ANSWER | 0.979 | Total fee for patients insured by Medicaid (State) |
| A08 | ambiguous | correct_clarify | CLARIFY | 0.05 | Total fee at Saint Mary's Clinic |
| A09 | fanout | correct | ANSWER | 0.979 | Total fee for visits with an Imaging procedure |
| A10 | fanout | correct | ANSWER | 0.979 | How many visits included an MRI? |
| A11 | zero_fact | correct | WARN | 0.899 | Total fee for patients insured by Pacific Mutual |
| A12 | unknown | correct_clarify | CLARIFY | 0.05 | Total fee for patients insured by Cigna |
| A13 | topn | correct | ANSWER | 0.993 | Top 3 doctors by total fee |
| A14 | nulls | correct | ANSWER | 0.979 | What is the average copay? |
| A15 | ambiguous | correct_clarify | CLARIFY | 0.05 | Total fee in June 2025 |
| A17 | time | correct | ANSWER | 0.979 | Total fee for visits in June 2025 |
| A16 | ambiguous | correct_clarify | CLARIFY | 0.05 | Total fee by month |
| B01 | single | correct | ANSWER | 0.979 | What is the total freight cost? |
| B02 | single | correct | ANSWER | 0.979 | How many shipments were there? |
| B03 | nulls | correct | ANSWER | 0.993 | Total freight cost by carrier |
| B04 | join_filter | correct | ANSWER | 0.979 | Total freight cost for carrier O'Brien & Sons |
| B05 | join_filter | correct | ANSWER | 0.979 | Total freight cost for Gold tier customers |
| B06 | grouped | correct | ANSWER | 1.0 | Total freight cost by origin hub |
| B07 | ambiguous | correct_clarify | CLARIFY | 0.05 | Total freight cost for Port of Rotterdam |
| B08 | join_filter | abstained | CLARIFY | 0.3 | How many parcels were shipped by Blue Jay Freight? |
| B09 | fanout | correct | ANSWER | 0.979 | Total freight cost for shipments tagged Fragile |
| B10 | distinct | correct | ANSWER | 0.979 | How many distinct customers shipped in July 2025? |
| B11 | zero_fact | correct | WARN | 0.899 | Total freight cost for carrier Dormant Haulage |
| B12 | unknown | correct_clarify | CLARIFY | 0.05 | Total freight cost for carrier Fedex |
| B13 | topn | correct | ANSWER | 0.986 | Top 2 carriers by total freight cost |
| B14 | nulls | correct | ANSWER | 0.979 | What is the average insured value? |
| B15 | ambiguous | correct_clarify | CLARIFY | 0.05 | Total freight cost by region code |
