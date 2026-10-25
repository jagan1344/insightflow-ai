# adversarial / A9

- correct answers: 15/15 answerable
- answered answerable: 15/15
- silent wrong (answered, wrong; incl. answered-when-should-clarify): 0/20
- of which confidence >= 0.70: 0
- abstained on answerable: 0
- correct clarifications: 5/5
- errors: 0

| id | family | outcome | action | conf | question |
|---|---|---|---|---|---|
| X01 | multi_value | correct | ANSWER | 0.979 | Total fee for Cardiology doctors and Pediatrics doctors |
| X02 | multi_value | correct | WARN | 0.979 | Total freight cost for Gold tier customers and Silver tier customers |
| X03 | unusual_value | correct_clarify | CLARIFY | 0.05 | Total fee for patients insured by Cigna'; DROP TABLE visits;-- |
| X04 | misleading | correct_clarify | CLARIFY | 0.05 | What was the total fee not including copay? |
| X05 | unfamiliar_term | correct_clarify | CLARIFY | 0.05 | What are the total charges? |
| X06 | empty | correct | WARN | 0.899 | Total fee for visits in June 2031 |
| X07 | nulls | correct | ANSWER | 0.979 | How many visits have no discharge date? |
| X08 | nulls | correct | WARN | 0.979 | What is the average copay for Cardiology doctors? |
| X09 | nulls | correct | ANSWER | 0.979 | How many shipments have no insured value? |
| X10 | unusual_value | correct | ANSWER | 0.979 | Total fee for Dr. K. Okafor-11 |
| X11 | unusual_value | correct | WARN | 0.979 | Total freight cost for carrier Sky Cargo (Intl) |
| X12 | wording | correct | ANSWER | 0.979 | TOTAL FEE FOR CARDIOLOGY DOCTORS |
| X13 | wording | correct | ANSWER | 0.979 | total   fee   for   cardiology    doctors |
| X14 | complex | correct | ANSWER | 0.993 | Top 3 specialties by total fee for visits in March 2025 |
| X15 | complex | correct | ANSWER | 1.0 | Average fee per visit by specialty |
| X16 | complex | correct | ANSWER | 0.979 | Total freight cost for shipments delivered in June 2025 |
| X17 | paraphrase | correct | WARN | 1.0 | Total freight cost by destination hub |
| X18 | ambiguous | correct_clarify | CLARIFY | 0.05 | Total freight cost for the Hamburg Terminal |
| X19 | grain | correct_clarify | CLARIFY | 0.05 | How many parcels are there? |
| X20 | nulls | correct | ANSWER | 0.979 | What is the average weight? |
