# 06 — Error analysis of the v5 first run (A0, frozen 38b60d1)

Inspection happened only after the raw output was committed (`4bbba9c`) and scored (`v5_A0_first_run.summary.json`).
No reference answer or label was changed. Figure: `figures/fig7_outcomes_by_category.pdf`.

## Headline (denominators stated; Wilson 95% intervals)
| metric | value |
|---|---|
| correct / answerable | 14/74 = 18.9% [11.6, 29.3] |
| answered / answerable (coverage) | 17/74 = 23.0% |
| correct / answered answerable | 14/17 = 82.4% [59.0, 93.8] |
| wrong answers / all questions | 7/105 = 6.7% [3.3, 13.1] (3 wrong values on answerable items + 4 answers to clarify items) |
| appropriate refusals | 27/31 (clarify 15/19, unsupported 12/12) |
| unnecessary clarifications | 57/74 |
| errors / crashes | 0 |
| latency p50 / p95 / max | 54 / 660 / 2,076 ms |

Sensitivity, pre-registered (the 20 items the author flagged as borderline removed; 85 questions remain):
14/65 correct, 16/65 answered, 5/85 wrong answers, 17/20 appropriate refusals, 49/65 unnecessary clarifications.
The conclusions do not depend on the borderline labels.

## The 7 wrong answers
| id | category | what happened | class |
|---|---|---|---|
| RI12 | negation | "completed trips not paid in cash" -> `pay_method = 'Cash'` (204 vs 1039): negation on a value filter lost | polarity inversion |
| IN04 | fk_inference | "total claimed amount by adjuster" -> COUNT(*) per adjuster: the measure phrase "claimed amount" did not bind to `claim_amt`, the planner fell back to a row count; confidence 0.996 | wrong measure (fallback) |
| IN14 | distinct_count | correct COUNT(DISTINCT policy_no) = 437, but an unrequested SUM column was appended, so the reported figure is the sum | extra unrequested measure |
| RI24 | ratio | "tip rate" -> SUM(tip_amt) | ratio answered as a sum |
| HO08 | date role | "bookings ... in March 2025" with two date columns -> booked_on chosen without asking (label: clarify) | date role guessed |
| HO21 | ambiguous | "Which hotel is doing best?" -> booking count by hotel (label: clarify) | vague metric filled by default |
| IN28 | ambiguous (borderline) | "What's the average claim?" -> AVG(claim_amt); label says clarify (author flags it borderline) | label-dependent |

Four of these (IN04, IN14, RI24, HO08) are classes the semantic layer should cover in principle, but
`distinct_count` is outside the layer's intent allow-list (IN14), and the measure-fallback (IN04) and
"rate" wording (RI24) are not modelled by the type checks.

## Why 57 answerable questions were clarified
| cause (first veto / refusal reason) | count |
|---|---|
| planner could not bind a measure ("too vague or off-scope"): paraphrases such as "amount claimed", "kilowatt-hours", "room nights", "reservations", "paid out", "percentage of" | 20 |
| unexplained-word heuristic flagged ordinary words ("break down", "came from", "ones", "leave out", "least", "minus", "blank") | 11 |
| plan requires an item it could not bind (dimension words such as "check-in month", "for", "total"; negative existence "haven't been assigned"; role-ambiguous zone values) | 11 |
| column word mentioned but not used ("fares", "method", "installation date") | 7 |
| number not used (thresholds on related tables written as "1,000", "4.8", "40 square metres") | 3 |
| compile failure, ambiguity (readings differ), wording audit, table noun, semantic layer | 1 each |

Interpretation: on schemas and wording the developer did not write, lexical grounding is the main
bottleneck. The vetoes that prevent most wrong answers are the same heuristics that cause most unnecessary
clarifications; they trade coverage for safety. The prior sealed first runs (42/54 on K1) were on schemas
authored in the same process as the implementation and therefore overstate coverage on unfamiliar data.

## Representative traces
Stored in `eval/results/v5_A0_first_run.json` (fields `sql`, `reason`, `semantic_findings`, `signals`).
