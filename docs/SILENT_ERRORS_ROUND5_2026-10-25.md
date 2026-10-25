# Silent semantic errors - round 5 (2026-10-25)

Start: `9a13250`, clean and equal to origin; FINAL_SEAL.txt and FINAL4_SEAL.txt verified. Sealed records
(`final_F1_*`, `final4_G1_*`) and their hashes are untouched. Backend code for the new sealed set was frozen at
`dd6ea56`; the set was sealed in `21d057f`; its first run is `9cca989` (recorded before any failure was inspected).

## 1. The five Schema-F (G1) silent errors, reproduced at 36878e7 (38/38 outputs identical)
Artifact: `results/diagnosis_G1_silent_errors_reproduced_at_36878e7.json` (SQL, rows, notes, signals).
| id | system | independent answer | root cause | why it passed |
|---|---|---|---|---|
| F08 loans by branch | 3 groups via loans.branch_id (160/170/170) | via member home branch: 4 groups incl. NULL (122/118/135/125) | two valid routes of different length; shorter chosen silently | the materiality check only handled equal-length routes; breakdown-reconciliation holds for both |
| F09 late fee for Springfield | 745.71 (WARN for NULL share only) | 527.46 via home branch | same | same; the WARN was unrelated |
| F17 distinct books in 2025 | 9 | 9 under loan_date, due_date and returned_date | none: all readings agree | label defect (section 2) |
| F24 top 3 genres by loans | included an unnamed NULL group (56) as a "genre" | 225 / 118 / 55 without NULL | ranking kept the LEFT-JOIN NULL group | no check on NULL group labels |
| F32 loans returned late | 500 (all loans) | 274 (returned_date > due_date) | "returned late" qualifier dropped | column phrase guard needs the full column name |
Fixed in round 4 (post-hoc); round 5 adds regression tests in `tests/test_round5.py` and relatives:
overdue / outstanding / renewed (vocabulary coverage), halves, quarters spelled out, ISO dates, "shipped"/"not returned"
(date-state IS [NOT] NULL), percentage and top-N cues, "and not X", "each X", "total per row", "had a defect".

## 2. Label disagreements (nothing edited; `results/label_review_round5.md`, script `label_review.py`)
| id | verdict | evidence | effect |
|---|---|---|---|
| F17 | defective label | 9 under all three date columns; policy is to answer when readings agree | G1: silent wrong 5/38 -> 4/38, correct 18/27 -> 19/28, clarifications 8/11 -> 8/10 |
| C25 | defective label | single reading; 647351.92 by independent SQL; label encoded the then-missing capability | F1: correct 17/24 -> 17/25, abstained 4 -> 5, clarifications 8/8 -> 7/7 |
| H15 (round 5) | ambiguous wording ("held" verb or status 'Held') | 9274.14 vs 5731.77 | H1: answerable 47 -> 45 with H15, M14 moved to clarify; silent wrong stays 3/57 |
| M14 (round 5) | ambiguous (started_at vs finished_at) | 8320 vs 8199 | first-run abstention becomes a correct clarification |
Original figures are reported next to every corrected figure; none of the corrections is applied to the sealed files.

## 3. New untouched set: three unfamiliar schemas (events, factory, bank), 57 questions
Sealed before the first run (`FINAL5_SEAL.txt`), recorded before inspection.
| run | correct/answerable | answered/answerable | silent wrong | abstained (answerable) | correct clarifications | latency p50/p95 |
|---|---|---|---|---|---|---|
| **H1 first run** | **39/47** | 42/47 | **3/57** | 5 | 10/10 | 12/31 ms |
| H1 re-scored with proposed label corrections | 39/45 | 41/45 | 3/57 | 4 | 11/12 | |
| H3 after fixes (NOT held out) | 43/47 | 43/47 | 0/57 | 4 | 10/10 | 14/36 ms |
H1 failures: H15 (lowercase "held" read as status value; label disputed), H18 (SUM(refunded) used as the price: 0/1 flag and
"not" ignored), B03 ("by transaction type" dropped, scalar total), plus abstentions M07 (no finish time), M09 (had a defect),
M14 (disputed), B14 (exclusion followed by "transactions" mis-read as a KPI), B18 (customers two hops away).
Fixes: 0/1 columns become conditions; "not X" on a used measure is vetoed; "by <phrase>" with no grouping is vetoed;
value exclusions no longer collide with KPI nouns; has/lacks child rows (NOT EXISTS); inflected date phrases; lowercase
word equal to a status value is run with and without the filter and asked only if the answers differ.
Remaining after fixes: H15 and M14 are (correctly) asked; B03 and B18 clarify (coverage gap, not wrong).

## 4. All first runs pooled (SUMMARY_round5.md)
Answers scoring >= 0.9: 134, of which 111 correct and 21 silently wrong (16%); mean score of wrong answers (0.979-0.993)
is never lower than of correct ones (0.975-0.979). The score is an execution/plan-agreement signal, not a probability;
it was not recalibrated. Protection is the veto layer plus WARN caveats.

## 5. Coverage trade-off
Vocabulary coverage is applied only to registered relational data (flat uploads keep legacy phrase rules) and treats
-ed / irregular-past words as caveats (WARN) and other unmapped words as clarifications. Its false-clarification cost
was measured while building: one dev regression ("across") fixed by extending the function-word list. In the tuned runs
answerable questions not answered: C 0/24, F 2/27, round-5 set 4/47, dev4 1/46, dev 1/25, adversarial 0/15. Because
the function-word list was extended using dev failures, the first-run H1 number is the unbiased one.

## 6. Query safety
`tests/test_round5b.py` runs destructive and injection wording ("Delete the defects table", "...; DROP TABLE transactions",
"Update every balance to zero") and asserts row counts unchanged, no write keyword in generated SQL; the executor stays
read-only (PRAGMA query_only), time-limited and cost-checked (tests from round 3 pass).

## 7. Remaining errors / limits
F17, C25 (label issues); H15 first-run silent answer; unprobed classes certainly exist (every round of probing found new
ones). Unsupported or abstaining: customers/entities more than one hop from the base table, abbreviations such as
"transaction type" for txn_type, wording-to-column mappings that are not prefix/stem related, ratio definitions,
anti-joins on dimensions, hierarchies, multi-year lists, non-English text, non-SQLite databases.

## 8. Tests and reproduction
Backend suite: 437 passed, 0 failed (420 at start of this round's coding, 400 at round-4 close). Historical
27/27, 25/25 and 23/23-answerable benchmarks unchanged.
    cd backend && python -m pytest -q
    cd ../evaluation/v3 && sha256sum -c FINAL_SEAL.txt FINAL4_SEAL.txt FINAL5_SEAL.txt
    python run_r5.py final5 <label>      # events/factory/bank; first run needs backend at dd6ea56
    python label_review.py > results/label_review_round5.md
    python calibration_report.py > results/SUMMARY_round5.md
