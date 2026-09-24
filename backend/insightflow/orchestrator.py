"""InsightFlow orchestrator — plan-then-compile agentic pipeline.

Pipeline (2026-09-24 rewrite):

    question
      → get_active_dataset()
      → build_catalog(dataset)                  # KPICatalog
      → Planner(dataset, catalog).plan()        # AnalyticalPlan
      → PlanValidator.validate()                # semantic report
      → SQLCompiler.compile()                   # SQL string
      → validate_sql()                          # structural
      → run_sql()                               # actual execution
      → validate_kpi_result()                   # semantic result checks
      → analyse()                               # human summary
      → build_evidence()                        # traceable formula chain
      → score_confidence()                      # 9-signal, plan-aware
      → decide()                                # ANSWER / WARN / CLARIFY / ABSTAIN
      → explain()                               # evidence-first paragraph

Legacy path (`_rule_generate`) is retained ONLY as a fallback for
questions the planner marks AMBIGUOUS, so the 55 existing regression
tests continue to pass. New questions on any dataset shape flow through
the new pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .analysis.analyzer import Analysis, analyse
from .analysis.viz import chart_spec
from .execution.executor import QueryResult, run_sql
from .explain.explainer import explain, recommend, plan_evidence_line
from .knowledge.dataset_registry import get_active_dataset
from .knowledge.kpi import KPI, KPIS
from .knowledge.kpi_catalog import build_catalog
from .llm import LLMClient
from .memory import Memory
from .nlsql.generator import GenSQL, generate_sql
from .plan import (
    AnalyticalPlan, IntentKind, Planner, PlanValidator, SQLCompiler,
    ValidationReport,
)
from .reliability.confidence import Confidence, score_confidence
from .reliability.decision import (
    ANSWER, WARN, CLARIFY, ABSTAIN, Decision, decide,
)
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
    plan_trace: Optional[Dict[str, Any]] = None

    @property
    def answered(self) -> bool:
        return self.decision.action in (ANSWER, WARN)


# ---------------------------------------------------------------------------
# Helpers to bridge the AnalyticalPlan into the legacy KPI validator +
# analyzer types (which want a `KPI` object). We synthesise a KPI record
# from the plan's headline measure so the validator can still check
# ratio_0_1 / non_negative rules; the SQL text is the catalog's canonical
# form so no double-computation happens.
# ---------------------------------------------------------------------------

def _headline_kpi_from_plan(plan: AnalyticalPlan) -> Optional[KPI]:
    if not plan.measures:
        return None
    m = plan.measures[0]
    unit = m.unit or ""
    ratio_0_1 = unit == "ratio"
    non_neg = m.kpi_id not in ("profit", "gross_margin")
    return KPI(
        key=m.kpi_id,
        name=m.display_name or m.kpi_id.replace("_", " ").title(),
        sql_expr=m.formula,
        description=f"Computed by the analytical planner.",
        unit=unit,
        non_negative=non_neg,
        ratio_0_1=ratio_0_1,
    )


def _legacy_intent_of(plan: AnalyticalPlan) -> str:
    """Map plan intent kind to the string the legacy analyzer expects."""
    ik = plan.intent_kind
    if ik in (IntentKind.TREND, IntentKind.AVERAGE_AT_GRAIN,
              IntentKind.GROWTH):
        return "trend"
    if ik == IntentKind.CONTRIBUTION:
        return "diagnostic"
    if ik in (IntentKind.BREAKDOWN, IntentKind.TOP_N, IntentKind.BOTTOM_N,
              IntentKind.SHARE_OF_TOTAL, IntentKind.COMPARISON,
              IntentKind.RATIO):
        return "breakdown"
    return "aggregate"


class Orchestrator:
    def __init__(self, llm: Optional[LLMClient] = None,
                 memory: Optional[Memory] = None):
        self.llm = llm or LLMClient()
        self.memory = memory or Memory()

    # ==================================================================
    def ask(self, question: str) -> InsightResponse:
        ds = get_active_dataset()
        catalog = build_catalog(ds)

        # 1. Plan the question against the active dataset.
        planner = Planner(ds, catalog)
        plan = planner.plan(question)

        # 2. Validate the plan semantically.
        validator = PlanValidator(ds, catalog)
        report = validator.validate(plan)

        # 3. If the plan is ambiguous OR was rejected on demo but the
        #    demo pipeline can still parse it, fall back so all legacy
        #    tests still pass. On uploaded datasets we NEVER fall back —
        #    the plan-based path is authoritative.
        if plan.intent_kind == IntentKind.AMBIGUOUS or \
                (ds.kind == "demo" and not report.ok):
            return self._legacy_ask(question, ds, plan, report)

        # 4. Compile.
        compiler = SQLCompiler(ds, catalog)
        sql = compiler.compile(plan)

        if not sql:
            return self._unanswerable_response(
                question, plan, report,
                reason="Could not compile a SQL query for this plan.")

        # 5. Structural SQL validation.
        sqlval = validate_sql(sql)

        # 6. Execute if valid.
        if sqlval.ok:
            result = run_sql(sql)
        else:
            result = QueryResult(
                error="SQL failed validation: " + "; ".join(sqlval.issues))

        # 7. Result-level KPI validation.
        headline_kpi = _headline_kpi_from_plan(plan)
        kpival = validate_kpi(headline_kpi, result)

        # 8. Deterministic analysis summary.
        legacy_intent = _legacy_intent_of(plan)
        month = None
        for f in plan.filters:
            if f.kind == "time_range" and f.lo:
                try:
                    month = int(str(f.lo).split("-")[1])
                except Exception:
                    pass
        # For a comparison / contribution, treat the target period as the
        # "month" the analyzer diagnoses.
        if month is None and plan.contribution is not None:
            try:
                month = int(plan.contribution.target_period.split("-")[1])
            except Exception:
                pass
        if month is None and plan.comparison is not None:
            try:
                month = int(plan.comparison.target_period.split("-")[1])
            except Exception:
                pass
        analysis = analyse(headline_kpi, result, legacy_intent, month)

        # 9. Evidence (with a plan trace).
        filters_dict: Dict[str, Any] = {}
        for f in plan.filters:
            if f.kind == "time_range":
                filters_dict["time_range"] = f"{f.lo} .. {f.hi}"
            elif f.kind == "metric_lt":
                filters_dict[f.kpi_id] = f"< {f.threshold}"
        for d in plan.dims:
            filters_dict.setdefault("dims", []).append(d.column)
        evidence = build_evidence(question, sql, headline_kpi,
                                    filters_dict, result)

        # 10. Confidence (plan-aware).
        confidence = score_confidence(
            sqlval, kpival, result,
            ambiguous=False, out_of_scope=False,
            query_intent=None, sql=sql,
            plan=plan, plan_report=report,
        )

        # 11. Decision.
        demanded = bool(plan.dims or plan.filters
                        or plan.comparison or plan.contribution)
        decision = decide(confidence, sql_ok=sqlval.ok, exec_ok=result.ok,
                          ambiguous=False, query_intent=None,
                          plan=plan, plan_report=report,
                          demanded_breakdown=demanded)

        # 12. Explain (evidence-first).
        if decision.action in (ANSWER, WARN):
            trace = plan_evidence_line(plan, catalog.table)
            body = explain(evidence, analysis, llm=self.llm)
            explanation = f"{trace}\n\n{body}"
            recommendation = (recommend(analysis)
                              if plan.intent_kind == IntentKind.CONTRIBUTION
                              else None)
        elif decision.action == CLARIFY:
            explanation = self._clarify_message_from_plan(plan, report)
            recommendation = None
        else:  # ABSTAIN
            explanation = ("I'm abstaining because the query did not pass "
                           "safety/validation or returned no reliable data.")
            recommendation = None

        chart = (chart_spec(result, legacy_intent)
                 if decision.action in (ANSWER, WARN)
                 else {"kind": "none"})

        notes: List[str] = []
        notes.append(f"active_dataset={ds.id} table={ds.table}")
        notes.append(f"plan_kind={plan.intent_kind}")
        if report.issues:
            notes.append("plan_issues=" + "; ".join(
                f"{i.kind}:{i.message}" for i in report.issues))
        if kpival.issues:
            notes.append(f"kpi_issues={kpival.issues}")
        if sqlval.issues:
            notes.append(f"sql_issues={sqlval.issues}")

        # Keep `.intent` as the LEGACY intent string so existing test
        # assertions that inspect `resp.intent == 'diagnostic'` still hold.
        response = InsightResponse(
            question=question, sql=sql,
            intent=legacy_intent, decision=decision,
            confidence=confidence, analysis=analysis, evidence=evidence,
            result=result, explanation=explanation,
            recommendation=recommendation, chart=chart, notes=notes,
            plan_trace=plan.as_trace(),
        )
        self.memory.add(question, decision.action, confidence.score)
        return response

    # ==================================================================
    def _clarify_message_from_plan(self, plan: AnalyticalPlan,
                                    report: ValidationReport) -> str:
        if plan.intent_kind == IntentKind.AMBIGUOUS:
            return ("This question is too open-ended to answer from the data "
                    "alone. Try naming a specific metric (e.g. revenue, "
                    "profit) and — optionally — a breakdown, time window "
                    "or comparison.")
        if plan.unavailable:
            gaps = ", ".join(u.split(":", 1)[-1] for u in plan.unavailable)
            return (f"I can't answer this on the current dataset — it's "
                    f"missing: {gaps}. Load a dataset with those fields, "
                    f"or ask about what's available.")
        errs = [i for i in report.issues if i.severity == "error"]
        if errs:
            joined = "; ".join(e.message for e in errs)
            return f"The current dataset can't satisfy this question: {joined}"
        return ("I'm not confident enough to answer this. Could you name a "
                "specific KPI and (optionally) a dimension or time window?")

    # ==================================================================
    def _unanswerable_response(self, question: str, plan: AnalyticalPlan,
                                report: ValidationReport, reason: str
                                ) -> InsightResponse:
        empty = QueryResult()
        sqlval = ValidationResult(ok=False, score=0.0, issues=[reason])
        kpival = KPIValidationResult(
            kpi_recognised=False, rules_passed=False, score=0.0,
            issues=[reason],
        )
        confidence = score_confidence(
            sqlval, kpival, empty, ambiguous=False, out_of_scope=True,
            query_intent=None, sql="", plan=plan, plan_report=report,
        )
        decision = Decision(CLARIFY, reason)
        evidence = build_evidence(question, "", None, {}, empty)
        analysis = Analysis(summary=reason)
        explanation = self._clarify_message_from_plan(plan, report)
        return InsightResponse(
            question=question, sql="", intent=plan.intent_kind,
            decision=decision, confidence=confidence, analysis=analysis,
            evidence=evidence, result=empty, explanation=explanation,
            recommendation=None, chart={"kind": "none"},
            notes=[reason], plan_trace=plan.as_trace(),
        )

    # ==================================================================
    # Legacy fallback — used ONLY when the plan-based path is inapplicable
    # (demo dataset with an ambiguous / unsupported plan). Preserves the
    # 55 regression tests without leaking legacy behavior into uploaded
    # datasets.
    def _legacy_ask(self, question: str, ds, plan: AnalyticalPlan,
                    report: ValidationReport) -> InsightResponse:
        gen: GenSQL = generate_sql(question, llm=self.llm)

        ambiguous = (not gen.out_of_scope and gen.kpi is None
                     and gen.dimension is None and gen.month is None)

        if gen.out_of_scope:
            empty_result = QueryResult()
            sqlval = ValidationResult(ok=False, score=0.0,
                                       issues=["out of scope"])
            kpival = KPIValidationResult(
                kpi_recognised=False, rules_passed=False, score=0.0,
                issues=["question is out of the BI domain"],
            )
            conf = score_confidence(
                sqlval, kpival, empty_result, ambiguous=False,
                out_of_scope=True, query_intent=gen.query_intent, sql="",
                plan=plan, plan_report=report,
            )
            evidence = build_evidence(question, "", None, {}, empty_result)
            is_vague = gen.query_intent is not None and gen.query_intent.vague
            summary = ("This question is too open-ended to answer from the "
                       "data alone.") if is_vague else (
                       "This question does not appear to be about the "
                       "available business data.")
            analysis = Analysis(summary=summary)
            reason = ("vague/open-ended — no specific KPI or dimension named"
                      if is_vague else "out of scope for the loaded dataset")
            decision = Decision(CLARIFY, reason)
            return InsightResponse(
                question=question, sql="", intent="unknown",
                decision=decision, confidence=conf, analysis=analysis,
                evidence=evidence, result=empty_result,
                explanation=(
                    "I can help with the loaded dataset. Try asking about a "
                    "specific KPI (e.g. revenue, orders, gross margin, "
                    "profit, discount rate) — optionally broken down by "
                    "region, category, sub-category, product, segment or "
                    "month."
                ),
                recommendation=None, chart={"kind": "none"},
                notes=list(gen.notes), plan_trace=plan.as_trace(),
            )

        sqlval = validate_sql(gen.sql)
        if sqlval.ok:
            result = run_sql(gen.sql)
        else:
            result = QueryResult(
                error="SQL failed validation: " + "; ".join(sqlval.issues))
        kpival = validate_kpi(gen.kpi, result)
        analysis = analyse(gen.kpi, result, gen.intent, gen.month)

        filters: Dict[str, Any] = {}
        if gen.month is not None:
            filters["month"] = f"2026-{gen.month:02d}"
        if gen.dimension:
            filters["breakdown"] = gen.dimension
        evidence = build_evidence(question, gen.sql, gen.kpi, filters, result)

        confidence = score_confidence(
            sqlval, kpival, result, ambiguous=ambiguous, out_of_scope=False,
            query_intent=gen.query_intent, sql=gen.sql,
            plan=plan, plan_report=report,
        )
        demanded = gen.query_intent is not None and (
            gen.query_intent.dimensions or gen.query_intent.filters
            or gen.query_intent.explicit_factors)
        decision = decide(confidence, sql_ok=sqlval.ok, exec_ok=result.ok,
                          ambiguous=ambiguous,
                          query_intent=gen.query_intent,
                          plan=plan, plan_report=report,
                          demanded_breakdown=bool(demanded))

        if decision.action in (ANSWER, WARN):
            explanation = explain(evidence, analysis, llm=self.llm)
            recommendation = recommend(analysis) if gen.diagnostic else None
        elif decision.action == CLARIFY:
            explanation = self._legacy_clarify(gen.query_intent)
            recommendation = None
        else:
            explanation = ("I'm abstaining because the query did not pass "
                           "safety/validation or returned no reliable data.")
            recommendation = None

        chart = (chart_spec(result, gen.intent)
                 if decision.action in (ANSWER, WARN) else {"kind": "none"})

        return InsightResponse(
            question=question, sql=gen.sql, intent=gen.intent,
            decision=decision, confidence=confidence, analysis=analysis,
            evidence=evidence, result=result, explanation=explanation,
            recommendation=recommendation, chart=chart,
            notes=list(gen.notes)
                  + [f"kpi_issues={kpival.issues}" if kpival.issues else ""]
                  + [f"sql_issues={sqlval.issues}" if sqlval.issues else ""]
                  + [f"legacy_fallback plan_kind={plan.intent_kind}"],
            plan_trace=plan.as_trace(),
        )

    def _legacy_clarify(self, intent) -> str:
        if intent is None:
            return ("I'm not confident enough to answer this. Could you "
                    "specify a KPI (e.g. revenue, margin) and a dimension "
                    "or time window?")
        if intent.unavailable:
            gaps = ", ".join(g.split(":", 1)[-1] for g in intent.unavailable)
            return (f"I can't answer this on the current dataset — it's "
                    f"missing: {gaps}. Load a dataset that includes those "
                    f"columns, or ask about the fields that are available.")
        if intent.dimensions and intent.filters and any(
                f.get("kind") == "metric_lt_zero" for f in intent.filters):
            m = next((f["metric"] for f in intent.filters
                      if f.get("kind") == "metric_lt_zero"), "profit")
            dim = intent.dimensions[0]
            return (f"I can break {m} down by {dim.replace('_', ' ')} and "
                    f"flag the loss-making ones — want {m} by "
                    f"{dim.replace('_', ' ')}, filtered to negatives?")
        if intent.analysis_type == "correlation" and intent.dimensions:
            metrics = " and ".join(intent.metrics) or "the requested metrics"
            dim = intent.dimensions[0]
            return (f"I can show {metrics} together per {dim.replace('_', ' ')} "
                    f"so you can see the relationship. Want that breakdown?")
        if intent.dimensions:
            return (f"I have an overall figure, but the question asks for a "
                    f"breakdown by "
                    f"{', '.join(d.replace('_', ' ') for d in intent.dimensions)}. "
                    f"Want that breakdown?")
        return ("I'm not confident enough to answer this. Could you specify "
                "a KPI and a dimension or time window?")
