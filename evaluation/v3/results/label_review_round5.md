# Label review (round 5) - proposed corrections; sealed records unchanged

- **F17** (final4_G1_first_and_only): defective label (underspecified question whose readings all agree). 3 date columns give identical distinct-book counts {'loan_date': 9, 'due_date': 9, 'returned_date': 9}; the stated policy is to answer when every reading agrees. Original label (CLARIFY) contradicted that policy.
- **C25** (final_F1_first_and_only): defective label (question is unambiguous; label encoded then-missing capability). 'excluding California students' has one reading; independent SQL gives 647351.92. The original label expected CLARIFY only because exclusion was unsupported.
- **H15** (final5_H1_first_and_only): defective label (ambiguous wording: 'held' = ordinary verb or status value 'Held'). independent SQL: 9274.14 without the status filter vs 5731.77 with status='Held'; the readings differ, so by the stated policy a clarification is the correct response.
- **M14** (final5_H1_first_and_only): defective label (two date columns on the base table; readings differ). independent SQL: units planned in June 2025 is 8320 by started_at and 8199 by finished_at; the question names neither, so a clarification is the correct response.


### final4_G1_first_and_only

| | answerable | correct | answered | silent wrong | abstained (answerable) | clarifications correct |
|---|---|---|---|---|---|---|
| original label (as sealed, as first reported) | 27 | 18/27 | 20/27 | 5/38 | 7 | 8/11 |
| proposed corrected label | 28 | 19/28 | 21/28 | 4/38 | 7 | 8/10 |

### final_F1_first_and_only

| | answerable | correct | answered | silent wrong | abstained (answerable) | clarifications correct |
|---|---|---|---|---|---|---|
| original label (as sealed, as first reported) | 24 | 17/24 | 20/24 | 3/32 | 4 | 8/8 |
| proposed corrected label | 25 | 17/25 | 20/25 | 3/32 | 5 | 7/7 |

### final5_H1_first_and_only

| | answerable | correct | answered | silent wrong | abstained (answerable) | clarifications correct |
|---|---|---|---|---|---|---|
| original label (as sealed, as first reported) | 47 | 39/47 | 42/47 | 3/57 | 5 | 10/10 |
| proposed corrected label | 45 | 39/45 | 41/45 | 3/57 | 4 | 11/12 |
