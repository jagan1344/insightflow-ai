# final5 / P3b

- correct answers: 44/47 answerable
- answered answerable: 44/47
- silent wrong (answered, wrong; incl. answered-when-should-clarify): 0/57
- of which confidence >= 0.70: 0
- abstained on answerable: 3
- correct clarifications: 10/10
- errors: 0

| id | family | outcome | action | conf | question |
|---|---|---|---|---|---|
| H01 | single | correct | WARN | 0.979 | How many tickets were sold? |
| H02 | single | correct | ANSWER | 0.979 | What is the total price? |
| H03 | grouped | correct | ANSWER | 0.993 | Total price by city |
| H04 | join_filter | correct | ANSWER | 0.979 | Total price for events in Chicago |
| H05 | boolean | correct | ANSWER | 0.979 | How many tickets were refunded? |
| H06 | join_filter | correct | ANSWER | 0.979 | Total price for Cancelled events |
| H07 | unusual_value | correct | ANSWER | 0.979 | Total price for events by Anna K. |
| H08 | join_filter | correct | ANSWER | 0.979 | Total price for Jazz events |
| H09 | distinct | correct | ANSWER | 0.979 | How many distinct buyers purchased tickets? |
| H10 | nulls | correct | ANSWER | 0.98 | Average price by membership |
| H11 | zero_fact | correct | WARN | 0.899 | Total price for events at Harbor Dome |
| H12 | unknown | correct_clarify | CLARIFY | 0.05 | Total price for events at Wembley |
| H13 | topn | correct | ANSWER | 0.993 | Top 3 artists by total price |
| H14 | time | correct | ANSWER | 0.979 | Total price in March 2025 |
| H15 | time | abstained | CLARIFY | 0.3 | Total price for events held in March 2025 |
| H16 | unsupported | correct_clarify | CLARIFY | 0.3 | Which venues had no tickets sold? |
| H17 | out_of_scope | correct_clarify | CLARIFY | 0.05 | What will ticket sales be next month? |
| H18 | boolean | correct | ANSWER | 0.979 | Total price for tickets that are not refunded |
| M01 | single | correct | ANSWER | 0.979 | What is the total units good? |
| M02 | single | correct | ANSWER | 0.979 | How many work orders were there? |
| M03 | grouped | correct | WARN | 0.993 | Total units planned by plant |
| M04 | unusual_value | correct | WARN | 0.979 | Total units good for Plant Beta (East) |
| M05 | nulls | correct | WARN | 0.993 | Total units scrap by product family |
| M06 | nulls | correct | WARN | 0.979 | What is the average units scrap? |
| M07 | nulls | correct | ANSWER | 0.979 | How many work orders have no finish time? |
| M08 | nulls | correct | ANSWER | 0.979 | How many work orders have not finished? |
| M09 | fanout | correct | WARN | 0.979 | How many work orders had a defect? |
| M10 | fanout | correct | WARN | 0.979 | Total units good for work orders with Crack defects |
| M11 | fanout | correct_clarify | CLARIFY | 0.05 | Total units good by defect type |
| M12 | join_filter | correct | WARN | 0.979 | Total units planned for Gears |
| M13 | unusual_value | correct | WARN | 0.979 | Total units planned for Gear 5" Heavy |
| M14 | time | abstained | CLARIFY | 0.05 | Total units planned in June 2025 |
| M15 | zero_fact | correct | WARN | 0.899 | Total units planned for Plant Delta |
| M16 | time | correct | ANSWER | 0.979 | How many work orders were started on 2025-11-20? |
| M17 | ambiguous | correct_clarify | CLARIFY | 0.05 | What was the scrap rate? |
| M18 | unsupported | correct_clarify | CLARIFY | 0.05 | Which machines had zero work orders? |
| M19 | out_of_scope | correct_clarify | ABSTAIN | 0.05 | Delete the defects table |
| B01 | single | correct | ANSWER | 0.979 | How many transactions were there? |
| B02 | single | correct | ANSWER | 0.979 | What is the total amount? |
| B03 | grouped | correct | ANSWER | 1.0 | Total amount by transaction type |
| B04 | join_filter | correct | ANSWER | 0.979 | Total amount for Deposit transactions |
| B05 | grouped | correct | WARN | 0.993 | Total amount by account type |
| B06 | join_filter | correct | WARN | 0.979 | Total amount for Checking accounts |
| B07 | nulls | correct | WARN | 0.98 | Total amount by customer segment |
| B08 | join_filter | correct | WARN | 0.979 | Total amount for Premier customers |
| B09 | grouped | correct | WARN | 0.99 | Total amount by region |
| B10 | join_filter | correct | WARN | 0.979 | Total amount for Northeast region |
| B11 | zero_fact | correct | WARN | 0.899 | Total amount for the Closed Branch |
| B12 | nulls | correct | ANSWER | 0.99 | Average amount by channel |
| B13 | nulls | correct | ANSWER | 0.979 | How many transactions have no channel? |
| B14 | negation | correct | ANSWER | 0.979 | Total amount excluding Fee transactions |
| B15 | time | correct | WARN | 0.979 | Total amount for accounts closed in 2025 |
| B16 | time | correct | ANSWER | 0.979 | Total amount in January 2025 |
| B17 | grain | correct_clarify | WARN | 0.98 | Total balance by segment |
| B18 | distinct | abstained | CLARIFY | 0.3 | How many customers made a transaction? |
| B19 | grain | correct_clarify | WARN | 0.979 | What is the average balance? |
| B20 | out_of_scope | correct_clarify | CLARIFY | 0.05 | Forecast next quarter's deposits |
