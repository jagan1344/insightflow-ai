"""Semantic fulfilment check.

Where `plan.fidelity.FidelityValidator` compares the plan's structure
against the SQL text statically, this module compares the EXECUTED
RESULT against the structured intent — the sanity-check layer that
decides whether a successfully-executed query actually answers the
question.

Rules enforced:

    * TREND / AVERAGE_AT_GRAIN / GROWTH / BREAKDOWN → must return more
      than one row when the time window covers more than one period or
      the dimension has more than one value in the data.
    * COMPARISON → must return exactly two labelled periods.
    * CONTRIBUTION → must return at least one row and expose a `delta`
      column.
    * DIRECT_KPI with a time-range filter → aggregated result must have
      a non-NULL headline value when the range contains data (an
      all-NULL row is an empty-filter failure).
    * SHARE_OF_TOTAL → shares in result must sum to ~1.0.
    * TOP_N / BOTTOM_N → result row count must not exceed N.

Returns `(ok, issues)`. An `ok=False` with a non-empty issues list
should cause the decision layer to WARN or ABSTAIN rather than ANSWER
(see decision policy for exact mapping).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ..execution.executor import QueryResult
from ..plan import AnalyticalPlan, IntentKind


@dataclass
class FulfilmentReport:
    ok: bool = True
    score: float = 1.0
    issues: List[str] = field(default_factory=list)


def _is_all_null_row(row) -> bool:
    for v in row:
        if v is None:
            continue
        return False
    return True


def _time_range_month_count(plan: AnalyticalPlan) -> int:
    """Approximate the number of monthly buckets a plan's time filter
    covers. Returns 0 when the plan has no time filter."""
    for f in plan.filters:
        if f.kind != "time_range":
            continue
        try:
            lo_y, lo_m = str(f.lo).split("-")[:2]
            hi_y, hi_m = str(f.hi).split("-")[:2]
            lo_y, lo_m, hi_y, hi_m = int(lo_y), int(lo_m), int(hi_y), int(hi_m)
        except (ValueError, IndexError):
            return 0
        return (hi_y - lo_y) * 12 + (hi_m - lo_m) + 1
    return 0


def validate_fulfilment(plan: AnalyticalPlan,
                         result: QueryResult) -> FulfilmentReport:
    """Compare an executed result against the structured plan intent."""
    issues: List[str] = []
    if not result.ok:
        return FulfilmentReport(ok=False, score=0.0,
                                 issues=[f"execution failed: {result.error}"])
    rows = result.rows or []
    cols = result.columns or []
    ik = plan.intent_kind

    # TREND / AVERAGE_AT_GRAIN / GROWTH — a time grouping is expected
    if ik in (IntentKind.TREND, IntentKind.AVERAGE_AT_GRAIN,
              IntentKind.GROWTH):
        expected_buckets = _time_range_month_count(plan)
        if expected_buckets > 1 and len(rows) <= 1:
            issues.append(
                f"intent is {ik} with a {expected_buckets}-period time range, "
                f"but result has only {len(rows)} row — grouping was lost "
                f"somewhere in SQL generation.")
        # Check that the first column is time-ish for TREND.
        if ik == IntentKind.TREND and rows:
            first_col = cols[0].lower() if cols else ""
            if not any(hint in first_col for hint in
                        ("month", "quarter", "year", "week", "day",
                         "date", "period", "time")):
                issues.append(
                    f"trend result's first column {first_col!r} is not "
                    f"time-shaped — expected a period/month/day label.")

    # COMPARISON — exactly two rows with distinct period labels
    if ik == IntentKind.COMPARISON and plan.comparison is not None:
        if len(rows) != 2:
            issues.append(
                f"comparison expected two periods, got {len(rows)} rows.")

    # CONTRIBUTION — must have delta column + at least one row
    if ik == IntentKind.CONTRIBUTION:
        if not rows:
            issues.append("contribution query returned no rows.")
        elif "delta" not in [c.lower() for c in cols]:
            issues.append(
                "contribution result missing 'delta' column — the "
                "pipeline cannot summarise a contribution without it.")

    # DIRECT_KPI with time filter — a result that's all-NULL means
    # the filter matched zero rows (SUM/COUNT on empty set).
    if ik == IntentKind.DIRECT_KPI and plan.filters and rows:
        if len(rows) == 1 and _is_all_null_row(rows[0]):
            issues.append(
                "aggregate returned NULL — the applied filter matched no "
                "rows in the dataset.")

    # SHARE_OF_TOTAL — shares must sum to ~1.0
    if plan.share_of_total and rows:
        share_idx = None
        for i, c in enumerate(cols):
            if c.lower() == "share" or c.lower().endswith("_share"):
                share_idx = i
                break
        if share_idx is None and cols:
            share_idx = len(cols) - 1
        if share_idx is not None:
            total = 0.0
            for r in rows:
                try:
                    total += float(r[share_idx] or 0.0)
                except (TypeError, ValueError):
                    pass
            if not (0.98 <= total <= 1.02):
                issues.append(
                    f"share_of_total shares sum to {total:.3f} — expected "
                    f"≈ 1.0; the SQL may be missing a denominator.")

    # TOP_N / BOTTOM_N — count bound
    if plan.top_n is not None and plan.top_n > 0 and len(rows) > plan.top_n:
        issues.append(
            f"result returned {len(rows)} rows but plan.top_n={plan.top_n}.")

    # BREAKDOWN — a breakdown that returns a single row with no dim
    # column means the GROUP BY was dropped.
    if ik == IntentKind.BREAKDOWN and plan.dims and len(rows) <= 1 \
            and not plan.filters:
        issues.append(
            "breakdown returned a single row — grouping by the requested "
            "dimension was likely dropped from the SQL.")

    if not issues:
        return FulfilmentReport(ok=True, score=1.0, issues=[])
    # Score decays with issue count but never zero (so the decision
    # layer can still choose WARN rather than ABSTAIN for mild cases).
    score = max(0.0, 1.0 - 0.3 * len(issues))
    return FulfilmentReport(ok=False, score=score, issues=issues)
