# final4 / P2

- correct answers: 25/27 answerable
- answered answerable: 25/27
- silent wrong (answered, wrong; incl. answered-when-should-clarify): 1/38
- of which confidence >= 0.70: 1
- abstained on answerable: 2
- correct clarifications: 10/11
- errors: 0

| id | family | outcome | action | conf | question |
|---|---|---|---|---|---|
| F01 | single | correct | ANSWER | 0.979 | How many loans were there? |
| F02 | nulls | correct | WARN | 0.979 | What is the total late fee? |
| F03 | nulls | correct | WARN | 0.979 | What is the average late fee? |
| F04 | nulls | correct | ANSWER | 0.979 | How many loans have no return date? |
| F05 | grouped | correct | WARN | 0.992 | Total late fee by genre |
| F06 | unusual_value | correct | ANSWER | 0.979 | How many loans of books in Sci-Fi & Fantasy? |
| F07 | unusual_value | correct | ANSWER | 0.979 | How many loans of Children's books? |
| F08 | ambiguous | correct_clarify | CLARIFY | 0.3 | How many loans by branch? |
| F09 | ambiguous | correct_clarify | CLARIFY | 0.3 | Total late fee for Springfield |
| F10 | join_filter | correct | ANSWER | 0.979 | How many loans by Gold tier members? |
| F11 | fanout | correct | WARN | 0.979 | How many loans of books by Ursula K. Le Guin? |
| F12 | fanout | correct_clarify | CLARIFY | 0.05 | Loans by author |
| F13 | ambiguous | correct_clarify | CLARIFY | 0.05 | Total late fee in March 2025 |
| F14 | time | correct | ANSWER | 0.979 | How many loans were made in March 2025? |
| F15 | time | correct | ANSWER | 0.979 | How many loans were returned in April 2025? |
| F16 | distinct | correct | ANSWER | 0.979 | How many distinct members borrowed books? |
| F17 | ambiguous | silent_wrong | WARN | 0.979 | How many distinct books were borrowed in 2025? |
| F18 | numeric_filter | abstained | CLARIFY | 0.05 | Total late fee for books published after 2000 |
| F19 | numeric_filter | correct | WARN | 0.979 | Total late fee for books priced over 20 |
| F20 | numeric_filter | correct | WARN | 0.979 | Total late fee for books with price over 20 |
| F21 | negation | correct | WARN | 0.979 | Total late fee excluding Poetry |
| F22 | zero_fact | correct | WARN | 0.899 | Total late fee for Poetry |
| F23 | unknown | correct_clarify | CLARIFY | 0.05 | Total late fee for Cooking |
| F24 | topn | correct | ANSWER | 0.993 | Top 3 genres by number of loans |
| F25 | unsupported | correct_clarify | CLARIFY | 0.05 | Which members have never borrowed a book? |
| F26 | out_of_scope | correct_clarify | CLARIFY | 0.05 | What will late fees be next year? |
| F27 | out_of_scope | correct_clarify | ABSTAIN | 0.05 | Remove all overdue loans |
| F28 | nulls | correct | WARN | 0.98 | Average late fee by tier |
| F29 | numeric_filter | correct | ANSWER | 0.979 | How many loans had a late fee over 5? |
| F30 | numeric_filter | correct | WARN | 0.979 | Total late fee for loans with late fee over 5 |
| F31 | unknown | correct_clarify | CLARIFY | 0.05 | How many loans of Tolkien's books? |
| F32 | column_compare | abstained | CLARIFY | 0.3 | How many loans were returned late? |
| F33 | ambiguous | correct_clarify | CLARIFY | 0.05 | Average late fee for Gold tier members in 2025 |
| F34 | join_filter | correct | WARN | 0.979 | Average late fee for Gold tier members |
| F35 | single | correct | ANSWER | 0.979 | What is the maximum late fee? |
| F36 | multi_value | correct | WARN | 0.979 | Total late fee for Silver or Gold tier members |
| F37 | time | correct | WARN | 0.979 | Total late fee for members who joined in 2024 |
| F38 | combo | correct | ANSWER | 0.979 | How many loans of Sci-Fi & Fantasy books by Gold tier members? |
