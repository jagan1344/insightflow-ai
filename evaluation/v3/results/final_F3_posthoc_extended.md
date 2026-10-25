# final / F3_posthoc_extended

- correct answers: 24/24 answerable
- answered answerable: 24/24
- silent wrong (answered, wrong; incl. answered-when-should-clarify): 1/32
- of which confidence >= 0.70: 1
- abstained on answerable: 0
- correct clarifications: 7/8
- errors: 0

| id | family | outcome | action | conf | question |
|---|---|---|---|---|---|
| C01 | single | correct | ANSWER | 0.979 | What is the total tuition paid? |
| C02 | single | correct | ANSWER | 0.979 | How many enrollments were there? |
| C03 | nulls | correct | ANSWER | 0.979 | What is the average grade points? |
| C04 | grouped | correct | ANSWER | 1.0 | Total tuition paid by home state |
| C05 | join_filter | correct | ANSWER | 0.979 | Total tuition paid by students from California |
| C06 | join_filter | correct | ANSWER | 0.979 | Total tuition paid for the course Calculus I |
| C07 | unusual_value | correct | ANSWER | 0.979 | Total tuition paid for Art History: 1800–1900 |
| C08 | unusual_value | correct | ANSWER | 0.979 | Total tuition paid for Women's Studies |
| C09 | fanout | correct | ANSWER | 0.979 | Total tuition paid for courses taught by Prof. Ngozi Eze-Bello |
| C10 | distinct | correct | ANSWER | 0.979 | How many distinct students enrolled in Calculus I? |
| C11 | topn | correct | ANSWER | 0.993 | Top 3 home states by total tuition paid |
| C12 | ambiguous | correct_clarify | CLARIFY | 0.05 | Total tuition paid by department |
| C13 | ambiguous | correct_clarify | CLARIFY | 0.05 | Total tuition paid for Computer Science |
| C14 | zero_fact | correct | WARN | 0.899 | Total tuition paid for Classics |
| C15 | unknown | correct_clarify | CLARIFY | 0.05 | Total tuition paid for Linguistics |
| C16 | ambiguous | correct_clarify | CLARIFY | 0.05 | Total tuition paid in March 2025 |
| C17 | time | correct | ANSWER | 0.979 | Total tuition paid for enrollments completed in May 2025 |
| C18 | nulls | correct | ANSWER | 1.0 | Average grade points by home state |
| C19 | nulls | correct | ANSWER | 0.979 | How many enrollments have no grade points? |
| C20 | grain | correct_clarify | CLARIFY | 0.05 | How many students are there? |
| C21 | foreign_measure | correct | ANSWER | 0.979 | Total credits enrolled |
| C22 | numeric_filter | correct | ANSWER | 0.979 | Total tuition paid for 4 credit courses |
| C23 | grouped | correct | ANSWER | 1.0 | Average tuition paid by home state |
| C24 | multi_value | correct | ANSWER | 0.979 | Total tuition paid by students from Texas and Ohio |
| C25 | negation | silent_wrong | ANSWER | 0.979 | Total tuition paid excluding California students |
| C26 | single | correct | ANSWER | 0.979 | What is the maximum tuition paid? |
| C27 | unusual_value | correct | ANSWER | 0.979 | Total tuition paid by O'Neil, Sam |
| C28 | unknown | correct_clarify | CLARIFY | 0.05 | Total tuition paid by students from Atlantis |
| C29 | empty | correct | WARN | 0.899 | Total tuition paid for enrollments completed in 2031 |
| C30 | fanout | correct_clarify | CLARIFY | 0.05 | Total tuition paid by instructor |
| C31 | topn | correct | ANSWER | 0.986 | Top 2 courses by total tuition paid |
| C32 | topn | correct | ANSWER | 0.979 | Which home state has the highest average grade points? |
