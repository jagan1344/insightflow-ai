"""Plan → SQL fidelity validation.

Given a validated `AnalyticalPlan` and the SQL string the compiler
produced, `FidelityValidator.check(plan, sql)` returns a `FidelityReport`
saying, per plan feature, whether the SQL actually implements it.

This is orthogonal to structural SQL validation (which just says "will
the DB parse and execute this?") and to KPI validation (which checks the
result values). Fidelity catches the class of bugs where the SQL runs
successfully but doesn't answer the question the user asked — the
"executable but semantically wrong" case.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from .plan import (
    AnalyticalPlan, ComparisonSpec, ContributionSpec, FilterExpr,
    IntentKind, MeasureRef, RelativeStatSpec,
)


@dataclass
class FidelityCheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class FidelityReport:
    ok: bool
    score: float                       # 0..1 — fraction of checks that passed
    checks: List[FidelityCheck] = field(default_factory=list)

    def failed(self) -> List[FidelityCheck]:
        return [c for c in self.checks if not c.passed]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _no_space(s: str) -> str:
    return re.sub(r"\s+", "", s.lower())


class FidelityValidator:
    """Static SQL-vs-plan checker. No execution, no DB access."""

    def check(self, plan: AnalyticalPlan, sql: str) -> FidelityReport:
        checks: List[FidelityCheck] = []
        if not sql:
            return FidelityReport(ok=False, score=0.0, checks=[
                FidelityCheck("sql_present", False, "compiler produced no SQL"),
            ])

        s = _norm(sql)
        sn = _no_space(sql)

        # 1) Table referenced (uploaded → dataset_slug; demo → orders).
        # Accept quoted, bare, or joined form and boundary tolerant.
        if plan.table:
            t = plan.table.lower()
            table_hit = bool(
                re.search(rf'\b{re.escape(t)}\b', s)
                or f'"{t}"' in s)
            checks.append(FidelityCheck(
                "table_referenced", table_hit,
                f"expected table '{plan.table}' referenced in SQL"))

        # 2) Every measure's canonical formula literally appears
        for m in plan.measures:
            if not m.formula:
                continue
            f_no_space = _no_space(m.formula)
            passed = f_no_space in sn
            # For contribution / average-at-grain the formula is embedded
            # inside a CTE, so the substring test is still valid.
            checks.append(FidelityCheck(
                f"measure_formula:{m.kpi_id}", passed,
                f"formula {m.formula!r} in SQL"))

        # 3) Every dim is in a GROUP BY (or is the time bucket)
        if plan.dims:
            has_group_by = "group by" in s
            checks.append(FidelityCheck(
                "group_by_present", has_group_by,
                "SQL contains GROUP BY when the plan has dims"))
            for d in plan.dims:
                if d.is_time and d.time_unit:
                    ok = d.time_unit in s or d.time_column.lower() in s
                else:
                    ok = d.column.lower() in s
                checks.append(FidelityCheck(
                    f"dim_referenced:{d.column}", ok,
                    f"dim '{d.column}' present in SQL"))

        # 4) top_n / bottom_n → LIMIT N and ORDER BY
        if plan.top_n is not None:
            has_limit = f"limit {plan.top_n}" in s
            checks.append(FidelityCheck(
                "top_n_limit", has_limit,
                f"SQL contains LIMIT {plan.top_n}"))
            checks.append(FidelityCheck(
                "top_n_order_by", "order by" in s,
                "SQL contains ORDER BY when top_n is set"))

        # 5) share_of_total → window SUM OVER () or subquery divide
        if plan.share_of_total:
            has_share = ("sum(sum(" in sn.replace(" ", "")
                          or "over()" in sn.replace(" ", "")
                          or ") / sum(" in s
                          or "* 1.0 / sum(" in s)
            checks.append(FidelityCheck(
                "share_of_total_denominator", has_share,
                "SQL divides by a group total"))

        # 6) comparison → both period literals present
        if plan.comparison is not None:
            cs = plan.comparison
            b_ok = cs.base_period in sql
            t_ok = cs.target_period in sql
            checks.append(FidelityCheck(
                "comparison_base_period", b_ok,
                f"base period '{cs.base_period}' present in SQL"))
            checks.append(FidelityCheck(
                "comparison_target_period", t_ok,
                f"target period '{cs.target_period}' present in SQL"))
            checks.append(FidelityCheck(
                "comparison_two_rows", "union" in s,
                "comparison SQL uses UNION so both periods land in results"))

        # 7) contribution → both period CTEs + delta expression
        if plan.contribution is not None:
            ok_delta = "delta" in s
            checks.append(FidelityCheck(
                "contribution_delta_expr", ok_delta,
                "SQL computes a delta column"))
            checks.append(FidelityCheck(
                "contribution_period_ctes",
                "with base as" in s and "targ as" in s,
                "SQL has base and targ CTEs"))

        # 8) filters → WHERE (time_range/eq/in) or HAVING (metric_lt)
        for f in plan.filters:
            if f.kind == "time_range":
                ok = "where" in s and (str(f.lo) in sql or str(f.lo)[:7] in sql)
                checks.append(FidelityCheck(
                    f"filter_time_range:{f.lo}..{f.hi}", ok,
                    "time-range filter present"))
            elif f.kind == "metric_lt":
                ok = "having" in s or "where" in s
                checks.append(FidelityCheck(
                    f"filter_metric_lt:{f.kpi_id}", ok,
                    f"metric-threshold filter for {f.kpi_id}"))
            elif f.kind == "eq" and f.column:
                ok = f.column.lower() in s
                checks.append(FidelityCheck(
                    f"filter_eq:{f.column}", ok, "equality filter present"))

        # 9) relative_to_stat → agg CTE + SELECT with entity col + stat filter
        if plan.relative_stat is not None:
            rs: RelativeStatSpec = plan.relative_stat
            checks.append(FidelityCheck(
                "rel_stat_agg_cte", "with agg as" in s,
                "SQL builds a per-entity CTE"))
            checks.append(FidelityCheck(
                "rel_stat_entity", rs.entity_column.lower() in s,
                f"entity column {rs.entity_column} referenced"))
            checks.append(FidelityCheck(
                "rel_stat_stat_op",
                any(t in s for t in ("avg(", "median(")),
                "group statistic computed in SQL"))

        # 10) grain → for average_at_grain, ensure both an inner GROUP BY
        # and an outer AVG.
        if plan.grain is not None and plan.grain.kind == "time" \
                and plan.intent_kind == IntentKind.AVERAGE_AT_GRAIN:
            ok = "avg(" in s and "group by" in s
            checks.append(FidelityCheck(
                "avg_at_grain_shape", ok,
                "SQL has AVG of grouped SUM"))

        passed = sum(1 for c in checks if c.passed)
        total = max(1, len(checks))
        score = passed / total
        ok = all(c.passed for c in checks)
        return FidelityReport(ok=ok, score=score, checks=checks)
