"""Decision policy: Answer / Warn / Clarify / Abstain."""
from __future__ import annotations

from dataclasses import dataclass

from ..config import settings
from .confidence import Confidence


ANSWER = "ANSWER"
WARN = "WARN"
CLARIFY = "CLARIFY"
ABSTAIN = "ABSTAIN"


@dataclass
class Decision:
    action: str
    reason: str


def decide(confidence: Confidence,
           sql_ok: bool,
           exec_ok: bool,
           ambiguous: bool) -> Decision:
    if not sql_ok:
        return Decision(ABSTAIN, "generated SQL failed validation")
    if not exec_ok:
        return Decision(ABSTAIN, "query execution failed")

    score = confidence.score
    if score >= settings.threshold_high:
        return Decision(ANSWER, f"confidence {score:.2f} ≥ {settings.threshold_high:.2f}")
    if score >= settings.threshold_low:
        if ambiguous:
            return Decision(CLARIFY, f"confidence {score:.2f} is mid-range and question is ambiguous")
        return Decision(WARN, f"confidence {score:.2f} between {settings.threshold_low:.2f} and {settings.threshold_high:.2f}")
    return Decision(ABSTAIN, f"confidence {score:.2f} below {settings.threshold_low:.2f}")
