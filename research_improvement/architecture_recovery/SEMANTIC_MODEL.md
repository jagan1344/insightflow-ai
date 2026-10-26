# Schema semantic model

Code: `backend/insightflow/engine/schema_model.py` (model), `backend/insightflow/engine/lexicon.py` (which words can
name which element), `backend/insightflow/engine/words.py` (shared word layer).

## Established facts and inferences are kept apart

`SchemaModel.describe()` reports both, and every inferred join is marked `(inferred)` in paths, SQL evidence and the
answer's caveats.

| Established (read from SQLite) | Inferred (heuristic, inspectable) |
|---|---|
| tables, columns, declared SQL types | column kind: id / measure / boolean / date / category / text |
| primary keys | units (`_min`, `_km`, `_pct`, …) and money-likeness (`amt`, `fee`, `price`, …) |
| declared foreign keys | undeclared foreign keys (rules below) |
| NOT NULL | stored values used for grounding (categories, ≤ 400 distinct) |

No metric is invented. The model only knows columns and their kinds. It defines no "revenue", "churn", "loyalty"
or "efficiency", and questions that need one are asked back ("Total revenue" → clarify).

## Column kinds (`_classify`)

1. A primary key or declared FK column is `id`.
2. A numeric column whose values are all in {0, 1} is `boolean`.
3. A numeric column with an id-like name (suffix id/cd/code/no/num/key/nbr/ref) is `id`.
4. Any other numeric column is `measure`, and is `money` if its name has a money word.
5. A text column whose sample values all look like ISO dates is `date`.
6. Other text is `category` when it has at most 200 distinct values or no more than 20% of rows are distinct; otherwise `text`.
7. `ordinal(c)`: an integer measure with ≤ 30 distinct values and no money meaning (grade level, model year). It may
   label groups as well as be measured.

## Undeclared foreign keys (strict)

An edge child.col → parent.pk is inferred only when all of the following hold:
1. The child column name is id-like (suffix rule above). This alone removes the spurious `orders.cust_rating →
   customers` edge found in the audit.
2. The parent has a single-column key of the same type affinity.
3. Name evidence:
   - the same name as the parent key; or
   - the last non-suffix word of the child name names the parent table (`opened_by_agent_id` → agents); or
   - it is a vowel-less abbreviation of a parent table word (`start_stn_id` → stations); or
   - for TEXT keys, the same key suffix.
4. Every non-null child value exists in the parent (full containment).
5. Exactly one candidate parent.

`grader_id` / `proctor_id` (which hold teacher ids in the school dev schema) are therefore **not** joined to `teachers`.
Nothing in the names says so, and the engine asks instead ("grader_id has no lookup table that names its values").

## Paths

All simple paths of up to 3 steps from the anchor table are enumerated, and a path never goes up after going down.
Each `Path` records:
- its steps, as (edge, up|down);
- `fans_out`: whether any step goes one-to-many;
- `inferred`;
- `role`: the anchor FK column it starts with.

A lookup reached by two FKs (start/end station, opened/resolved agent) has two paths with different roles. They are
never merged.

## Lexicon (which words name which element)

- **Words.** Names are split, expanded through a small list of common business abbreviations (`amt`, `qty`, `dt`,
  `cnt`, …) and stemmed with one consistent stemmer that is also applied to questions. A leading `no`/`non` in a
  name stays a negation (`no_show`); a trailing `no` is "number" (`order_no`).
- **Schema-derived abbreviations.** A short token that abbreviates exactly one longer word used elsewhere in the same
  schema is mapped to it: a vowel-less subsequence (`mbr` → member, `stn` → station) or a truncation (`stu` → student,
  `accom` → accommodation). These come from the schema itself, never from a global synonym list.
- **Core words.** Each column has *core* words: those a question must contain to name it. Generic words (`amount`,
  `date`, `id`, …) are left out unless that would leave only the table's own noun. Then the full name is needed:
  `order_dt` needs "order date" and `booked_on` needs "booked on", so the noun "bookings" never selects a date column.
- **Optional words when matching.** Units may be omitted (`score_pct` ← "score", `dur_min` ← "duration"). So may
  polarity and light verbs of flags (`helmet_used` ← "helmet", `sla_met` ← "SLA"), but never down to a function word
  alone.
- **Role words.** These are added only for tables reached by more than one role, and help choose between roles.
- **Values.** Stored values of category/text columns are indexed with their table, column and path.

## Determinism

The model is built from the database alone and cached by file modification time. The same file always gives the
same model, which is checked in `backend/tests/test_engine.py` (FK inference, kinds, established vs inferred).
