# v5 diagnostic set: frozen first run (38b60d1) vs POST-HOC DEVELOPMENT result (da925ad)

The 105 v5 questions were inspected and used to guide the changes, so the post-hoc column is NOT held-out evidence; it shows what the changes do on the questions that motivated them.

| measure | first run 38b60d1 | post-hoc da925ad |
|---|---|---|
| correct / 74 answerable | 14 | 63 |
| answered / 74 answerable | 17 | 64 |
| wrong values / 74 answerable | 3 | 1 |
| answers to clarify items / 31 | 4 | 1 |
| wrong answers / 105 | 7 | 2 |
| appropriate refusals / 31 | 27 | 30 |
| unnecessary clarifications / 74 | 57 | 10 |
| latency p50 ms | 54.1 | 214.3 |
| latency p95 ms | 660.2 | 795.6 |

## Paired transitions

| first run -> post-hoc | n | ids |
|---|---|---|
| unnecessary_clarify -> correct | 47 | HO01 HO02 HO03 HO05 HO06 HO07 HO09 HO11 HO12 HO13 HO14 HO15 HO16 HO18 HO19 HO25 IN01 IN02 IN06 IN10 IN11 IN12 IN13 IN15 IN17 IN20 IN21 EN01 EN02 EN04 EN05 EN08 EN09 EN13 EN14 EN17 EN18 RI04 RI05 RI08 RI10 RI11 RI14 RI15 RI17 RI20 RI23 |
| correct_clarify -> correct_clarify | 27 | (unchanged) |
| correct -> correct | 14 | (unchanged) |
| unnecessary_clarify -> unnecessary_clarify | 10 | (unchanged) |
| wrong_answer_to_clarify_item -> correct_clarify | 3 | HO21 IN28 RI24 |
| silent_wrong -> correct | 2 | IN14 RI12 |
| silent_wrong -> silent_wrong | 1 | (unchanged) |
| wrong_answer_to_clarify_item -> wrong_answer_to_clarify_item | 1 | (unchanged) |

Correct answers gained: 49; lost: 0. Wrong answers eliminated: 5; new wrong answers: 0.

Remaining wrong answers: HO08 (date role chosen from the noun 'bookings', a documented design rule that the author's label disputes) and IN04 (correct measure; the system keeps the NULL group of unassigned claims, the author's inner-join reference drops it - a convention disagreement, not changed in either direction).

Remaining unnecessary clarifications (10): HO20, IN18 (a part of the composite is itself ambiguous: date role / 'denied' as value or word), IN07 (date difference), IN08 (parent-entity measure), IN26 (child-table measure), EN10 (threshold on a 3-hop numeric attribute written as 'priced above 0.20 per kWh'), EN12 ('per kWh' without a stated formula; author-flagged borderline), EN24 ('actual readings' unmapped), RI02 (unit conversion minutes -> hours), RI16 ('started at' role not resolved).
