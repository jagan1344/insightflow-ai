"""InsightFlow orchestrator — ties the full agentic pipeline together."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .analysis.analyzer import Analysis, analyse
from .analysis.viz import chart_spec
from .execution.executor import QueryResult, run_sql
from .explain.explainer import explain, recommend
from .llm import LLMClient
from .memory import Memory
from .nlsql.generator import GenSQL, generate_sql
from .reliability.confidence import Confidence, score_confidence
from .reliability.decision import ANSWER, WARN, CLARIFY, ABSTAIN, Decision, decide
from .reliability.evidence import Evidence, build_evidence
from .validation.kpi_validator import KPIValidationResult, validate_kpi
from .validation.sql_validator import ValidationResult, validate_sql


@dataclass
class InsightResponse:
    question: str
    sql: str
    intent: str
    decision: Decision
    confidence: Confidence
    analysis: Analysis
    evidence: Evidence
    result: QueryResult
    explanation: str
    recommendation: Optional[str]
    chart: Dict[str, Any]
    notes: List[str] = field(default_factory=list)

    @property
    def answered(self) -> bool:
        return self.decision.action in (ANSWER, WARN)


class Orchestrator:
    def __init__(self, llm: Optional[LLMClient] = None, memory: Optional[Memory] = None):
        self.llm = llm or LLMClient()
        self.memory = memory or Memory()

    # ------------------------------------------------------------------
    def ask(self, question: str) -> InsightResponse:
        # 1. generate SQL
        gen: GenSQL = generate_sql(question, llm=self.llm)

        # 2. ambiguity heuristic — mid-signal question with no month + no dim
        ambiguous = (
            not gen.out_of_scope
            and gen.kpi is None
            and gen.dimension is None
            and gen.month is None
        )

        # 3. handle out-of-scope up-front
        if gen.out_of_scope:
            empty_result = QueryResult()
            sqlval = ValidationResult(ok=False, score=0.0, issues=["out of scope"])
            kpival = KPIValidationResult(
                kpi_recognised=False, rules_passed=False, score=0.0,
                issues=["question is out of the BI domain"],
            )
            conf = score_confidence(sqlval, kpival, empty_result,
                                    ambiguous=False, out_of_scope=True)
            evidence = build_evidence(question, "", None, {}, empty_result)
            analysis = Analysis(
                summary=("This question does not appear to be about the "
                         "available business data.")
            )
            decision = Decision(CLARIFY, "out of scope for the loaded dataset")
            resp = InsightResponse(
                question=question, sql="", intent="unknown",
                decision=decision, confidence=conf, analysis=analysis,
                evidence=evidence, result=empty_result,
                explanation=(
                    "I can help with the sales dataset. Try asking about "
                    "revenue, order count, units sold, average order value, "
                    "gross margin or discount rate — optionally broken down "
                    "by region, category, product, segment or month."
                ),
                recommendation=None,
                chart={"kind": "none"},
                notes=list(gen.notes),
            )
            self.memory.add(question, decision.action, conf.score)
            return resp

        # 4. validate SQL
        sqlval = validate_sql(gen.sql)

        # 5. execute (only if valid)
        if sqlval.ok:
            result = run_sql(gen.sql)
        else:
            result = QueryResult(error="SQL failed validation: " + "; ".join(sqlval.issues))

        # 6. validate KPI
        kpival = validate_kpi(gen.kpi, result)

        # 7. analyse
        analysis = analyse(gen.kpi, result, gen.intent, gen.month)

        # 8. evidence
        filters: Dict[str, Any] = {}
        if gen.month is not None:
            filters["month"] = f"2026-{gen.month:02d}"
        if gen.dimension:
            filters["breakdown"] = gen.dimension
        evidence = build_evidence(question, gen.sql, gen.kpi, filters, result)

        # 9. confidence
        confidence = score_confidence(
            sqlval, kpival, result,
            ambiguous=ambiguous, out_of_scope=False,
        )

        # 10. decision
        decision = decide(confidence, sql_ok=sqlval.ok, exec_ok=result.ok, ambiguous=ambiguous)

        # 11. explain + recommend only when we answer
        if decision.action in (ANSWER, WARN):
            explanation = explain(evidence, analysis, llm=self.llm)
            recommendation = recommend(analysis) if gen.diagnostic else None
        elif decision.action == CLARIFY:
            explanation = ("I'm not confident enough to answer this. "
                           "Could you specify a KPI (e.g. revenue, margin) "
                           "and a dimension or time window?")
            recommendation = None
        else:  # ABSTAIN
            explanation = ("I'm abstaining because the query did not pass "
                           "safety/validation or returned no reliable data.")
            recommendation = None

        chart = chart_spec(result, gen.intent) if decision.action in (ANSWER, WARN) else {"kind": "none"}

        response = InsightResponse(
            question=question,
            sql=gen.sql,
            intent=gen.intent,
            decision=decision,
            confidence=confidence,
            analysis=analysis,
            evidence=evidence,
            result=result,
            explanation=explanation,
            recommendation=recommendation,
            chart=chart,
            notes=list(gen.notes)
                  + [f"kpi_issues={kpival.issues}" if kpival.issues else ""]
                  + [f"sql_issues={sqlval.issues}" if sqlval.issues else ""],
        )
        self.memory.add(question, decision.action, confidence.score)
        return response
