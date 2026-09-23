"""Business/KPI rule validation for a query result."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..execution.executor import QueryResult
from ..knowledge.kpi import KPI


@dataclass
class KPIValidationResult:
    kpi_recognised: bool
    rules_passed: bool
    score: float
    issues: List[str] = field(default_factory=list)


def _numeric(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def validate_kpi(kpi: Optional[KPI], result: QueryResult) -> KPIValidationResult:
    if kpi is None:
        return KPIValidationResult(
            kpi_recognised=False, rules_passed=False, score=0.45,
            issues=["no KPI recognised in question"],
        )

    if not result.ok:
        return KPIValidationResult(
            kpi_recognised=True, rules_passed=False, score=0.4,
            issues=[f"query execution failed: {result.error}"],
        )

    issues: List[str] = []
    if kpi.key in result.columns:
        col_idx = result.columns.index(kpi.key)
    else:
        # fall back to the last numeric-looking column
        col_idx = len(result.columns) - 1 if result.columns else None

    values = []
    if col_idx is not None:
        for row in result.rows:
            v = _numeric(row[col_idx])
            if v is not None:
                values.append(v)

    if kpi.non_negative:
        bad = [v for v in values if v < 0]
        if bad:
            issues.append(f"{kpi.name} must be non-negative but saw {bad[:3]}")

    if kpi.ratio_0_1:
        bad = [v for v in values if v < 0.0 or v > 1.0]
        if bad:
            issues.append(f"{kpi.name} must be within [0,1] but saw {bad[:3]}")

    rules_passed = not issues
    score = 1.0 if rules_passed else 0.4
    return KPIValidationResult(
        kpi_recognised=True, rules_passed=rules_passed, score=score, issues=issues,
    )
