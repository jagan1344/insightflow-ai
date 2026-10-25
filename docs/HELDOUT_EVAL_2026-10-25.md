# Held-out generalization evaluation (v3) - 2026-10-25

Baseline: commit 38e1481 (270 tests, 27/27 curated, 25/25 advanced - reproduced).
Historical files under evaluation/v2/exec_accuracy_* are unchanged.

## Method
- Unseen schema: `evaluation/v2/build_heldout_dataset.py` -> `backend/data/heldout.db`
  (multi-word "East Coast", "APAC HQ"; apostrophe "Men's Apparel"; ampersand
  "R&D Hardware"; overlapping "R&D" division vs "R&D Hardware" line; NULL tier,
  NULL shipping_cost; an office with zero sales).
- `evaluation/v2/heldout_e2e.py` denormalizes it to a flat CSV, registers it as an
  uploaded dataset, and asks 28 questions through the real Orchestrator.
- Oracle: independent sqlite3 SQL on the original multi-table DB (never the planner).

## Before (same 16 initial questions, before fixes)
6/16 correct (37.5%); 10 silently wrong answers at 0.98 confidence:
every value-filter question returned the unfiltered revenue total; "how many sales"
returned SUM(revenue); average/min/max of `gross_amount` returned SUM(revenue);
"missing shipping cost" returned a SUM; "customers with missing tier" returned a row count (62) not 7.

## Root causes and changes
1. Value detector required `<value> <column-name>` (e.g. "East Coast office_name"),
   so natural nouns never matched -> now schema-grounded: every dimension column's
   distinct values are indexed; longest-first, word-bounded, non-overlapping matches
   (`_value_index`, `_value_mentions`); noun optional. Demo-schema path unchanged.
2. Unknown-value guard was demo-only -> generalized to uploaded schemas using the
   dataset's own dimension nouns (`_find_unknown_dim_values`).
3. Values present in several columns -> CLARIFY (`_find_ambiguous_values`).
4. Silent fallback to total_revenue when an aggregate (avg/min/max/count) was asked
   but no measure bound -> now AMBIGUOUS; "how many <noun>" binds row_count.
5. Extremum / null-column / generic avg+sum KPIs used hardcoded demo column names and
   underscore-only aliases -> bound from the dataset's measure/column names (space-normalized).
6. "How many customers with missing tier" -> COUNT(DISTINCT entity).

## After
- Answerable: 23/23 correct (100%). Expected abstentions: 5/5 (Mars/East/South Pole office,
  Diamond tier, zero-sales office). Full suite 270 pass; curated 27/27; advanced 25/25.

## Remaining limitations (not claimed solved)
- 28 questions on one schema is still a small sample; this is not general correctness.
- Flat uploads cannot distinguish "unknown value" from "known value with zero fact rows"
  (dimension tables are gone); both CLARIFY. Multi-table schemas with real dimension
  tables are only handled for the demo schema; the generalized path covers single-table uploads.
- Value matching can collide with ordinary words (mitigated by a stoplist and ambiguity
  CLARIFY, not eliminated); values are read from the DB at plan time (cost grows with
  cardinality; columns >5000 distinct are skipped).
- Value-first matching means "Revenue in APAC region" filters territory=APAC though
  "region" is not a column; this is value-grounded but not noun-verified.

## Reproduce
    python evaluation/v2/build_heldout_dataset.py
    python evaluation/v2/heldout_e2e.py
    cd backend && python -m pytest -q
