"""Seven-signal confidence engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from ..config import settings
from ..execution.executor import QueryResult
from ..knowledge.schema_agent import get_schema
from ..validation.kpi_validator import KPIValidationResult
from ..validation.sql_validator import ValidationResult


@dataclass
class Confidence:
    score: float
    signals: Dict[str, float] = field(default_factory=dict)


def _schema_match(sqlval: ValidationResult) -> float:
    if not sqlval.referenced_tables:
        return 0.0
    schema = get_schema()
    known = {t.lower() for t in schema.tables.keys()}
    hits = sum(1 for t in sqlval.referenced_tables if t in known)
    return hits / len(sqlval.referenced_tables)


def _data_completeness(result: QueryResult) -> float:
    if not result.ok or not result.rows:
        return 0.0
    total = 0
    non_null = 0
    for row in result.rows:
        for v in row:
            total += 1
            if v is not None:
                non_null += 1
    return (non_null / total) if total else 0.0


def _evidence_strength(result: QueryResult) -> float:
    if not result.ok:
        return 0.0
    n = result.n_rows
    if n == 0:
        return 0.0
    if n == 1:
        return 0.7
    return min(1.0, 0.6 + 0.1 * min(4, n))


def score_confidence(sqlval: ValidationResult,
                     kpival: KPIValidationResult,
                     result: QueryResult,
                     ambiguous: bool,
                     out_of_scope: bool) -> Confidence:
    ctx = 1.0
    if ambiguous:
        ctx = 0.55
    if out_of_scope:
        ctx = 0.10

    executed_ok = result.ok
    result_consistency = 1.0 if (kpival.rules_passed and executed_ok) else 0.3

    signals = {
        "sql_validity":        max(0.0, min(1.0, sqlval.score)),
        "schema_match":        _schema_match(sqlval),
        "kpi_match":           max(0.0, min(1.0, kpival.score)),
        "context_consistency": ctx,
        "data_completeness":   _data_completeness(result),
        "evidence_strength":   _evidence_strength(result),
        "result_consistency":  result_consistency,
    }

    weights = settings.confidence_weights
    score = sum(weights.get(k, 0.0) * v for k, v in signals.items())

    if out_of_scope:
        score = min(score, 0.30)

    score = max(0.0, min(1.0, score))
    return Confidence(score=score, signals=signals)
