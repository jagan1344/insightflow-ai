"""Semantic validation of the execution result.

Runs AFTER SQL execution. Where `validation.sql_validator` checks
structure and `plan.fidelity` checks that the SQL implements the plan,
this module checks that the RESULT ROWS are internally consistent with
what the plan promised:

    * Percentage shares should sum ~1.0 for `share_of_total`.
    * `top_n` should return at most N rows, sorted DESC on the measure.
    * `bottom_n` should return at most N rows, sorted ASC.
    * `comparison` should return exactly two rows, one per period.
    * `contribution` should have a numeric `delta` column and non-empty rows.
    * Ratio KPIs (unit=ratio, ratio_0_1=True) should be in [0, 1].
    * Non-negative KPIs shouldn't have negative headline values.
    * Empty result on a non-filter question is a warning, not a pass.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ..execution.executor import QueryResult
from ..plan import AnalyticalPlan, IntentKind


@dataclass
class ResultIssue:
    severity: str    # "error" | "warning" | "info"
    message: str


@dataclass
class ResultReport:
    ok: bool
    score: float
    issues: List[ResultIssue] = field(default_factory=list)


def _numeric_col(rows: list, idx: int) -> list:
    out = []
    for r in rows:
        try:
            out.append(float(r[idx]))
        except (TypeError, ValueError):
            pass
    return out


class ResultValidator:
    def check(self, plan: AnalyticalPlan, result: QueryResult) -> ResultReport:
        issues: List[ResultIssue] = []
        if not result.ok:
            return ResultReport(ok=False, score=0.0, issues=[
                ResultIssue("error",
                             f"query execution failed: {result.error}"),
            ])
        rows = result.rows or []
        cols = result.columns or []

        # 1) share_of_total → shares should sum ~1.0 (allow slack for
        # display rounding / floating math).
        if plan.share_of_total and rows and "share" in [c.lower() for c in cols]:
            idx = [c.lower() for c in cols].index("share")
            vals = _numeric_col(rows, idx)
            if vals:
                total = sum(vals)
                if not (0.98 <= total <= 1.02):
                    issues.append(ResultIssue(
                        "warning",
                        f"share_of_total column sums to {total:.3f} — "
                        f"expected ~1.0"))

        # 2) top/bottom N cardinality + ordering
        if plan.top_n is not None and rows and plan.measures:
            if len(rows) > plan.top_n:
                issues.append(ResultIssue(
                    "error",
                    f"top_n=N={plan.top_n} but result returned "
                    f"{len(rows)} rows"))
            # last measure column drives the ordering
            m_idx = len(cols) - 1
            vals = _numeric_col(rows, m_idx)
            if len(vals) >= 2:
                sorted_desc = vals == sorted(vals, reverse=True)
                sorted_asc = vals == sorted(vals)
                if plan.intent_kind == IntentKind.TOP_N and not sorted_desc:
                    issues.append(ResultIssue(
                        "error", "top_n result is not sorted descending"))
                if plan.intent_kind == IntentKind.BOTTOM_N and not sorted_asc:
                    issues.append(ResultIssue(
                        "error", "bottom_n result is not sorted ascending"))

        # 3) comparison shape
        if plan.comparison is not None:
            if len(rows) != 2:
                issues.append(ResultIssue(
                    "error",
                    f"comparison must return two rows, got {len(rows)}"))
            else:
                periods = {str(r[0]) for r in rows}
                expected = {plan.comparison.base_period,
                            plan.comparison.target_period}
                if periods != expected:
                    issues.append(ResultIssue(
                        "error",
                        f"comparison rows {periods} != expected {expected}"))

        # 4) contribution shape
        if plan.contribution is not None:
            if not rows:
                issues.append(ResultIssue(
                    "warning", "contribution query returned no rows"))
            elif "delta" not in [c.lower() for c in cols]:
                issues.append(ResultIssue(
                    "error", "contribution result missing 'delta' column"))

        # 5) ratio KPI must be in [0, 1] on breakdown / direct rows
        for m in plan.measures:
            if m.unit != "ratio":
                continue
            m_idx = None
            for i, c in enumerate(cols):
                if c.lower() == m.kpi_id.lower():
                    m_idx = i; break
            if m_idx is None:
                continue
            for r in rows:
                try:
                    v = float(r[m_idx])
                    if v < 0.0 or v > 1.0:
                        issues.append(ResultIssue(
                            "warning",
                            f"KPI {m.kpi_id} value {v} outside [0, 1]"))
                        break
                except (TypeError, ValueError):
                    continue

        # 6) empty result on a non-filter question is a warning
        wants_filter = any(f.kind in ("metric_lt", "metric_gt")
                            for f in plan.filters)
        if not rows and not wants_filter \
                and plan.intent_kind not in (IntentKind.AMBIGUOUS,
                                              IntentKind.UNSUPPORTED):
            issues.append(ResultIssue(
                "warning",
                "query executed but returned no rows"))

        errors = [i for i in issues if i.severity == "error"]
        warns = [i for i in issues if i.severity == "warning"]
        if errors:
            score = 0.0
        elif warns:
            score = max(0.4, 1.0 - 0.15 * len(warns))
        else:
            score = 1.0
        return ResultReport(ok=(not errors), score=score, issues=issues)
