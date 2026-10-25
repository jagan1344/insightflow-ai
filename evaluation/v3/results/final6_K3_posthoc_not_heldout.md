# final6 / K3_posthoc_not_heldout

- correct answers: 49/54 answerable
- answered answerable: 49/54
- silent wrong (answered, wrong; incl. answered-when-should-clarify): 0/66
- of which confidence >= 0.70: 0
- abstained on answerable: 5
- correct clarifications: 12/12
- errors: 0

| id | family | outcome | action | conf | question |
|---|---|---|---|---|---|
| A01 | single | correct | ANSWER | 0.979 | How many flights were there? |
| A02 | single | correct | ANSWER | 0.979 | What is the total fare? |
| A03 | flag | correct | ANSWER | 0.979 | How many flights were cancelled? |
| A04 | flag | correct | ANSWER | 0.979 | How many flights were not delayed? |
| A05 | flag | correct | ANSWER | 0.979 | Total fare for cancelled flights |
| A06 | grouped | correct | WARN | 1.0 | Total fare by carrier |
| A07 | join_filter | correct | WARN | 0.979 | Total fare for the Oneworld alliance |
| A08 | nulls | correct | WARN | 0.98 | Total fare by alliance |
| A09 | zero_fact | correct | WARN | 0.899 | Total fare for Ghost Air |
| A10 | unknown | correct_clarify | CLARIFY | 0.05 | Total fare for Lufthansa |
| A11 | undetected_fk | abstained | CLARIFY | 0.3 | Total fare by origin airport |
| A12 | abbreviation | abstained | CLARIFY | 0.05 | Total passengers |
| A13 | single | abstained | CLARIFY | 0.3 | Average fare per flight |
| A14 | ambiguous | correct_clarify | CLARIFY | 0.05 | Total fare in March 2025 |
| A15 | time | correct | ANSWER | 0.979 | Total fare for flights departing in March 2025 |
| A16 | topn | correct | WARN | 0.986 | Top 2 carriers by total fare |
| A17 | negation | correct | ANSWER | 0.979 | Total fare excluding cancelled flights |
| A18 | flag | correct | ANSWER | 0.979 | What is the average fare for delayed flights? |
| A19 | unsupported | correct_clarify | CLARIFY | 0.05 | Which airports had no departures? |
| A20 | out_of_scope | correct_clarify | CLARIFY | 0.05 | Predict next month's bookings |
| S01 | single | correct | ANSWER | 0.979 | What is the total usd? |
| S02 | single | correct | ANSWER | 0.979 | How many invoices were there? |
| S03 | nulls | correct | ANSWER | 0.979 | How many invoices have not been paid? |
| S04 | grouped | correct | ANSWER | 0.993 | Total usd by plan |
| S05 | unusual_value | correct | ANSWER | 0.979 | Total usd for the Enterprise (Annual) plan |
| S06 | grouped | correct | ANSWER | 1.0 | Total usd by country |
| S07 | join_filter | correct | ANSWER | 0.979 | Total usd for Germany |
| S08 | related_flag | correct | ANSWER | 0.979 | Total usd for trial subscriptions |
| S09 | fanout | correct | ANSWER | 0.979 | Total usd for accounts with Open tickets |
| S10 | fanout | correct_clarify | CLARIFY | 0.05 | Total usd by priority |
| S11 | ambiguous | correct_clarify | CLARIFY | 0.05 | Total usd in June 2025 |
| S12 | time | correct | ANSWER | 0.979 | Total usd for invoices issued in June 2025 |
| S13 | time | correct | ANSWER | 0.979 | Total usd for invoices paid in June 2025 |
| S14 | grain | correct_clarify | ABSTAIN | 0.05 | What is the average monthly price? |
| S15 | grain | correct_clarify | WARN | 0.979 | What is the total seats? |
| S16 | join_filter | correct | ANSWER | 0.979 | Total usd for the Software industry |
| S17 | zero_fact | correct | WARN | 0.899 | Total usd for the Legacy plan |
| S18 | negation | correct | ANSWER | 0.979 | Total usd excluding the Starter plan |
| S19 | distinct | correct | WARN | 0.979 | How many distinct accounts were invoiced? |
| S20 | unsupported | correct_clarify | CLARIFY | 0.05 | Which accounts have no tickets? |
| R01 | single | correct | ANSWER | 0.979 | How many readings were there? |
| R02 | single | correct | ANSWER | 0.979 | What is the average moisture? |
| R03 | abbreviation | correct | WARN | 0.979 | What is the average temperature? |
| R04 | nulls | correct | ANSWER | 0.979 | How many readings have no temperature? |
| R05 | flag | abstained | CLARIFY | 0.3 | How many readings had a faulty sensor? |
| R06 | grouped | correct | ANSWER | 1.0 | Average moisture by crop |
| R07 | grouped | correct | ANSWER | 0.986 | Average moisture by region |
| R08 | join_filter | correct | ANSWER | 0.979 | Average moisture for Corn |
| R09 | unusual_value | correct | ANSWER | 0.979 | Average moisture for O'Neil Family Farm |
| R10 | zero_fact | correct | WARN | 0.899 | Average moisture for Fallow Ridge |
| R11 | unusual_value | correct | ANSWER | 0.979 | Average moisture for Riverbend (North) |
| R12 | time | correct | ANSWER | 0.979 | Average moisture in July 2025 |
| R13 | negation | correct | ANSWER | 0.979 | Average moisture excluding Cotton |
| R14 | grain | correct_clarify | WARN | 0.979 | What is the total acres? |
| R15 | numeric_filter | abstained | CLARIFY | 0.3 | Average moisture for fields larger than 100 acres |
| R16 | numeric_filter | correct | ANSWER | 0.979 | Average moisture for fields with more than 100 acres |
| R17 | topn | correct | ANSWER | 0.986 | Top 2 crops by average moisture |
| R18 | time | correct | ANSWER | 0.979 | How many readings were taken on 2025-11-20? |
| R19 | unsupported | correct_clarify | CLARIFY | 0.05 | Which farms had no readings? |
| V01 | single | correct | ANSWER | 0.979 | What is the total yield tons? |
| V02 | grouped | correct | ANSWER | 1.0 | Total yield tons by crop |
| V03 | grouped | correct | ANSWER | 0.986 | Total yield tons by region |
| V04 | join_filter | correct | ANSWER | 0.979 | Total yield tons for Soy |
| V05 | time | correct | ANSWER | 0.979 | Total yield tons in October 2025 |
| V06 | single | correct | ANSWER | 0.979 | How many harvests were there? |
| V07 | ambiguous | correct_clarify | CLARIFY | 0.3 | Total yield tons per acre |
