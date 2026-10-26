# Grounding design

Code: `backend/insightflow/engine/grounding.py` (`Grounder.ground(question) -> Grounding(query, mentions, periods)`).

## Principles

1. **No global synonym replacement.** The question is never rewritten. Words are matched against schema names, their
   schema-derived abbreviations, and stored values. A word the schema does not contain ("revenue", "visits",
   "borrowed") is left unresolved, and the engine asks.
2. **Full accounting.** Every content token must be consumed by one of:
   - a stored value, a period, a number or comparator, a limit;
   - a column, table or role mention;
   - an operation cue (aggregation, grouping, percentage, comparison, negation, time bucket);
   - a light word (function words, generic verbs such as "have", "placed", "included").

   Anything left over produces `unresolved: words not grounded: …` and a clarification.
3. **Negation is never dropped.** A `not`/`no`/`never`/`without` that no condition consumed blocks the answer.
4. **Ambiguity is preserved.** These are reported, never resolved by order or score:
   - candidates that tie (two columns with the same words; a value present in two columns or two roles);
   - two roles with no disambiguating word ("tickets by agent");
   - several date columns with no date named ("monthly gross amount");
   - a stored value that is also an operation word ("Monthly" plan vs monthly series).
5. **Inspectable trace.** Every decision is an `Evidence(span, grounded_to, reason)`. Assumptions (summing when no
   aggregation word was given, inferred joins, how missing values are treated) are listed and turn ANSWER into WARN.

## Pipeline

1. **Normalise surface only.** Remove thousands separators, expand "n't" to "not", turn "%" into "percent", and
   join particles ("check-in" → "checkin").
2. **Values.** Stored values match case-insensitively, with simple plurals. Short all-caps codes need exact case, and
   values that are function words need exact case.
3. **Periods.** Month and quarter ranges, pairs and halves, ISO dates, month-year, year ranges, before/after/since/until,
   bare years. Relative dates are unsupported (no reference date).
4. **Numbers.** Comparators (prefix, or suffix such as "or more", "+"); limits ("top 3", "which 2", "3 highest").
5. **Schema mentions.** Greedy longest span over column and table entries.
   - A span may include "of"/"the" inside it, truncations of short name words ("dist" ← "distance"), derived nouns
     ("renewed" → `renewal_cnt`), and un-/non- prefixes (negation).
   - Unit words attach to the column just named ("duration in minutes"), or name a column alone when exactly one
     measure has that unit ("fare per kilometre").
6. **Assembly.**
   - Value conditions use EXISTS for one-to-many tables. A value right before its own column noun ("the
     Escalations team") consumes the noun.
   - Yes/no columns take their polarity from the name (ok/met/valid …), antonyms (failed/missed/faulty …), participles
     ("paid") and negation.
   - Missing-value phrases become IS NULL. A missing value behind a nullable link is unsupported, because "no row" and
     "empty value" cannot be told apart.
   - Existence: "with/had/no/any <child table>", or the child noun as a participle ("returned", "tagged"), becomes
     `[NOT] EXISTS`.
   - Verb forms of nullable date columns become IS [NOT] NULL. Verb forms of count columns become `= 0` / `> 0`.
   - A number attaches to its unit's column ("30 minutes") or to the nearest measure.
   - The date role must be named (a date column word, or a verb matching a date column) or be the only date
     column. Otherwise the engine asks.
   - Measure, products, ratios, differences, counts, distinct counts, percentages and period comparisons are built as
     in TYPED_QUERY_PLAN.md.
   - Grouping uses cues ("by", "per", "for each") and the entity after a limit ("top 3 accounts"):
     - an entity becomes its display (name) column;
     - "customer segment" means the segment column of customers;
     - an agentive "by" after a participle ("taken by students") is not a grouping;
     - a participle naming a role ("resolved by each agent", "handled by each adjuster") keeps only rows where that
       link exists;
     - a bare id with no lookup cannot label groups (clarify).
7. **Accounting** as above.

## Role disambiguation

When a mention has candidates on several role paths, `_choose_path` scores each by the role words and table or
column words within 3 tokens: "start station" → `start_stn_id`; "ending at Harbor Point" → `end_stn_id`; "resolved by
each agent" → `resolved_by_agent_id`. A tie means ambiguity.

## Date roles: a withdrawn default (recorded decision)

During development I briefly made the base table's only NOT NULL date the default event date ("monthly loans" →
checkout date). I withdrew it for three reasons:
1. My own earlier gym test treated exactly this structure as ambiguous.
2. The external author of the Round 7 set labelled "bookings in March 2025" (NOT NULL `booked_on`, nullable
   `checkin_dt`) as needing clarification. That set is revealed, so this decision also contaminates the Round 7
   diagnostic. It is disclosed in EVALUATION_RESULTS.md.
3. Silent wrong answers cost more than one clarification.

The engine now asks which date is meant whenever more than one date column could apply and none is named. The five
development labels that had assumed the default were changed to "either" (`dev_questions.py`, label history at the end).
