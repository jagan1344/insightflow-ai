"""Chat endpoint wrapping the InsightFlow orchestrator."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from insightflow.orchestrator import Orchestrator

from .schemas import (
    AskRequest, AskResponse, ConfidenceModel, DecisionModel, EvidenceModel,
    EvidenceStep,
)


router = APIRouter()
_orch = Orchestrator()


@router.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest):
    try:
        resp = _orch.ask(req.question)
    except Exception as e:  # defensive
        raise HTTPException(status_code=500, detail=str(e))

    result_columns = list(resp.result.columns) if resp.result.ok else []
    result_rows = [list(r) for r in resp.result.rows] if resp.result.ok else []

    return AskResponse(
        question=resp.question,
        sql=resp.sql,
        intent=resp.intent,
        kpi=resp.evidence.kpi.name if resp.evidence.kpi else None,
        decision=DecisionModel(action=resp.decision.action, reason=resp.decision.reason),
        confidence=ConfidenceModel(score=resp.confidence.score, signals=resp.confidence.signals),
        answer=resp.analysis.summary or "",
        explanation=resp.explanation,
        recommendation=resp.recommendation,
        chart=resp.chart or {"kind": "none"},
        result_columns=result_columns,
        result_rows=result_rows,
        evidence=EvidenceModel(
            chain=[EvidenceStep(step=s["step"], value=s["value"])
                   for s in resp.evidence.as_chain()],
            sample_rows=resp.evidence.sample_rows,
            row_count=resp.evidence.row_count,
        ),
        notes=[n for n in resp.notes if n],
    )
