"""Capability pre-gate.

The planner has a conservative fallback: when it cannot bind an
unsupported operation keyword, it hands back a `total_revenue`
DIRECT_KPI plan. That silently converts a question like
"what is the median order revenue?" into
`SELECT SUM(revenue) FROM orders` — the pipeline then faithfully
executes a semantically unrelated query and returns ANSWER at high
confidence.

This gate inspects the question text BEFORE the planner runs and
refuses the request with a specific reason when it names a
capability we don't actually support. All refusals route to CLARIFY
with a message naming the unsupported capability — never to a quiet
fallback-and-answer.

The gate is intentionally conservative: it names each unsupported
construct explicitly and leaves anything it doesn't recognise alone,
so the planner retains full control of everything it genuinely
handles.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# Pattern → (short name, user-facing reason). Order matters: specific
# constructs come before generic ones.
_UNSUPPORTED: list[tuple[str, str, str]] = [
    # ---- Statistical aggregations we don't compute ----
    # Median / percentile / stddev / variance — IMPLEMENTED in Phase 4
    # via Python post-aggregation. Only skew/kurtosis/mode remain
    # refused for now.
    (r"\b(?:skewness|kurtosis)\b",
     "distribution_statistic",
     "I can't compute skewness or kurtosis yet."),

    (r"\b(?:mode|modal)\s+(?:of|value)\b",
     "mode_statistic",
     "I can't compute statistical mode yet — try a top-N by frequency "
     "instead."),

    # ---- Rolling / moving / trailing windows ----
    # IMPLEMENTED in Phase 2 for monthly cadence via window AVG() with
    # ROWS BETWEEN N PRECEDING AND CURRENT ROW. The planner intent is
    # ROLLING_AVG; the compiler lowers to SQLite 3.25+ window SQL.
    # Only non-monthly cadences (daily / weekly / quarterly) remain
    # refused for now.
    (r"\b(?:rolling|moving|trailing)\s+(?:\d+[\s-]+)?"
     r"(?:day|days|week|weeks|quarter|quarters|year|years)\b",
     "rolling_window_non_monthly",
     "I can only compute monthly rolling / moving averages right now. "
     "Daily / weekly / quarterly / yearly rolling windows aren't "
     "implemented yet — try the monthly equivalent."),

    # "Last N days / weeks" is NOW IMPLEMENTED in Phase 2 as a day-level
    # time_range filter. No refusal needed.

    # Within-group ranking is NOW IMPLEMENTED in Phase 2 via window
    # functions. No refusal needed.

    # ---- Data-quality / null-aware questions ----
    # Null-aware counts for a specific column are NOW IMPLEMENTED.
    # Keep the refusal for GENERIC data-quality asks that don't name a
    # concrete column.
    (r"\b(?:missing|null|nulls|empty|blank|unknown|unspecified|incomplete)\s+"
     r"(?:value|values|data|cells|column|columns)\b",
     "generic_data_quality",
     "I can only answer null / missing questions about a specific "
     "column (e.g. 'orders with missing cost'). For a dataset-wide "
     "data-quality view, use the Data Quality page / API."),

    (r"\bduplicate(?:s|d)?\s+(?:row|rows|record|records|order|orders)\b",
     "duplicate_detection",
     "I can't detect duplicate rows yet. Use the Data Quality page "
     "or write a direct SQL query via the Analytics Explorer."),

    # ---- Row-level MIN / MAX for a single transaction ----
    # The aggregate MIN / MAX of a column is NOW IMPLEMENTED in Phase 2.
    # The refusal only remains for the "single order" phrasing which
    # asks for the row-level record not an aggregate.
    (r"\b(?:minimum|smallest|lowest|maximum|largest|highest|biggest)\s+"
     r"(?:single\s+|individual\s+)?(?:order|row|transaction)\s+"
     r"(?:single\s+|individual\s+)?record\b",
     "row_level_record",
     "I can compute the single minimum / maximum VALUE of a column, "
     "but I can't retrieve the full record for that single row. Try "
     "'bottom 5 orders by revenue' instead."),

    # COUNT DISTINCT phrased as "how many distinct X" is NOW
    # IMPLEMENTED for recognised dimension columns. No refusal needed.

    # Threshold on a grouped metric with a NUMERIC literal is NOW
    # IMPLEMENTED via metric_gt_grouped / metric_lt_grouped filters.
    # No refusal needed.

    # ---- "List X" when there's no bound dim / only an aggregate target ----
    # Narrower: "list customers with the most orders" → implies ranking
    # but the pipeline only emits an aggregate.
    (r"\blist\s+\w+\s+with\s+(?:the\s+)?(?:most|highest|biggest|"
     r"largest|lowest|smallest|fewest|least)\b",
     "list_entities_by_rank",
     "I can't yet produce a per-entity list ranked by an aggregate "
     "(e.g. 'list customers with the most orders'). Try the "
     "equivalent 'top N <entity> by <metric>' phrasing — e.g. "
     "'top 5 customers by order count'."),
]


@dataclass
class CapabilityVerdict:
    unsupported: bool = False
    code: str = ""
    reason: str = ""


def check_capability(question: str) -> CapabilityVerdict:
    """Return a verdict naming the first unsupported capability
    matched by the question. The pipeline turns an unsupported verdict
    into a CLARIFY response with the reason verbatim.
    """
    if not question:
        return CapabilityVerdict()
    q = " " + question.lower().strip() + " "
    # Normalise whitespace.
    q = re.sub(r"\s+", " ", q)
    for pattern, code, reason in _UNSUPPORTED:
        if re.search(pattern, q, flags=re.IGNORECASE):
            return CapabilityVerdict(unsupported=True, code=code,
                                      reason=reason)
    return CapabilityVerdict()
