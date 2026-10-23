"""Request-level safety and intent checks that run BEFORE SQL
generation.

The pipeline's `validation/sql_validator.py` rejects mutating SQL
statically, but by then the planner has already reinterpreted the
destructive request as something harmless (e.g. `COUNT(*)`). The checks
in this module gate the question at the orchestrator entry so the
planner never sees it.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..plan.planner import is_destructive_request, is_forecast_question
from .capability_check import check_capability


@dataclass
class RequestSafety:
    destructive: bool = False
    forecast: bool = False
    unsupported: bool = False
    code: str = ""
    reason: str = ""

    @property
    def refuse(self) -> bool:
        return self.destructive or self.forecast or self.unsupported


def check_request(question: str) -> RequestSafety:
    """Classify an incoming NL question for pre-SQL safety.

    Order matters:
      1. destructive intent  → ABSTAIN
      2. forecasting intent  → CLARIFY (not implemented)
      3. unsupported capability → CLARIFY (named specifically)
    """
    if is_destructive_request(question):
        return RequestSafety(
            destructive=True, code="destructive",
            reason=("This request looks like a destructive data operation "
                    "(delete / modify / truncate). InsightFlow AI is "
                    "read-only and will not execute, nor will it "
                    "reinterpret the request as an unrelated read-only "
                    "query."),
        )
    if is_forecast_question(question):
        return RequestSafety(
            forecast=True, code="forecast",
            reason=("This question asks for a forecast or prediction. "
                    "Forecasting is not implemented in this build — I "
                    "will not substitute a historical total for a future "
                    "estimate. Try asking about an observed period "
                    "(e.g. 'What was revenue in September 2026?')."),
        )
    cap = check_capability(question)
    if cap.unsupported:
        return RequestSafety(unsupported=True, code=cap.code,
                              reason=cap.reason)
    return RequestSafety()
