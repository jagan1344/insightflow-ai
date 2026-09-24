"""Pydantic request/response models."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# -------- chat --------

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


class DecisionModel(BaseModel):
    action: str
    reason: str


class ConfidenceModel(BaseModel):
    score: float
    signals: Dict[str, float]


class EvidenceStep(BaseModel):
    step: str
    value: Any


class EvidenceModel(BaseModel):
    chain: List[EvidenceStep]
    sample_rows: List[Dict[str, Any]] = []
    row_count: int = 0


class AskResponse(BaseModel):
    question: str
    sql: str
    intent: str
    kpi: Optional[str] = None
    decision: DecisionModel
    confidence: ConfidenceModel
    answer: str
    explanation: str
    recommendation: Optional[str] = None
    chart: Dict[str, Any]
    result_columns: List[str] = []
    result_rows: List[List[Any]] = []
    evidence: EvidenceModel
    notes: List[str] = []
    failure_category: str = "NONE"
    diagnostics: Optional[Dict[str, Any]] = None
    plan_trace: Optional[Dict[str, Any]] = None


# -------- dashboard --------

class KpiValue(BaseModel):
    value: float
    unit: str
    delta_pct: float


class Point(BaseModel):
    label: str
    value: float


class DashboardPayload(BaseModel):
    version: int
    kpis: Dict[str, KpiValue]
    revenue_by_month: List[Dict[str, Any]]
    revenue_by_region: List[Dict[str, Any]]
    revenue_by_category: List[Dict[str, Any]]
    margin_by_category: List[Dict[str, Any]]


# -------- misc --------

class SimpleResponse(BaseModel):
    ok: bool = True
    detail: str = ""
    row_count: Optional[int] = None
