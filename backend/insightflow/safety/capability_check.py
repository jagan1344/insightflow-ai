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
    # "the median X" / "compute the median" → median-statistic ask.
    # Exclude "above the median" / "below the median" / "versus the median"
    # — those are the relative_to_stat intent and the planner handles them.
    (r"\b(?:what(?:'s|\s+is)?\s+the\s+median|compute\s+(?:the\s+)?median|"
     r"show\s+(?:me\s+)?(?:the\s+)?median|give\s+(?:me\s+)?(?:the\s+)?median)\b",
     "median_statistic",
     "I can't compute medians yet — only sums, counts, averages, "
     "ratios, and shares. Try 'average order value' instead."),

    (r"\b(?:percentile|percentiles|p(?:50|75|90|95|99)\b|quartile|quartiles|decile|deciles)\b",
     "percentile_statistic",
     "I can't compute percentiles / quartiles yet. Try 'average' or "
     "'top N' to approximate."),

    (r"\b(?:standard\s+deviation|stddev|variance|skewness|kurtosis)\b",
     "distribution_statistic",
     "I can't compute standard deviation or variance yet — only "
     "sums, counts, averages, ratios and shares."),

    (r"\b(?:mode|modal)\s+(?:of|value)\b",
     "mode_statistic",
     "I can't compute statistical mode yet — try a top-N by frequency "
     "instead."),

    # ---- Rolling / moving / trailing windows ----
    (r"\b(?:rolling|moving|trailing)\s+(?:\d+[\s-]+)?"
     r"(?:day|week|month|quarter|year|average|sum)",
     "rolling_window",
     "I can't compute rolling / moving / trailing-window aggregates "
     "yet. Ask for a specific period instead "
     "(e.g. 'revenue in June 2026', 'monthly revenue in Q2 2026')."),

    (r"\b(?:last|past|previous)\s+\d+\s+(?:day|days|week|weeks)\b",
     "sliding_window_days",
     "I can't compute arbitrary 'last N days / weeks' windows yet. "
     "Try a calendar range such as 'revenue in July 2026' or "
     "'last month'."),

    # ---- Within-group ranking ----
    (r"\btop\s+\d+\s+\w+\s+(?:in|per|within|for)\s+each\b",
     "top_n_within_group",
     "I can't compute 'top-N within each group' (window-ranking) yet. "
     "Try a plain 'top N by metric' breakdown instead."),

    (r"\btop\s+\w+\s+(?:in|per|within|for)\s+each\b",
     "top_1_within_group",
     "I can't pick 'the top entry within each group' yet (window "
     "ranking). Try asking about one group at a time, or a plain "
     "top-N by metric."),

    (r"\brank(?:ed|ing|s)?\s+\w+\s+(?:within|per|by|in)\s+each\b",
     "rank_within_group",
     "I can't compute ranks within each group yet. Ask for a plain "
     "top-N breakdown instead."),
    (r"\brank(?:ed|ing|s)?\s+(?:within|per|by)\s+(?:each|group)\b",
     "rank_within_group",
     "I can't compute ranks within each group yet. Ask for a plain "
     "top-N breakdown instead."),

    # ---- Data-quality / null-aware questions ----
    (r"\b(?:missing|null|nulls|empty|blank|unknown|unspecified|incomplete)\s+"
     r"(?:value|values|rows|records|cost|revenue|discount|date|dates|data|cells|column|columns)\b",
     "null_awareness",
     "I can't query for missing / null / empty values yet. The "
     "pipeline treats every row's columns as populated. If you "
     "need a data-quality view, use the Data Quality page / API "
     "(/api/pages/data_quality) which profiles coverage directly."),

    (r"\bduplicate(?:s|d)?\s+(?:row|rows|record|records|order|orders)\b",
     "duplicate_detection",
     "I can't detect duplicate rows yet. Use the Data Quality page "
     "or write a direct SQL query via the Analytics Explorer."),

    # ---- Row-level MIN/MAX (as opposed to aggregate) ----
    # Allow optional "single"/"individual" filler between the adjective
    # and the noun ("maximum single order value", "largest individual
    # revenue").
    (r"\b(?:minimum|smallest|lowest)\s+(?:single\s+|individual\s+)?"
     r"(?:order|row|transaction)\s*"
     r"(?:single\s+|individual\s+)?"
     r"(?:revenue|value|amount|quantity|discount|profit|margin)\b",
     "row_level_min",
     "I can't retrieve the single smallest-row value yet. Try asking "
     "for a 'bottom N' breakdown instead."),

    (r"\b(?:maximum|largest|highest|biggest)\s+(?:single\s+|individual\s+)?"
     r"(?:order|row|transaction)\s*"
     r"(?:single\s+|individual\s+)?"
     r"(?:revenue|value|amount|quantity|discount|profit|margin)\b",
     "row_level_max",
     "I can't retrieve the single largest-row value yet. Try asking "
     "for a 'top N' breakdown instead."),

    (r"^\s*(?:please\s+)?(?:what(?:'s|\s+is)?\s+the\s+)?"
     r"(?:min|minimum|smallest|lowest)\s+(?:order\s+)?(?:revenue|value|amount)\s*\??$",
     "row_level_min_short",
     "I can't compute the single smallest-row value yet. Try "
     "'bottom 5 orders by revenue' or a filtered sum."),

    # ---- COUNT DISTINCT (not currently in the catalog) ----
    (r"\b(?:how\s+many\s+(?:unique|distinct|different|separate))\b",
     "count_distinct",
     "I can't compute count-distinct yet — try asking for the "
     "breakdown directly (e.g. 'revenue by customer', 'revenue "
     "by product')."),

    (r"\b(?:distinct|unique)\s+(?:count|number)\b",
     "count_distinct_phrase",
     "I can't compute count-distinct yet. Try a breakdown by that "
     "dimension instead."),

    # ---- Threshold on a grouped metric with a NUMERIC literal
    # ("months where revenue > 400k", "regions with revenue above
    # 1 million"). Requires a numeric literal (optionally with
    # k / m / million) after the comparison word so "above average /
    # below the median" (relative_to_stat) are NOT caught here.
    #
    # Variant A: starts with a question word ("Which months...").
    (r"\b(?:which|what|in\s+which)\s+(?:month|months|quarter|quarters|"
     r"year|years|region|regions|category|categories|product|products|"
     r"customer|customers|segment|segments)\b"
     r"[^?]{0,80}?\b(?:exceed(?:ed|s)?|above|over|greater\s+than|"
     r">\s*|more\s+than|at\s+least|than)\s*"
     r"(?:\$\s*)?\d[\d,]*(?:\.\d+)?\s*(?:k|m|million|thousand|billion)?\b",
     "threshold_on_grouped_metric",
     "I can't yet filter groups by a numeric threshold on their "
     "aggregated metric (e.g. 'months where revenue > 400k'). Ask "
     "for the breakdown ('revenue by month') and apply the threshold "
     "visually, or use the Analytics Explorer for a direct SQL "
     "query with HAVING."),
    # Variant B: declarative noun phrase ("regions with revenue above
    # 1 million", "months with sales over 400k").
    (r"\b(?:month|months|quarter|quarters|year|years|region|regions|"
     r"category|categories|product|products|customer|customers|"
     r"segment|segments)\s+with\s+\w+\s+"
     r"(?:exceed(?:ed|s)?|above|over|greater\s+than|more\s+than|"
     r"at\s+least|than)\s+"
     r"(?:\$\s*)?\d[\d,]*(?:\.\d+)?\s*(?:k|m|million|thousand|billion)?\b",
     "threshold_on_grouped_metric_declarative",
     "I can't yet filter groups by a numeric threshold on their "
     "aggregated metric (e.g. 'regions with revenue above 1 million'). "
     "Ask for the breakdown and apply the threshold visually, or use "
     "the Analytics Explorer for a direct SQL query with HAVING."),

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
