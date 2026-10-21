"""Evidence-grounded explanations and recommendations."""
from __future__ import annotations

import json
from typing import Optional

from ..analysis.analyzer import Analysis
from ..llm import LLMClient
from ..plan import AnalyticalPlan, IntentKind
from ..reliability.evidence import Evidence


_SYSTEM = (
    "You are a careful business-intelligence analyst. Given a chain of evidence "
    "(question, SQL, KPI definition, filters, row count, sample rows) and a "
    "deterministic analytic summary, write a single crisp paragraph that "
    "explains the answer. Ground every claim in the evidence. Do not invent "
    "numbers. If unsure, say so."
)


def plan_evidence_line(plan: AnalyticalPlan, table: str) -> str:
    """A one-line evidence trace surfaced above the answer.

    Shape: "KPI · formula · grain · filters · comparison · dataset".
    """
    parts: list[str] = []
    if plan.measures:
        m = plan.measures[0]
        parts.append(f"KPI: {m.kpi_id} ≡ {m.formula}")
    if plan.dims:
        dims = ", ".join(d.column + (f" (by {d.time_unit})" if d.is_time
                                      and d.time_unit else "")
                         for d in plan.dims)
        parts.append(f"Grouped by: {dims}")
    if plan.grain and plan.grain.kind == "time":
        parts.append(f"Grain: {plan.grain.time_unit} of {plan.grain.time_column}")
    if plan.comparison:
        parts.append(f"Comparison: {plan.comparison.base_period} vs "
                     f"{plan.comparison.target_period}")
    if plan.contribution:
        parts.append(f"Contribution: {plan.contribution.base_period} → "
                     f"{plan.contribution.target_period} across "
                     f"{plan.contribution.dim_column}")
    if plan.filters:
        fs: list[str] = []
        for f in plan.filters:
            if f.kind == "time_range":
                fs.append(f"time ∈ [{f.lo}, {f.hi}]")
            elif f.kind == "metric_lt":
                fs.append(f"{f.kpi_id} < {f.threshold}")
            elif f.kind == "metric_gt":
                fs.append(f"{f.kpi_id} > {f.threshold}")
            elif f.kind == "eq" and f.column:
                fs.append(f"{f.column} = {f.value}")
        if fs:
            parts.append("Filters: " + "; ".join(fs))
    if plan.top_n is not None:
        parts.append(f"Top-N: {plan.top_n}")
    if plan.share_of_total:
        parts.append("Share of total")
    parts.append(f"Dataset: {table}")
    return " · ".join(parts)


_FORECAST_PHRASES = (
    "will be", "projected", "projection", "forecast", "forecasted",
    "forecasting", "expected to be", "going to be", "estimate for next",
    "estimate for the next", "prediction", "predicted", "we predict",
    "we project",
)

_CAUSAL_PHRASES = (
    "caused by", "due to", "because of", "the cause is", "the reason is",
    "driven by",  # mild — allowed inside diagnostics with contributor data
)


def _looks_like_forecast(text: str) -> bool:
    lo = text.lower()
    return any(p in lo for p in _FORECAST_PHRASES)


def explain(evidence: Evidence, analysis: Analysis,
             llm: Optional[LLMClient] = None,
             plan: Optional[AnalyticalPlan] = None) -> str:
    """Build the user-facing paragraph. Guarded so the explainer can
    never label a historical aggregate as a forecast / projection.
    """
    base = analysis.summary
    text = base
    if llm is not None and llm.available:
        prompt = (
            f"Evidence chain (JSON):\n{json.dumps(evidence.as_chain(), default=str, indent=2)}\n\n"
            f"Deterministic summary:\n{analysis.summary}\n\n"
            "Rules: Describe only what the evidence shows. Do NOT project, "
            "predict, forecast, or claim causality the data does not support. "
            "If the question asked for a forecast or future value, say that "
            "a forecast is not supported by this evidence instead of "
            "inventing one.\n\n"
            "Write one paragraph (<= 90 words) grounded in the evidence."
        )
        candidate = llm.complete(prompt, system=_SYSTEM, temperature=0.0)
        if candidate:
            text = candidate

    # Hard explanation gate — regardless of whether the LLM or the
    # deterministic summary produced the text, strip forecast phrasing
    # when the plan does NOT support forecasting. The pipeline has no
    # genuine forecaster today; see safety/__init__.py.
    if plan is not None and plan.intent_kind != IntentKind.UNSUPPORTED \
            and _looks_like_forecast(text):
        # The plan is NOT a forecast request (safety gate would have
        # fired earlier) — the LLM is hallucinating. Fall back to the
        # deterministic summary.
        return base
    if plan is not None and plan.intent_kind == IntentKind.UNSUPPORTED \
            and "forecasting" in (plan.unavailable or []):
        return ("I can't produce a forecast for this question. "
                "Forecasting is not implemented in this build. "
                "Here is the evidence I do have: " + base)
    return text or base


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
