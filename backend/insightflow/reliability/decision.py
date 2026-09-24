"""Decision policy: Answer / Warn / Clarify / Abstain.

Plan-aware (2026-09-24): if the analytical plan has semantic errors, or if
its `plan_fidelity` is below the intent-coverage floor, we CLARIFY rather
than ANSWER — no matter how clean the SQL is.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..config import settings
from ..nlsql.generator import QueryIntent
from ..plan import AnalyticalPlan, IntentKind, ValidationReport
from .confidence import Confidence


ANSWER = "ANSWER"
WARN = "WARN"
CLARIFY = "CLARIFY"
ABSTAIN = "ABSTAIN"


@dataclass
class Decision:
    action: str
    reason: str


def _coverage_of(confidence: Confidence) -> float:
    return float(confidence.signals.get("intent_coverage", 1.0))


def _fidelity_of(confidence: Confidence) -> float:
    return float(confidence.signals.get("plan_fidelity", 1.0))


def decide(confidence: Confidence,
           sql_ok: bool,
           exec_ok: bool,
           ambiguous: bool,
           query_intent: Optional[QueryIntent] = None,
           plan: Optional[AnalyticalPlan] = None,
           plan_report: Optional[ValidationReport] = None,
           demanded_breakdown: Optional[bool] = None,
           fidelity_ok: bool = True,
           result_ok: bool = True,
           ) -> Decision:
    if not sql_ok:
        return Decision(ABSTAIN, "generated SQL failed validation")
    if not exec_ok:
        return Decision(ABSTAIN, "query execution failed")

    coverage = _coverage_of(confidence)
    fidelity = _fidelity_of(confidence)

    # Plan-level: ambiguous / unsupported → CLARIFY
    if plan is not None and plan.intent_kind == IntentKind.AMBIGUOUS:
        return Decision(CLARIFY, "question is too vague to plan")
    if plan is not None and plan.unavailable:
        gaps = ", ".join(plan.unavailable)
        return Decision(CLARIFY,
                        f"plan requires items not in the dataset: {gaps}")
    if plan_report is not None and not plan_report.ok:
        return Decision(
            CLARIFY,
            "semantic plan validation failed: " + "; ".join(
                i.message for i in plan_report.issues if i.severity == "error"),
        )

    # Plan/SQL fidelity: SQL executes but doesn't implement the plan.
    if not fidelity_ok:
        return Decision(
            CLARIFY,
            "plan → SQL fidelity check failed: the generated SQL does "
            "not fully implement the analytical plan",
        )

    # Result validation: e.g. top-N returned wrong sort, shares don't
    # sum to 1, comparison returned wrong number of rows.
    if not result_ok:
        return Decision(
            WARN,
            "result did not pass semantic validation — see diagnostics "
            "for details",
        )

    # Something the user asked for isn't in the loaded schema — say so
    # instead of guessing (legacy path).
    if query_intent is not None and query_intent.unavailable:
        gaps = ", ".join(query_intent.unavailable)
        return Decision(CLARIFY,
                        f"required item(s) not in the loaded dataset: {gaps}")

    demanded = demanded_breakdown if demanded_breakdown is not None else (
        query_intent is not None and (
            query_intent.dimensions or query_intent.filters
            or query_intent.explicit_factors)
    )
    if demanded and min(coverage, fidelity) < 0.5:
        return Decision(
            CLARIFY,
            f"coverage {coverage:.2f} / fidelity {fidelity:.2f} — "
            f"SQL doesn't cover the required breakdown/filter/factor",
        )

    score = confidence.score
    if score >= settings.threshold_high:
        return Decision(ANSWER,
                        f"confidence {score:.2f} ≥ {settings.threshold_high:.2f}")
    if score >= settings.threshold_low:
        if ambiguous:
            return Decision(CLARIFY,
                            f"confidence {score:.2f} is mid-range and question is ambiguous")
        if demanded and min(coverage, fidelity) < 0.99:
            return Decision(WARN,
                            f"confidence {score:.2f}, coverage {coverage:.2f}, "
                            f"fidelity {fidelity:.2f} — answer may not cover "
                            f"every requested breakdown/factor")
        return Decision(
            WARN,
            f"confidence {score:.2f} between {settings.threshold_low:.2f} "
            f"and {settings.threshold_high:.2f}",
        )
    return Decision(ABSTAIN, f"confidence {score:.2f} below {settings.threshold_low:.2f}")
