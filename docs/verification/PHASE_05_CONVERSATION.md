# Phase 5 — Conversational follow-ups

A minimal, explicit resolver that handles three documented rewrite
rules. Anything the rules do not match passes through to the planner
unchanged.

## Code

- `backend/insightflow/conversation/__init__.py` — `ConversationContext`
  dataclass + `resolve_followup` + `capture_context`.
- `backend/insightflow/orchestrator.py` — the orchestrator holds a
  single `ConversationContext` per instance; the API is one
  orchestrator per session so there is **no cross-session leakage**.

## Rewrite rules (narrow + explicit)

1. **"Now by X" / "and by X"** → replace the dim in the last question.
2. **"and in <period>" / "for <period>"** → replace the time filter.
3. **"compare it to <X>"** → promote the last question into a
   two-period comparison (planner handles the subsequent parsing).

## Safety

- **No prior anchor** → the follow-up passes through; the planner
  CLARIFIEs on its own if it cannot interpret.
- **Dataset switch between turns** → resolver returns the question
  unchanged. A filter from the previous dataset's schema is never
  carried into a new dataset.
- **Only ANSWER/WARN updates the anchor.** CLARIFY and ABSTAIN leave
  the prior anchor intact so the user can retry.
- **Fresh orchestrator per session** → cross-session isolation is
  structural, not merely enforced.

## Tests

`backend/tests/test_followup_resolver.py` — 12 tests covering:

- 7 unit tests of the resolver (no DB)
- 5 end-to-end tests through the orchestrator

Verified behaviours:

- "What was revenue in July 2026?" then "Now by region" →
  `GROUP BY regions.region_name WHERE order_date >= '2026-07-01' AND < '2026-08-01'`.
- "Revenue in July 2026" then "And in June 2026" → June filter
  replaces July.
- A failed destructive follow-up does not overwrite the anchor —
  the next follow-up resolves against July 2026.
- A fresh orchestrator has an empty context (`last_question is None`).

## Known limitations

- Pronoun resolution (`"that month"`, `"the previous metric"`) is NOT
  implemented. The planner handles the raw question which will usually
  CLARIFY — safer than an invented reference.
- The compare-rewrite produces awkward text when the base question is
  long; it still works but tightening the English form is deferred.
- The resolver does not read `Memory` (the ring buffer of past turns);
  it only reads the single anchor. This is deliberate — ambiguous
  historical references are the easy way to get wrong answers.
