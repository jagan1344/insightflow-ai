# dev4 / R6

- correct answers: 45/46 answerable
- answered answerable: 45/46
- silent wrong (answered, wrong; incl. answered-when-should-clarify): 0/59
- of which confidence >= 0.70: 0
- abstained on answerable: 1
- correct clarifications: 13/13
- errors: 0

| id | family | outcome | action | conf | question |
|---|---|---|---|---|---|
| D01 | single | correct | ANSWER | 0.979 | What are the total gross sales? |
| D02 | single | correct | ANSWER | 0.979 | What are the net sales? |
| D03 | grouped | correct | ANSWER | 1.0 | Net sales by category |
| D04 | unusual_value | correct | ANSWER | 0.979 | Gross sales for Kids' Toys |
| D05 | unusual_value | correct | ANSWER | 0.979 | Gross sales for Audio (Hi-Fi) |
| D06 | grouped | correct | ANSWER | 0.993 | Net sales by region |
| D07 | nulls | correct | ANSWER | 0.98 | Gross sales by customer segment |
| D08 | ambiguous | correct_clarify | CLARIFY | 0.05 | Gross sales in June 2025 |
| D09 | time | correct | ANSWER | 0.979 | Gross sales for orders placed in June 2025 |
| D10 | time | correct | ANSWER | 0.979 | Gross sales for orders shipped in July 2025 |
| D11 | grain | correct_clarify | WARN | 0.979 | What is the total shipping fee? |
| D12 | single | correct | ANSWER | 0.979 | What is the total shipping fee? |
| D13 | single | correct | ANSWER | 0.979 | How many orders were there? |
| D14 | grouped | correct | ANSWER | 0.993 | Total shipping fee by store region |
| D15 | nulls | correct | ANSWER | 0.979 | How many orders had no customer? |
| D16 | distinct | correct | ANSWER | 0.979 | How many distinct customers placed orders? |
| D17 | join_filter | correct | ANSWER | 0.979 | Gross sales for Wholesale customers |
| D18 | negation | correct | ANSWER | 0.979 | Net sales excluding Kids' Toys |
| D19 | single | correct | ANSWER | 0.979 | How many order lines were there? |
| D20 | distinct | correct | ANSWER | 0.979 | How many distinct products were sold? |
| D21 | out_of_scope | correct_clarify | CLARIFY | 0.05 | What will net sales be next quarter? |
| D22 | out_of_scope | correct_clarify | ABSTAIN | 0.05 | Delete all orders |
| D23 | unsupported | correct_clarify | CLARIFY | 0.05 | Which stores had no sales? |
| D24 | zero_fact | correct | WARN | 0.899 | Net sales for the Closed Outlet store |
| D25 | unknown | correct_clarify | CLARIFY | 0.05 | Net sales for the Mars Store |
| D26 | topn | correct | ANSWER | 0.993 | Top 3 products by gross sales |
| D27 | single | correct | ANSWER | 0.979 | What is the average unit price? |
| D28 | single | correct | ANSWER | 0.979 | What is the total quantity? |
| D29 | numeric_filter | correct | ANSWER | 0.979 | Total quantity for products with list price above 50 |
| D30 | numeric_filter | abstained | CLARIFY | 0.3 | Total quantity for products priced above 50 |
| D31 | combo | correct | ANSWER | 0.979 | Gross sales for orders placed in June 2025 excluding Online Store |
| D32 | ambiguous | correct_clarify | CLARIFY | 0.05 | What is the total revenue? |
| E01 | single | correct | ANSWER | 0.979 | What is the total salary? |
| E02 | single | correct | ANSWER | 0.979 | How many employees are there? |
| E03 | nulls | correct | ANSWER | 0.992 | Average salary by department |
| E04 | join_filter | correct | ANSWER | 0.979 | Total salary for Engineering |
| E05 | nulls | correct | WARN | 0.979 | What is the average bonus? |
| E06 | nulls | correct | ANSWER | 0.979 | How many employees have no bonus? |
| E07 | time | correct | ANSWER | 0.979 | Average salary of employees hired in 2023 |
| E08 | time | correct | ANSWER | 0.979 | How many employees were hired in March 2022? |
| E09 | unusual_value | correct | ANSWER | 0.979 | Total salary for Sales & Marketing |
| E10 | zero_fact | correct | WARN | 0.899 | Total salary for R&D Lab (Intl.) |
| E11 | unsupported | correct_clarify | CLARIFY | 0.05 | How many employees report to Dana Reyes? |
| E12 | negation | correct | ANSWER | 0.979 | Total salary excluding Terminated employees |
| E14 | single | correct | ANSWER | 0.979 | What are the total hours? |
| E15 | grouped | correct | ANSWER | 1.0 | Total hours by project |
| E16 | ambiguous | correct_clarify | CLARIFY | 0.05 | Total hours by department |
| E17 | ambiguous | correct_clarify | CLARIFY | 0.05 | Total hours for Engineering |
| E18 | join_filter | correct | ANSWER | 0.979 | Total hours for project Apollo |
| E19 | join_filter | correct | ANSWER | 0.979 | Total hours for Active employees |
| E20 | single | correct | ANSWER | 0.979 | What is the average hours per assignment? |
| E21 | distinct | correct | ANSWER | 0.979 | How many distinct employees worked on Apollo? |
| E22 | time | correct | ANSWER | 0.979 | Total hours in June 2025 |
| E23 | unsupported | correct_clarify | CLARIFY | 0.05 | Total salary by manager |
| E24 | single | correct | ANSWER | 0.979 | What is the highest salary? |
| E25 | out_of_scope | correct_clarify | CLARIFY | 0.05 | Predict next year's headcount |
| E26 | numeric_filter | correct | ANSWER | 0.979 | Total salary for employees with bonus over 5000 |
| E27 | time | correct | ANSWER | 0.979 | Total hours for employees hired in 2024 |
| E28 | ambiguous | correct_clarify | CLARIFY | 0.05 | Total hours for projects of the Legal department |
