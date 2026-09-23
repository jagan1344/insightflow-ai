"""Decision policy: Answer / Warn / Clarify / Abstain.

Coverage-aware (2026-09-23):
    A question that names a specific breakdown / filter / factor must be
    ANSWERed with SQL that actually covers those, or we must CLARIFY. It
    is never acceptable to answer a *different* question confidently.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..config import settings
from ..nlsql.generator import QueryIntent
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


def decide(confidence: Confidence,
           sql_ok: bool,
           exec_ok: bool,
           ambiguous: bool,
           query_intent: Optional[QueryIntent] = None) -> Decision:
    if not sql_ok:
        return Decision(ABSTAIN, "generated SQL failed validation")
    if not exec_ok:
        return Decision(ABSTAIN, "query execution failed")

    coverage = _coverage_of(confidence)

    # Something the user asked for isn't in the loaded schema — say so
    # instead of guessing.
    if query_intent is not None and query_intent.unavailable:
        gaps = ", ".join(query_intent.unavailable)
        return Decision(CLARIFY,
                        f"required item(s) not in the loaded dataset: {gaps}")

    # The question named a specific breakdown / loss filter / correlation
    # and the SQL didn't cover it → CLARIFY. This is the primary fix.
    demanded_breakdown = query_intent is not None and (
        query_intent.dimensions or query_intent.filters
        or query_intent.explicit_factors
    )
    if demanded_breakdown and coverage < 0.5:
        return Decision(
            CLARIFY,
            f"intent coverage {coverage:.2f} — SQL doesn't cover the "
            f"required breakdown/filter/factor",
        )

    score = confidence.score
    if score >= settings.threshold_high:
        return Decision(ANSWER, f"confidence {score:.2f} ≥ {settings.threshold_high:.2f}")
    if score >= settings.threshold_low:
        if ambiguous:
            return Decision(CLARIFY,
                            f"confidence {score:.2f} is mid-range and question is ambiguous")
        if demanded_breakdown and coverage < 0.99:
            return Decision(WARN,
                            f"confidence {score:.2f}, coverage {coverage:.2f} — "
                            f"answer may not cover every requested breakdown/factor")
        return Decision(
            WARN,
            f"confidence {score:.2f} between {settings.threshold_low:.2f} "
            f"and {settings.threshold_high:.2f}",
        )
    return Decision(ABSTAIN, f"confidence {score:.2f} below {settings.threshold_low:.2f}")
