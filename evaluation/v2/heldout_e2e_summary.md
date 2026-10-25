# Held-out generalization — E2E execution accuracy

- **Dataset:** denormalized heldout.db with multi-word, special-character, overlapping-name and zero-fact-row values
- **n_questions:** 28
- **Answered (ANSWER/WARN):** 23 / 28
- **Execution-correct (answerable questions):** 23 / 23 = 100.0%
- **Correct abstentions (expected CLARIFY/ABSTAIN):** 5 / 5

| id | action | exec_ok | question |
|---|---|:---:|---|
| H01 | ANSWER | ✅ | What is the total revenue? |
| H02 | ANSWER | ✅ | How many sales were there? |
| H03 | ANSWER | ✅ | What is the total quantity? |
| H04 | ANSWER | ✅ | What is the average gross amount? |
| H05 | ANSWER | ✅ | What is the maximum gross amount? |
| H06 | ANSWER | ✅ | What is the minimum gross amount? |
| H07 | ANSWER | ✅ | Revenue in East Coast office |
| H08 | ANSWER | ✅ | Revenue in R&D Hardware line |
| H09 | ANSWER | ✅ | Revenue in Men's Apparel line |
| H10 | ANSWER | ✅ | Revenue in North America territory |
| H11 | ANSWER | ✅ | Revenue for Platinum tier customers |
| H12 | CLARIFY | ✅ | Revenue in Antarctica Research Station office |
| H13 | ANSWER | ✅ | How many sales have missing shipping cost? |
| H14 | ANSWER | ✅ | How many customers have missing tier? |
| H15 | ANSWER | ✅ | How many distinct customers do we have? |
| H16 | ANSWER | ✅ | Revenue by office_name |
| H17 | CLARIFY | ✅ | Revenue in Mars office |
| H18 | CLARIFY | ✅ | Revenue in East office |
| H19 | CLARIFY | ✅ | Revenue for Diamond tier customers |
| H20 | CLARIFY | ✅ | Revenue in South Pole office |
| H21 | ANSWER | ✅ | Revenue in East Coast office in Men's Apparel line |
| H22 | ANSWER | ✅ | Revenue in East Coast office in R&D division for Platinum tier custome |
| H23 | ANSWER | ✅ | Revenue in Women's Apparel line |
| H24 | ANSWER | ✅ | Revenue by line_name for APAC HQ office |
| H25 | ANSWER | ✅ | Revenue in North America territory in March 2026 |
| H26 | ANSWER | ✅ | Revenue in the Enterprise division |
| H27 | ANSWER | ✅ | How many sales in EMEA Hub office? |
| H28 | ANSWER | ✅ | Average gross amount in Accessories line |

## Failures (exec_ok=False)
