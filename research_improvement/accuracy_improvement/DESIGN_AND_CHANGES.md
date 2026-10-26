# Semantic catalog, code changes and tests (start 0cde65b -> frozen da925ad)

## Semantic catalog (deterministic, inspectable)
The catalog the pipeline reasons with is assembled from schema evidence only; `semantic_catalog.py`
dumps it per dataset (examples: `catalogs/v5_*.json`). It contains:
- tables, column types, primary keys, NOT NULL columns; declared and inferred relationships with status
  and nullability (`knowledge/relational.py`, `rel_context.py`);
- per column: role, semantic type (money / quantity / flag / id / date / category), canonical words after
  abbreviation expansion, unit token, join path and fan-out class, flag polarity (positive name vs
  normal-condition name such as `sensor_ok`), and aggregation compatibility (ids: COUNT DISTINCT; flags:
  filter only, never SUM/AVG; money and quantity: SUM/AVG/MIN/MAX);
- metric definitions (`knowledge/kpi_catalog.py`): formula, aggregation, money-likeness, aliases;
- vocabulary (`knowledge/abbrev.py`, `knowledge/vocabulary.py`): abbreviations, unit words, synonym groups.
Column descriptions are not present in the schemas and no business definitions are invented.

## Code changes (all general; no question text or reference value appears in production code)
| file | change |
|---|---|
| `knowledge/vocabulary.py` (new) | question normalisation to schema vocabulary: thousands separators, phrasal/hyphen compounds (`drop-off`, `picked up`, `check-in`), multi-word column names in any order or "b of a" form (`amount claimed` -> `claim amt`, `type of room` -> `room type`), unit words (`kilowatt-hours`, `square metres`, `room nights`), synonym groups, stored all-caps acronyms (`online travel agencies` -> `OTA`, never across function words), revenue words -> the base table's single generic money column. A rewrite needs its target in the schema and must be unique; every rewrite is a note; interpretive ones are stated (WARN). |
| `composite.py` (new) | questions whose formula the wording states (percentage of rows, share of a total, explicit "A divided by B", period difference with a stated order) are answered from two sub-questions that pass the full pipeline; combined only when both are single answered numbers; formula stated; "X per Y" alone is not treated as a ratio |
| `plan/planner.py` | comparator suffixes ("1000 or more", "4.8 or higher"); "-ing" column stems; short-abbreviation prefix match next to a number; flag polarity synonyms and antonyms with proximity, negation-aware; inclusion phrases ("cancelled ones included"); exclusion cues (leaving out, omitting, "not paid in"); null-state filters (unknown / not recorded / left blank / don't have ... yet / haven't been assigned to an X -> nullable FK IS NULL), never on identifier columns, related columns only through non-nullable paths; "how many <quantity>" = SUM for non-money measures; NULL-tested measure becomes a row count; flags are conditions, not groupings, unless grouped explicitly; passive agent "driven by drivers rated 4.8" only with a restricting clause; head-noun dimension binding ("each insurance product"); "which N X ... most" = top N; short all-caps codes need capitals; role word before a role-playing value resolves the role; spurious unbound dimension words dropped |
| `knowledge/kpi_catalog.py` | plural aliases; no bare-core alias that equals a table's entity noun (`claim` for `claim_amt`); expanded-core aliases (`pax_cnt` -> passengers, `mins_cnt` -> minutes); generic money column aliases from the base-table noun (`bill amount`, `billed amount`, `amount billed`); `different X` for distinct counts; unit suffixes in core detection |
| `knowledge/rel_context.py` | members of a composite key that are not FKs are attributes (`lang`, `program_nm`) -> fan-out filters via EXISTS |
| `semantics/wording.py` (new) + `verify.py` | `comparator_not_preserved`, `negated_value_kept` (not inside NOT EXISTS / NOT IN scopes), `rate_not_computed`, `vague_metric` |
| `orchestrator.py` | normalisation step 0b with recorded rewrites; composite step 0c; semantic layer also for distinct_count and null_count intents; words consumed by applied filters; column-word exceptions for "cause of loss" and membership dates; inclusion-phrase flag columns |
| `reliability/mention_coverage.py`, `verification/intent_audit.py`, `semantics/spec.py` | function words (light verbs, contraction fragments), dataset domain name, comparator/null/flag/exclusion words consumed only when the matching filter is applied, hyphenated value modifiers; passive agent shared rule; MAX/MIN cue inside a used column name |
| `knowledge/abbrev.py` | cls, pay, rtg, lang, rpt, req, dist, dur, prem, nts, hrs, mins |

No safeguard was removed or loosened by threshold: the veto mechanisms remain; what changed is the
representation they check (which words count as explained). Two new safety checks were added.

## Tests (development, not held out)
- `tests/test_accuracy_mechanisms.py` (16): each mechanism with a positive and a negative case.
- `tests/test_generalization_dev.py` (55): a fresh gym schema in two naming schemes; 15 positive questions
  vs independent SQL in both schemes; metamorphic invariance (rename, row shuffle, unrelated table,
  duplicated child rows) per question; SUM vs COUNT; misleading flag name; member vs visit count;
  5 must-refuse questions (two-date ambiguity, anti-join, rate wording, vague metric, fan-out grouping);
  negated value; short code.
- Defects found by these tests and fixed before the freeze: "guest visits included" read as is_guest = 1;
  "Which members have no visits?" answered as visit_id IS NULL (null-state rule on an identifier);
  "how many minutes" unbound; MAX cue inside `max_cap`.
- Regression found by the monitor sets and fixed before the freeze: P3 lost C04, C23, M03 ("paid by home
  state" read as a passive agent); fixed by requiring a restricting clause (P4 = P1 everywhere).
- Full suite at the freeze: 597 passed, 0 failed, 3 warnings.
