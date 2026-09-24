"""Structured failure taxonomy for the analytical pipeline.

`classify_failure()` is called by the orchestrator when a request does
not answer, to tag the reason in one of the categories below. This
category is surfaced in diagnostics + tests so evaluation can slice
error modes without free-text grepping.
"""
from __future__ import annotations

from typing import Optional

from ..execution.executor import QueryResult
from ..validation.sql_validator import ValidationResult
from ..validation.kpi_validator import KPIValidationResult
from .plan import AnalyticalPlan, IntentKind, ValidationReport
from .fidelity import FidelityReport


class FailureCategory:
    NONE                        = "NONE"
    AMBIGUITY                   = "AMBIGUITY"
    UNSUPPORTED_DATA            = "UNSUPPORTED_DATA"
    INTENT_ERROR                = "INTENT_ERROR"
    KPI_ERROR                   = "KPI_ERROR"
    SCHEMA_MAPPING_ERROR        = "SCHEMA_MAPPING_ERROR"
    GRAIN_ERROR                 = "GRAIN_ERROR"
    AGGREGATION_ERROR           = "AGGREGATION_ERROR"
    FORMULA_ERROR               = "FORMULA_ERROR"
    FILTER_ERROR                = "FILTER_ERROR"
    TIME_ERROR                  = "TIME_ERROR"
    COMPARISON_ERROR            = "COMPARISON_ERROR"
    RANKING_ERROR               = "RANKING_ERROR"
    PLAN_ERROR                  = "PLAN_ERROR"
    SQL_SYNTAX_ERROR            = "SQL_SYNTAX_ERROR"
    SQL_DIALECT_ERROR           = "SQL_DIALECT_ERROR"
    SQL_SCHEMA_ERROR            = "SQL_SCHEMA_ERROR"
    PLAN_SQL_FIDELITY_ERROR     = "PLAN_SQL_FIDELITY_ERROR"
    EXECUTION_ERROR             = "EXECUTION_ERROR"
    RESULT_VALIDATION_ERROR     = "RESULT_VALIDATION_ERROR"
    EVIDENCE_ERROR              = "EVIDENCE_ERROR"
    CONFIDENCE_ERROR            = "CONFIDENCE_ERROR"


def classify_failure(
    plan: Optional[AnalyticalPlan],
    plan_report: Optional[ValidationReport],
    sql: str,
    sqlval: Optional[ValidationResult],
    fidelity: Optional[FidelityReport],
    exec_result: Optional[QueryResult],
    result_ok: bool = True,
    kpival: Optional[KPIValidationResult] = None,
) -> str:
    """Return the category best matching the observed failure state."""
    if plan is not None and plan.intent_kind == IntentKind.AMBIGUOUS:
        return FailureCategory.AMBIGUITY
    if plan is not None and plan.unavailable:
        return FailureCategory.UNSUPPORTED_DATA
    if plan is not None and plan.intent_kind == IntentKind.UNSUPPORTED:
        return FailureCategory.UNSUPPORTED_DATA
    if plan_report is not None and not plan_report.ok:
        # Look at first error to route to a finer bucket.
        for i in plan_report.issues:
            if i.severity != "error":
                continue
            if i.kind == "missing_kpi":
                return FailureCategory.KPI_ERROR
            if i.kind == "missing_column":
                return FailureCategory.SCHEMA_MAPPING_ERROR
            if i.kind == "bad_grain":
                return FailureCategory.GRAIN_ERROR
            if i.kind == "bad_aggregation":
                return FailureCategory.AGGREGATION_ERROR
            if i.kind == "bad_comparison":
                return FailureCategory.COMPARISON_ERROR
            if i.kind == "unbindable":
                return FailureCategory.UNSUPPORTED_DATA
        return FailureCategory.PLAN_ERROR
    if sqlval is not None and not sqlval.ok:
        joined = "; ".join(sqlval.issues).lower()
        if "unknown table" in joined or "unknown column" in joined:
            return FailureCategory.SQL_SCHEMA_ERROR
        if "forbidden keyword" in joined or "multiple statements" in joined:
            return FailureCategory.SQL_SYNTAX_ERROR
        return FailureCategory.SQL_SYNTAX_ERROR
    if exec_result is not None and not exec_result.ok:
        return FailureCategory.EXECUTION_ERROR
    if fidelity is not None and not fidelity.ok:
        return FailureCategory.PLAN_SQL_FIDELITY_ERROR
    if kpival is not None and not kpival.rules_passed:
        return FailureCategory.RESULT_VALIDATION_ERROR
    if not result_ok:
        return FailureCategory.RESULT_VALIDATION_ERROR
    return FailureCategory.NONE
