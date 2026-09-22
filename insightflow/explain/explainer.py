"""Evidence-grounded explanations and recommendations."""
from __future__ import annotations

import json
from typing import Optional

from ..analysis.analyzer import Analysis
from ..llm import LLMClient
from ..reliability.evidence import Evidence


_SYSTEM = (
    "You are a careful business-intelligence analyst. Given a chain of evidence "
    "(question, SQL, KPI definition, filters, row count, sample rows) and a "
    "deterministic analytic summary, write a single crisp paragraph that "
    "explains the answer. Ground every claim in the evidence. Do not invent "
    "numbers. If unsure, say so."
)


def explain(evidence: Evidence, analysis: Analysis, llm: Optional[LLMClient] = None) -> str:
    if llm is None or not llm.available:
        return analysis.summary
    prompt = (
        f"Evidence chain (JSON):\n{json.dumps(evidence.as_chain(), default=str, indent=2)}\n\n"
        f"Deterministic summary:\n{analysis.summary}\n\n"
        "Write one paragraph (<= 90 words) that a business stakeholder can act on."
    )
    text = llm.complete(prompt, system=_SYSTEM, temperature=0.0)
    return text or analysis.summary


def recommend(analysis: Analysis) -> Optional[str]:
    """Only for diagnostic answers: name the worst negative contributor."""
    if not analysis.contributors:
        return None
    negatives = [c for c in analysis.contributors if c.delta < 0]
    if not negatives:
        return None
    worst = min(negatives, key=lambda c: c.delta)
    unit_hint = ""
    return (
        f"Investigate {worst.dimension} '{worst.name}' — it drove the largest "
        f"negative swing ({worst.pct:+.1f}%, {worst.delta:+,.2f}). "
        f"Look at demand, pricing, promotions and stock-outs there first, "
        f"and consider a targeted recovery plan."
    )
