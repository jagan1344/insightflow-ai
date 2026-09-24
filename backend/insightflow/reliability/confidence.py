"""Nine-signal confidence engine.

Signals:
    sql_validity        — structural SQL validation
    schema_match        — referenced tables exist in the loaded schema
    kpi_match           — KPI rules (non_negative, ratio_0_1) hold on results
    context_consistency — ambiguous / out-of-scope penalties
    data_completeness   — NULL fraction in returned rows
    evidence_strength   — row count adequacy
    result_consistency  — result exists AND KPI rules held
    intent_coverage     — LEGACY: fraction of QueryIntent covered by SQL
                          (kept for legacy pipeline compatibility)
    plan_fidelity       — NEW: plan validator's fidelity score, plus
                          post-compile check that the SQL actually
                          references the plan's headline formula

The `plan_fidelity` hard cap `overall ≤ min(intent_coverage, plan_fidelity) + 0.05`
means neither a legacy-parse miss nor a plan-shape mismatch can be masked
by other signals.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Optional

from ..config import settings
from ..execution.executor import QueryResult
from ..knowledge.schema_agent import get_schema
from ..nlsql.generator import QueryIntent, compute_intent_coverage
from ..plan import AnalyticalPlan, ValidationReport
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


def _plan_fidelity(plan: Optional[AnalyticalPlan],
                   report: Optional[ValidationReport],
                   sql: str) -> float:
    """Combine the semantic validator's fidelity with a post-compile
    check that the SQL text actually contains each plan measure's
    canonical formula."""
    if plan is None or report is None:
        return 1.0
    base = report.fidelity
    if not plan.measures or not sql:
        return base
    # Post-compile check: is every measure formula present in the SQL?
    lo = sql.lower().replace(" ", "")
    hits = 0
    for m in plan.measures:
        f = (m.formula or "").lower().replace(" ", "")
        if not f:
            continue
        # match either the exact expression or a mildly rewritten one
        if f in lo:
            hits += 1
            continue
        # fuzzy: strip quotes and check
        f2 = re.sub(r'["\`\[\]]', "", f)
        lo2 = re.sub(r'["\`\[\]]', "", lo)
        if f2 in lo2:
            hits += 1
    ratio = hits / max(len(plan.measures), 1) if plan.measures else 1.0
    return max(0.0, min(1.0, base * (0.5 + 0.5 * ratio)))


def score_confidence(sqlval: ValidationResult,
                     kpival: KPIValidationResult,
                     result: QueryResult,
                     ambiguous: bool,
                     out_of_scope: bool,
                     query_intent: Optional[QueryIntent] = None,
                     sql: str = "",
                     plan: Optional[AnalyticalPlan] = None,
                     plan_report: Optional[ValidationReport] = None,
                     fidelity_score: Optional[float] = None,
                     result_score: Optional[float] = None,
                     ) -> Confidence:
    coverage = compute_intent_coverage(query_intent, sql)
    partially_covered = query_intent is not None and coverage < 0.99 and (
        query_intent.dimensions or query_intent.filters
        or query_intent.explicit_factors
    )

    fidelity = _plan_fidelity(plan, plan_report, sql)
    # Combine formula-fidelity with the structural fidelity score, when
    # available, so a valid formula in a wrong-shape SQL is caught.
    if fidelity_score is not None:
        fidelity = min(fidelity, fidelity_score)
    # A failing result validator cuts confidence proportionally.
    result_signal_scale = result_score if result_score is not None else 1.0

    ctx = 1.0
    if ambiguous:
        ctx = 0.55
    if out_of_scope:
        ctx = 0.10
    elif partially_covered:
        ctx = min(ctx, 0.30 + 0.55 * coverage)
    # If plan says fidelity is low (semantic error), degrade context too.
    if plan_report is not None and not plan_report.ok:
        ctx = min(ctx, 0.30)

    executed_ok = result.ok
    result_consistency = 1.0 if (kpival.rules_passed and executed_ok) else 0.3

    signals = {
        "sql_validity":        max(0.0, min(1.0, sqlval.score)),
        "schema_match":        _schema_match(sqlval),
        "kpi_match":           max(0.0, min(1.0, kpival.score)),
        "context_consistency": ctx,
        "data_completeness":   _data_completeness(result),
        "evidence_strength":   _evidence_strength(result),
        "result_consistency":  result_consistency * result_signal_scale,
        "intent_coverage":     max(0.0, min(1.0, coverage)),
        "plan_fidelity":       max(0.0, min(1.0, fidelity)),
    }

    weights = settings.confidence_weights
    score = sum(weights.get(k, 0.0) * v for k, v in signals.items())

    if out_of_scope:
        score = min(score, 0.30)

    # Twin hard caps — neither a legacy-parse miss nor a plan-shape
    # mismatch can be masked by other signals.
    score = min(score, coverage + 0.05, fidelity + 0.05)

    score = max(0.0, min(1.0, score))
    return Confidence(score=score, signals=signals)
