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

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .analysis.analyzer import Analysis, analyse
from .analysis.viz import chart_spec
from .execution.executor import QueryResult, run_sql
from .explain.explainer import explain, recommend, plan_evidence_line
from .knowledge.dataset_registry import get_active_dataset
from .knowledge.kpi import KPI, KPIS
from .knowledge.kpi_catalog import build_catalog
from .knowledge.semantic_model import build_semantic_model
from .llm import LLMClient
from .memory import Memory
# Optional — MCP integration is loaded lazily so the orchestrator still
# works when the mcp SDK isn't installed or the config file is missing.
try:
    from .mcp_integration import AgentMCP
except Exception:
    AgentMCP = None  # type: ignore
from .nlsql.generator import GenSQL, generate_sql
from .plan import (
    AnalyticalPlan, FailureCategory, FidelityValidator, IntentKind, Planner,
    PlanValidator, SQLCompiler, ValidationReport, classify_failure,
)
from .reliability.confidence import Confidence, score_confidence
from .reliability.decision import (
    ANSWER, WARN, CLARIFY, ABSTAIN, Decision, decide,
)
from .reliability.evidence import Evidence, build_evidence
from .reliability.result_validator import ResultValidator
from .validation.dialect_validator import DialectReport, validate_dialect
from .validation.kpi_validator import KPIValidationResult, validate_kpi
from .validation.semantic_fulfilment import FulfilmentReport, validate_fulfilment
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
    failure_category: str = FailureCategory.NONE
    diagnostics: Optional[Dict[str, Any]] = None

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
              IntentKind.RATIO, IntentKind.RELATIVE_TO_STAT):
        return "breakdown"
    return "aggregate"


_LAST_SCHEMA: dict = {}


def _schema_change_notes(ds) -> List[str]:
    """Compare the anchor's schema with what was seen on the previous ask
    and report what changed (columns/tables/relationships)."""
    if ds.kind == "demo":
        return []
    try:
        from .execution.executor import db_file_path
        from .knowledge.relational import schema_snapshot, snapshot_diff
        path = db_file_path()
        snap = schema_snapshot(path, ds.table)
    except Exception:
        return []
    old = _LAST_SCHEMA.get((path, ds.table))
    _LAST_SCHEMA[(path, ds.table)] = snap
    if old is None or old == snap:
        return []
    return ["schema_changed: " + snapshot_diff(old, snap)]


class Orchestrator:
    def __init__(self, llm: Optional[LLMClient] = None,
                 memory: Optional[Memory] = None):
        self.llm = llm or LLMClient()
        self.memory = memory or Memory()
        # Phase 5 (2026-10-23): per-orchestrator conversation context
        # for the minimal follow-up resolver. A fresh Orchestrator
        # (one per session) has no shared state with others, so no
        # cross-session leakage.
        from .conversation import ConversationContext
        self._ctx = ConversationContext()

    # ==================================================================
    def ask(self, question: str, *, _ds_override=None, _retry: bool = False,
            _extra_notes: Optional[List[str]] = None) -> InsightResponse:
        ds = _ds_override or get_active_dataset()
        self._cur_ds = ds
        self._extra_notes = list(_extra_notes or [])
        catalog = build_catalog(ds)
        self._extra_notes += _schema_change_notes(ds)
        if ds.kind != "demo" and not ds.columns:
            _p = AnalyticalPlan(intent_kind=IntentKind.AMBIGUOUS,
                                question=question, table=ds.table,
                                notes=["dataset table missing"],
                                unavailable=[f"table:{ds.table}"])
            return self._unanswerable_response(
                question, _p, ValidationReport(ok=False, fidelity=0.0, issues=[]),
                reason=(f"The table '{ds.table}' for dataset '{ds.name}' no "
                        f"longer exists (the schema changed). Re-upload or "
                        f"select another dataset."))

        # -1. Follow-up rewrite (Phase 5). "Now by region", "and in July
        # 2026", "compare it to last month" are rewritten against the
        # last successfully-answered question. If the active dataset
        # has changed since then, no rewrite happens.
        from .conversation import resolve_followup, capture_context
        original_question = question
        question = resolve_followup(question, self._ctx,
                                     active_dataset_id=getattr(ds, "id", None))

        # 0. Pre-SQL safety / intent check. Destructive requests ABSTAIN;
        # forecasting requests CLARIFY (not implemented). Both bypass the
        # planner entirely so no SQL is generated or executed.
        from .safety import check_request
        safety = check_request(question)
        if safety.destructive:
            empty_plan = AnalyticalPlan(
                intent_kind=IntentKind.UNSUPPORTED,
                question=question, table=ds.table,
                notes=["refused: destructive request"],
                unavailable=["destructive_operation"],
            )
            empty_report = ValidationReport(ok=False, fidelity=0.0, issues=[])
            return self._safety_abstain_response(question, empty_plan,
                                                 empty_report, safety.reason)
        if safety.forecast:
            empty_plan = AnalyticalPlan(
                intent_kind=IntentKind.UNSUPPORTED,
                question=question, table=ds.table,
                notes=["refused: forecasting not implemented"],
                unavailable=["forecasting"],
            )
            empty_report = ValidationReport(ok=False, fidelity=0.0, issues=[])
            return self._unanswerable_response(question, empty_plan,
                                                empty_report, safety.reason)
        if safety.unsupported:
            # Unsupported capability (median / percentile / rolling /
            # top-per-group / null-aware / row-level min/max /
            # count-distinct / threshold-on-grouped-metric / list-with-rank).
            # Refuse specifically — do NOT let the planner fall back to
            # total_revenue and emit a semantically unrelated query.
            empty_plan = AnalyticalPlan(
                intent_kind=IntentKind.UNSUPPORTED,
                question=question, table=ds.table,
                notes=[f"refused: unsupported capability={safety.code}"],
                unavailable=[f"capability:{safety.code}"],
            )
            empty_report = ValidationReport(ok=False, fidelity=0.0, issues=[])
            return self._unanswerable_response(question, empty_plan,
                                                empty_report, safety.reason)

        # 1. Plan the question against the active dataset.
        planner = Planner(ds, catalog)
        plan = planner.plan(question)

        # 2. Validate the plan semantically.
        validator = PlanValidator(ds, catalog)
        report = validator.validate(plan)

        # 2b. Adaptive clarification: an ambiguity (date column / join
        # path) is only worth a question if the candidate readings give
        # different answers.
        _alt_items = []
        _skip_alt_caveat = False
        if ds.kind != "demo" and getattr(ds, "rel", None) is not None \
                and plan.is_answerable():
            for _c in ([d.column for d in plan.dims] +
                       [f.column for f in plan.filters if f.column]):
                _sr = ds.rel.source(_c)
                if _sr is not None and _sr.kind == "safe" and _sr.alt_paths:
                    _alt_items.append(f"alternative_path:{_c}")
                    break
        if ds.kind != "demo" and (plan.unavailable or _alt_items) \
                and _ds_override is None:
            try:
                from .clarify.materiality import resolve as _resolve_amb
                from .execution.executor import db_file_path
                _res = _resolve_amb(question, list(plan.unavailable) + _alt_items,
                                    ds, catalog, db_file_path())
            except Exception:
                _res = None
            if _res is not None and _res.kind == "equivalent" \
                    and _res.ambiguity.startswith("alternative_path:"):
                self._extra_notes.append(
                    "path_choice_immaterial=" + _res.ambiguity + ": "
                    + str(len(_res.candidates)) + " join routes give identical results")
                _skip_alt_caveat = True
            elif _res is not None and _res.kind == "equivalent":
                return self.ask(
                    original_question, _ds_override=_res.candidates[0].ds,
                    _retry=_retry, _extra_notes=self._extra_notes + [
                        "ambiguity_immaterial=" + _res.ambiguity + ": "
                        + str(len(_res.candidates)) + " readings give identical results"])
            if _res is not None and _res.kind == "clarify":
                return self._unanswerable_response(
                    question, plan, report, reason=_res.prompt,
                    explanation=_res.prompt)

        if ds.kind != "demo" and _ds_override is None and plan.is_answerable():
            try:
                from .clarify.materiality import weak_value_check as _wv
                from .execution.executor import db_file_path as _dbq
                _wres = _wv(question, plan, ds, catalog, _dbq())
            except Exception:
                _wres = None
            if _wres is not None:
                return self._unanswerable_response(
                    question, plan, report, reason=_wres.prompt,
                    explanation=_wres.prompt)

        # 3. Fall back to the legacy generator ONLY on the demo dataset,
        #    where 55 regression tests depend on its behaviour.
        #
        #    On uploaded datasets we NEVER fall back — the plan is
        #    authoritative. In particular, an AMBIGUOUS plan on an
        #    uploaded dataset must CLARIFY cleanly (no fabricated SQL,
        #    no accidental "SUM(sales)" answer to "meaning of life").
        if ds.kind == "demo" and (plan.intent_kind == IntentKind.AMBIGUOUS
                                    or not report.ok):
            return self._legacy_ask(question, ds, plan, report)
        if plan.intent_kind == IntentKind.AMBIGUOUS:
            return self._unanswerable_response(
                question, plan, report,
                reason=(
                    "Question is too vague or off-scope for the "
                    f"loaded dataset ({ds.name!r}). Try asking about a "
                    "specific measure in the dataset — optionally with "
                    "a breakdown, time window, or comparison."))

        # 4. Compile.
        compiler = SQLCompiler(ds, catalog)
        sql = compiler.compile(plan)

        if not sql:
            return self._unanswerable_response(
                question, plan, report,
                reason="Could not compile a SQL query for this plan.")

        # 5a. Plan → SQL fidelity check (rejects "executes but doesn't
        # answer" SQL before we run it).
        fidelity = FidelityValidator().check(plan, sql, getattr(ds, 'rel', None))

        # 5b. Structural SQL validation.
        sqlval = validate_sql(sql)

        # 5c. Dialect compatibility — reject Postgres/MSSQL/MySQL
        # idioms before they hit SQLite. Rule-based compiler emits
        # SQLite SQL, so this almost never fires on the deterministic
        # path; it's the gate that catches an LLM-text-to-SQL fallback
        # or a future compiler regression.
        dialect = validate_dialect(sql, dialect="sqlite")
        if sqlval.ok and not dialect.ok:
            sqlval = ValidationResult(
                ok=False, score=0.0,
                issues=list(sqlval.issues) + list(dialect.issues),
                referenced_tables=list(sqlval.referenced_tables),
            )

        # 5d. Cost pre-flight (cartesian joins / runaway scans are not run).
        if sqlval.ok:
            try:
                from .config import settings as _cs
                from .execution.cost_guard import analyze as _analyze_cost
                from .execution.executor import db_file_path as _dbp
                if _cs.database_url.startswith("sqlite"):
                    _cost = _analyze_cost(_dbp(), sql, _cs.max_scan_cost)
                    if _cost.blocked:
                        return self._unanswerable_response(
                            question, plan, report,
                            reason="Query not run (too expensive or unsafe): "
                                   + "; ".join(_cost.reasons))
            except Exception:
                pass

        # 6. Execute if valid.
        if sqlval.ok:
            result = run_sql(sql)
            if (not result.ok and not _retry and re.search(
                    r"no such (table|column)", result.error or "", re.I)):
                # Schema changed under us: drop stale metadata, replan once.
                from .knowledge.schema_agent import refresh_schema
                refresh_schema()
                return self.ask(original_question, _retry=True,
                                _extra_notes=self._extra_notes +
                                ["schema_refreshed_after_execution_error"])
        else:
            result = QueryResult(
                error="SQL failed validation: " + "; ".join(sqlval.issues))

        # 6a. Post-aggregation statistic (Phase 4). For POST_AGG_STAT
        # plans the compiler emitted a column-SELECT; we fetch the
        # whole column (bypassing the result row-cap in run_sql because
        # a sample is semantically wrong for median/percentile/stddev)
        # and reduce in Python.
        if plan.intent_kind == IntentKind.POST_AGG_STAT and sqlval.ok:
            from .analysis import stats as _stats
            import sqlalchemy as _sa
            spec = next((n for n in (plan.notes or [])
                          if n.startswith("post_agg_stat=")), "")
            if spec:
                body = spec.split("=", 1)[1]
                stat_part, _col = body.rsplit(":", 1)
                if ":" in stat_part:
                    stat_name, pct = stat_part.split(":", 1)
                    pct_val = float(pct)
                else:
                    stat_name, pct_val = stat_part, None
                # Direct unbounded fetch for the stat.
                from .execution.executor import get_engine
                vals = []
                try:
                    with get_engine().connect() as c:
                        for row in c.execute(_sa.text(sql)):
                            v = row[0]
                            if v is not None:
                                vals.append(float(v))
                except Exception as e:
                    result = QueryResult(error=str(e))
                    vals = []
                if stat_name == "median":
                    out = _stats.median(vals)
                elif stat_name == "percentile" and pct_val is not None:
                    out = _stats.percentile(vals, pct_val)
                elif stat_name == "stddev":
                    out = _stats.stdev(vals)
                elif stat_name == "variance":
                    out = _stats.variance(vals)
                else:
                    out = None
                alias = plan.measures[0].kpi_id if plan.measures \
                         else stat_name
                if result.ok:
                    result = QueryResult(
                        rows=[(out,)], columns=[alias], error=None)

        # 6b. Result validation (post-execution semantic checks).
        result_report = ResultValidator().check(plan, result)

        # 6c. Semantic fulfilment — did the executed result actually
        # answer the planned intent? e.g. a 9-month trend question
        # that returns a single aggregate row is "SQL executed OK but
        # the question wasn't answered".
        fulfilment = validate_fulfilment(plan, result)

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
        # For contribution plans we already have the per-dim base/target
        # /delta rows in the executed result — build the summary from
        # those directly. The legacy `analyse(intent="diagnostic")`
        # branch re-queries the demo `orders` table, which returns
        # nonsense on uploaded datasets.
        if plan.intent_kind == IntentKind.CONTRIBUTION and result.ok \
                and result.rows and plan.contribution is not None:
            analysis = self._contribution_summary(plan, result, headline_kpi)
        elif plan.intent_kind == IntentKind.SHARE_OF_TOTAL and result.ok \
                and result.rows:
            analysis = self._share_summary(plan, result, headline_kpi)
        else:
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

        # 10. Confidence (plan-aware + fidelity + result-report aware).
        confidence = score_confidence(
            sqlval, kpival, result,
            ambiguous=False, out_of_scope=False,
            query_intent=None, sql=sql,
            plan=plan, plan_report=report,
            fidelity_score=fidelity.score,
            result_score=result_report.score,
        )

        # 11. Decision.
        demanded = bool(plan.dims or plan.filters
                        or plan.comparison or plan.contribution
                        or plan.relative_stat)
        decision = decide(confidence, sql_ok=sqlval.ok, exec_ok=result.ok,
                          ambiguous=False, query_intent=None,
                          plan=plan, plan_report=report,
                          demanded_breakdown=demanded,
                          fidelity_ok=fidelity.ok,
                          result_ok=result_report.ok)

        # 11a. Semantic-fulfilment gate (overrides a would-be ANSWER
        # when the executed result failed to match the planned intent).
        if (not fulfilment.ok) and decision.action in (ANSWER, WARN):
            decision = Decision(
                WARN if fulfilment.score >= 0.4 else CLARIFY,
                "semantic fulfilment check failed: "
                + "; ".join(fulfilment.issues),
            )

        # 11b. Relative-period coverage check (Defect B). If the time
        # filter came from a relative-period phrase ("last year",
        # "last month", ...) and executing the query returned no actual
        # data (either zero rows, or SUM/COUNT aggregated to NULL
        # because the filter matched no base rows), the dataset doesn't
        # cover the requested window. A quiet ANSWER-with-no-rows is
        # wrong — downgrade to CLARIFY with a specific message.
        def _is_data_empty(res) -> bool:
            if not res.ok:
                return False
            if not res.rows:
                return True
            # SUM(x) on an empty filter yields [(None,)] etc. Treat an
            # aggregate result where every numeric cell is None as empty.
            for row in res.rows:
                for v in row:
                    if v is None:
                        continue
                    if isinstance(v, (int, float)) and v == 0 \
                            and len(res.rows) == 1:
                        # A single zero row from COUNT(*) on empty filter
                        # should also count as "no data for that period".
                        continue
                    # anything non-None, non-zero → real data
                    return False
            return True

        rel_note = next((n for n in (plan.notes or [])
                          if n.startswith("relative_period=")), None)
        if (rel_note is not None and _is_data_empty(result)
                and decision.action in (ANSWER, WARN)):
            _rel_kind = rel_note.split("=", 1)[1].split(":", 1)[0]
            _rel_range = rel_note.split(":", 1)[1] if ":" in rel_note else ""
            decision = Decision(
                CLARIFY,
                f"'{_rel_kind.replace('_', ' ')}' resolved to "
                f"{_rel_range} but the dataset has no rows in that "
                f"range. Try a period inside the dataset's date range.",
            )

        # 11c. Mention-coverage veto: a categorical value named in the
        # question that appears nowhere in the executed SQL means part of
        # the question was dropped. Plan/SQL fidelity cannot see this
        # because both come from the same (lossy) reading of the question.
        if decision.action in (ANSWER, WARN) and sql:
            try:
                from .config import settings as _st
                from .reliability.mention_coverage import unrepresented_mentions
                _url = _st.database_url
                _dbp = _url.split(":///", 1)[1] if ":///" in _url else _url
                _miss = unrepresented_mentions(question, sql, _dbp, ds.table)
            except Exception:
                _miss = []
            try:
                from .reliability.mention_coverage import unrepresented_table_nouns
                _tn = unrepresented_table_nouns(question, sql, getattr(ds, "rel", None))
            except Exception:
                _tn = []
            try:
                from .reliability.mention_coverage import unrepresented_column_mentions
                _cm = unrepresented_column_mentions(question, sql, ds)
                from .reliability.mention_coverage import unrepresented_column_words
                _cm = _cm + [c for c in unrepresented_column_words(question, sql, ds)
                             if c not in _cm]
            except Exception:
                _cm = []
            try:
                from .reliability.mention_coverage import unrepresented_years
                _yr = unrepresented_years(question, sql)
            except Exception:
                _yr = []
            try:
                from .reliability.mention_coverage import unrepresented_iso_dates
                _yr = _yr + unrepresented_iso_dates(question, sql)
            except Exception:
                pass
            if _yr and not _miss and not _tn:
                decision = Decision(
                    CLARIFY,
                    "the question names " + ", ".join(_yr) + " but the "
                    "generated query has no such time constraint, so the "
                    "answer would cover all periods")
                confidence.signals["mention_coverage"] = 0.0
                confidence.score = min(confidence.score, 0.30)
            try:
                from .reliability.mention_coverage import unrepresented_numbers
                from .plan.planner import _value_index, _value_mentions
                _vt = ([lo for lo, _c in _value_mentions(question, _value_index(ds))]
                       if ds.kind != "demo" else [])
                _nums = unrepresented_numbers(question, sql, _vt)
            except Exception:
                _nums = []
            if _nums and not _miss and not _tn and not _yr:
                decision = Decision(
                    CLARIFY,
                    "the question contains the number(s) " + ", ".join(_nums) +
                    " but the generated query does not use them, so a "
                    "threshold or quantity would be ignored")
                confidence.signals["mention_coverage"] = 0.0
                confidence.score = min(confidence.score, 0.30)
            try:
                from .reliability.mention_coverage import unexplained_words
                _uh, _us = unexplained_words(question, ds, catalog)
                if plan.intent_kind in ("null_count", "distinct_count", "extremum",
                                        "threshold_grouped", "relative_to_stat") \
                        or any(m.aggregation == "count_distinct" for m in plan.measures):
                    _uh, _us = [], []      # operator words ("missing", "distinct") are consumed by the plan
            except Exception:
                _uh, _us = [], []
            self._unexplained_soft = _us
            if _uh and not _miss and not _tn and not _yr and not _nums:
                decision = Decision(
                    CLARIFY,
                    "I don't know how " + ", ".join(f"'{w}'" for w in _uh) +
                    " maps to this data, so the answer could ignore part of "
                    "your question")
                confidence.signals["mention_coverage"] = 0.0
                confidence.score = min(confidence.score, 0.30)
            if _cm and not _miss and not _tn:
                decision = Decision(
                    CLARIFY,
                    "the question mentions column(s) " +
                    ", ".join(f"'{c}'" for c in _cm) +
                    " that the generated query does not use, so it would "
                    "ignore part of your question")
                confidence.signals["mention_coverage"] = 0.0
                confidence.score = min(confidence.score, 0.30)
            if _tn and not _miss:
                decision = Decision(
                    CLARIFY,
                    "the question is about " + ", ".join(f"'{n}'" for n in _tn) +
                    ", but the query's base table is '" + ds.table + "' and "
                    "does not involve them, so it would answer at the wrong "
                    "grain")
                confidence.signals["mention_coverage"] = 0.0
                confidence.score = min(confidence.score, 0.30)
            if _miss:
                _desc = "; ".join(f"'{m.value}' (in {', '.join(m.where)})"
                                  for m in _miss)
                decision = Decision(
                    CLARIFY,
                    "the question mentions " + _desc + " but the query I "
                    "generated does not use it, so the answer would ignore "
                    "part of your question")
                confidence.signals["mention_coverage"] = 0.0
                confidence.score = min(confidence.score, 0.30)

        # 11c2. Wording audit: does the executed query answer THIS question?
        if decision.action in (ANSWER, WARN) and result.ok and sql:
            try:
                from .verification.intent_audit import audit as _audit
                _af = _audit(question, sql, plan, catalog, len(result.rows))
            except Exception:
                _af = []
            if _af:
                decision = Decision(
                    CLARIFY,
                    "the query may answer a different question than the one "
                    "asked: " + "; ".join(f.detail for f in _af))
                confidence.signals["semantic_audit_violations"] = float(len(_af))
                confidence.score = min(confidence.score, 0.30)

        # 11d. Independent verification + sensitivity diagnostics.
        _caveats: List[str] = []
        if decision.action in (ANSWER, WARN) and result.ok and sql:
            try:
                from .verification.answer_verifier import verify as _verify
                from .execution.executor import db_file_path as _dbp2
                _vrep = _verify(plan, sql, list(result.rows), ds, catalog,
                                _dbp2())
            except Exception:
                _vrep = None
            if _vrep is not None:
                if _vrep.violations:
                    decision = Decision(
                        CLARIFY,
                        "independent verification failed: "
                        + "; ".join(f.detail for f in _vrep.violations))
                    confidence.score = min(confidence.score, 0.30)
                confidence.signals["verification_violations"] = float(
                    len(_vrep.violations))
                confidence.signals["sensitivity_flags"] = float(
                    len(_vrep.diagnostics))
                _caveats = [f"{f.name}: {f.detail}" for f in _vrep.diagnostics]
                self._extra_notes += [f"{f.severity}:{f.name}:{f.detail}"
                                      for f in _vrep.findings]

        for _w in getattr(self, "_unexplained_soft", []):
            _caveats.append(f"'{_w}' was not mapped to any column or value and was not applied")
        self._unexplained_soft = []
        for _n in getattr(self, "_extra_notes", []):
            if _n.startswith(("ambiguity_immaterial", "path_choice_immaterial")):
                _caveats.append("the question could be read more than one way; every reading "
                                "gave this same result")
                break
        # 11e. Standing caveats that must not be silent: grain of related
        # measures and joins that rest on an inferred (undeclared) FK.
        _rel_ctx = getattr(ds, "rel", None)
        if _caveats and decision.action == ANSWER and _rel_ctx is None:
            decision = Decision(WARN, "answer rests on: " + "; ".join(_caveats))
        if decision.action in (ANSWER, WARN) and sql and _rel_ctx is not None:
            if any("{{dim:" in (m.formula or "") for m in plan.measures):
                _caveats.append(
                    f"a measure stored on a related table is counted once per "
                    f"'{ds.table}' row, so a value shared by several rows is "
                    f"counted several times")
            _weak = [f"{e.child_table}.{e.child_col}->{e.parent_table}.{e.parent_col}"
                     for e in _rel_ctx.schema.edges if e.status == "inferred"
                     and re.search(rf"\b{re.escape(e.parent_table)}\b", sql)
                     and re.search(rf"\b{re.escape(e.child_table)}\b", sql)
                     and e.child_col in sql]
            _alts = []
            for _c in ([d.column for d in plan.dims] +
                       [f.column for f in plan.filters if f.column]):
                _sr = _rel_ctx.source(_c)
                if _sr is not None and _sr.alternatives:
                    _alts.append(f"'{_c}' is read through "
                                 f"{_sr.steps[-1].edge.child_table}."
                                 f"{_sr.steps[-1].edge.child_col}; it is also "
                                 f"reachable via {_sr.alternatives[0]}")
            if _alts and not _skip_alt_caveat:
                _caveats.append("; ".join(_alts))
            if _weak:
                _caveats.append("relationship inferred from names and values, "
                                "not declared: " + ", ".join(_weak))
            if _caveats and decision.action == ANSWER:
                decision = Decision(WARN, "answer rests on: " + "; ".join(_caveats))

        # 12. Explain (evidence-first).
        if decision.action in (ANSWER, WARN):
            trace = plan_evidence_line(plan, catalog.table)
            body = explain(evidence, analysis, llm=self.llm, plan=plan)
            # Tell the user when we truncated a compound question so
            # they know the second half wasn't answered.
            dropped = ""
            for note in (plan.notes or []):
                if note.startswith("compound_question_dropped_suffix="):
                    dropped = note.split("=", 1)[1].strip("'\"")
                    break
            if dropped:
                body = (f"{body}\n\nNote: this question had multiple parts. "
                        f"I answered the first one. Ask the follow-up "
                        f"separately for a clean answer: {dropped!r}")
            explanation = f"{trace}\n\n{body}"
            if _caveats:
                explanation += "\n\nCaveats: " + "; ".join(_caveats)
            recommendation = (recommend(analysis)
                              if plan.intent_kind == IntentKind.CONTRIBUTION
                              else None)
        elif decision.action == CLARIFY:
            explanation = (self._clarify_message_from_plan(plan, report)
                           if plan.unavailable or not decision.reason
                           else decision.reason[0].upper() + decision.reason[1:] + ".")
            recommendation = None
        else:  # ABSTAIN
            explanation = ("I'm abstaining because the query did not pass "
                           "safety/validation or returned no reliable data.")
            recommendation = None

        # 12b. Semantic layer: typed spec -> type check -> preservation
        # (spec vs executed SQL vs rows vs the written answer).
        _sem = None
        _sem_err = None
        if decision.action in (ANSWER, WARN) and ds.kind != "demo" and result.ok and sql \
                and plan.intent_kind in ("direct_kpi", "breakdown", "top_n", "trend", "ratio"):
            try:
                from .semantics import verify_semantics
                _sem = verify_semantics(question, plan, sql, result, explanation, ds, catalog)
            except Exception as _e:               # fail closed: an unverified answer is not approved
                _sem = None
                _sem_err = f"{type(_e).__name__}: {str(_e)[:200]}"
                self._extra_notes.append(f"semantic_verifier_error={type(_e).__name__}")
                decision = Decision(
                    CLARIFY,
                    "the answer could not be checked against what you asked, "
                    "so it is not being given as correct")
                explanation = decision.reason[0].upper() + decision.reason[1:] + "."
                recommendation = None
                confidence.signals["semantic_verifier_error"] = 1.0
                confidence.score = min(confidence.score, 0.30)
            if _sem is not None and _sem.violations:
                decision = Decision(
                    CLARIFY,
                    "the answer may not mean what you asked: "
                    + "; ".join(f.detail for f in _sem.violations[:3]))
                explanation = decision.reason[0].upper() + decision.reason[1:] + "."
                recommendation = None
                confidence.signals["semantic_violations"] = float(len(_sem.violations))
                confidence.score = min(confidence.score, 0.30)

        chart = (chart_spec(result, legacy_intent)
                 if decision.action in (ANSWER, WARN)
                 else {"kind": "none"})

        notes: List[str] = list(self._extra_notes)
        notes.append(f"active_dataset={ds.id} table={ds.table}")
        notes.append(f"plan_kind={plan.intent_kind}")
        if report.issues:
            notes.append("plan_issues=" + "; ".join(
                f"{i.kind}:{i.message}" for i in report.issues))
        if kpival.issues:
            notes.append(f"kpi_issues={kpival.issues}")
        if sqlval.issues:
            notes.append(f"sql_issues={sqlval.issues}")
        if not fidelity.ok:
            notes.append("fidelity_failed=" + "; ".join(
                f"{c.name}:{c.detail}" for c in fidelity.failed()))
        if result_report.issues:
            notes.append("result_issues=" + "; ".join(
                f"{i.severity}:{i.message}" for i in result_report.issues))

        failure = (classify_failure(
            plan, report, sql, sqlval, fidelity, result, kpival=kpival,
            result_ok=result_report.ok,
        ) if decision.action not in (ANSWER, WARN) else FailureCategory.NONE)

        diagnostics = self._diagnostics(
            question=question, ds=ds, plan=plan, plan_report=report,
            sql=sql, sqlval=sqlval, fidelity=fidelity,
            result=result, result_report=result_report,
            kpival=kpival, confidence=confidence, decision=decision,
            failure=failure,
        )

        if _sem_err:
            diagnostics["semantic_verifier_error"] = _sem_err
        if _sem is not None:
            diagnostics["semantic_spec"] = _sem.spec.as_dict()
            diagnostics["semantic_findings"] = [
                {"rule": f.rule, "severity": f.severity, "detail": f.detail}
                for f in _sem.findings]

        # Keep `.intent` as the LEGACY intent string so existing test
        # assertions that inspect `resp.intent == 'diagnostic'` still hold.
        response = InsightResponse(
            question=question, sql=sql,
            intent=legacy_intent, decision=decision,
            confidence=confidence, analysis=analysis, evidence=evidence,
            result=result, explanation=explanation,
            recommendation=recommendation, chart=chart, notes=notes,
            plan_trace=plan.as_trace(),
            failure_category=failure, diagnostics=diagnostics,
        )
        self.memory.add(question, decision.action, confidence.score)
        # Capture context for Phase 5 follow-ups ONLY when we actually
        # answered. CLARIFY/ABSTAIN leaves prior context intact.
        if decision.action in (ANSWER, WARN):
            capture_context(question, self._ctx,
                             dataset_id=getattr(ds, "id", None))
        return response

    # ==================================================================
    def _contribution_summary(self, plan, result, kpi) -> Analysis:
        """Build a diagnostic-style summary from the contribution query's
        own rows (columns: dim, base_value, target_value, delta)."""
        from .analysis.analyzer import Analysis, Contributor
        cs = plan.contribution
        rows = result.rows
        # rows are sorted by delta already (compiler emits ORDER BY delta)
        contributors = []
        prev_total = 0.0
        curr_total = 0.0
        for r in rows:
            try:
                dim_name = str(r[0])
                base_v = float(r[1] or 0.0)
                targ_v = float(r[2] or 0.0)
                delta = float(r[3] or 0.0)
            except (TypeError, ValueError):
                continue
            prev_total += base_v
            curr_total += targ_v
            pct = (delta / base_v * 100.0) if base_v else 0.0
            contributors.append(Contributor(
                dimension=cs.dim_column, name=dim_name,
                prev=base_v, curr=targ_v, delta=delta, pct=pct))
        total_delta = curr_total - prev_total
        pct_change = (total_delta / prev_total * 100.0) if prev_total else 0.0
        kpi_name = kpi.name if kpi else "Value"
        # Pick the most-extreme contributor in the direction requested.
        want_decline = cs.direction == "decline"
        candidates = [c for c in contributors
                       if (c.delta < 0 if want_decline else True)] or contributors
        top = (min(candidates, key=lambda c: c.delta) if want_decline
               else max(candidates, key=lambda c: abs(c.delta)))
        headline = (
            f"{kpi_name} changed from {prev_total:,.2f} to {curr_total:,.2f} "
            f"({total_delta:+,.2f}, {pct_change:+.1f}%) between "
            f"{cs.base_period} and {cs.target_period}."
        )
        if top is not None:
            headline += (
                f" Largest {'decline' if top.delta < 0 else 'gain'} came from "
                f"{cs.dim_column} '{top.name}' ({top.delta:+,.2f}, "
                f"{top.pct:+.1f}%)."
            )
        return Analysis(summary=headline, headline_value=curr_total,
                        contributors=contributors,
                        prev_total=prev_total, curr_total=curr_total)

    # ==================================================================
    def _share_summary(self, plan, result, kpi) -> Analysis:
        """Build a summary for share_of_total. The last column is the
        share ratio (0..1). We render it as a percentage in the natural-
        language answer, and populate `headline_value` so the chart
        renders % on the axis when the frontend inspects it."""
        from .analysis.analyzer import Analysis
        rows = result.rows
        cols = [c.lower() for c in (result.columns or [])]
        share_idx = None
        for i, c in enumerate(cols):
            if c == "share" or c.endswith("_share") or c.endswith("_pct"):
                share_idx = i; break
        if share_idx is None:
            share_idx = len(cols) - 1  # fall back to last

        # Sort by share desc, pick the top slice
        try:
            top = max(rows, key=lambda r: float(r[share_idx] or 0.0))
            top_label = str(top[0])
            top_share = float(top[share_idx] or 0.0)
        except (TypeError, ValueError):
            top_label, top_share = "n/a", 0.0

        kpi_name = kpi.name if kpi else "value"
        n = len(rows)
        summary = (
            f"{kpi_name} split across {n} "
            f"{result.columns[0] if result.columns else 'group'} values — "
            f"leader: {top_label} ({top_share * 100:.1f}%)."
        )
        return Analysis(summary=summary, headline_value=top_share)

    # ==================================================================
    def _diagnostics(self, *, question, ds, plan, plan_report, sql,
                      sqlval, fidelity, result, result_report, kpival,
                      confidence, decision, failure) -> dict:
        return {
            "question": question,
            "dataset": {"id": ds.id, "kind": ds.kind, "table": ds.table},
            "plan": plan.as_trace(),
            "plan_validation": {
                "ok": plan_report.ok, "fidelity": plan_report.fidelity,
                "issues": [
                    {"kind": i.kind, "severity": i.severity,
                     "message": i.message}
                    for i in plan_report.issues
                ],
            },
            "sql": sql,
            "sql_validation": {
                "ok": sqlval.ok, "issues": list(sqlval.issues),
                "referenced_tables": list(sqlval.referenced_tables),
            },
            "fidelity": {
                "ok": fidelity.ok, "score": fidelity.score,
                "checks": [
                    {"name": c.name, "passed": c.passed, "detail": c.detail}
                    for c in fidelity.checks
                ],
            },
            "execution": {"ok": result.ok, "n_rows": result.n_rows,
                           "error": result.error},
            "result_validation": {
                "ok": result_report.ok, "score": result_report.score,
                "issues": [
                    {"severity": i.severity, "message": i.message}
                    for i in result_report.issues
                ],
            },
            "kpi_validation": {
                "recognised": kpival.kpi_recognised,
                "rules_passed": kpival.rules_passed,
                "score": kpival.score,
                "issues": list(kpival.issues),
            },
            "confidence": {"score": confidence.score,
                            "signals": dict(confidence.signals)},
            "decision": {"action": decision.action, "reason": decision.reason},
            "failure_category": failure,
        }

    # ==================================================================
    def _clarify_message_from_plan(self, plan: AnalyticalPlan,
                                    report: ValidationReport) -> str:
        if plan.unavailable:
            from .clarify.messages import targeted_message
            _t0 = targeted_message(plan.unavailable,
                                   getattr(self, "_cur_ds", None))
            if _t0:
                return _t0
        if plan.intent_kind == IntentKind.AMBIGUOUS:
            return ("This question is too open-ended to answer from the data "
                    "alone. Try naming a specific metric (e.g. revenue, "
                    "profit) and — optionally — a breakdown, time window "
                    "or comparison.")
        if plan.unavailable:
            from .clarify.messages import targeted_message
            _t = targeted_message(plan.unavailable,
                                  getattr(self, "_cur_ds", None))
            if _t:
                return _t
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
    def _safety_abstain_response(self, question: str, plan: AnalyticalPlan,
                                   report: ValidationReport, reason: str
                                   ) -> InsightResponse:
        """ABSTAIN response for destructive-intent refusals. Reuses the
        shell of `_unanswerable_response` but hard-codes the Decision to
        ABSTAIN and the failure category to UNSUPPORTED, since the
        pipeline is deliberately not planning / executing the request."""
        empty = QueryResult()
        sqlval = ValidationResult(ok=False, score=0.0, issues=[reason])
        kpival = KPIValidationResult(
            kpi_recognised=False, rules_passed=False, score=0.0,
            issues=[reason])
        confidence = score_confidence(
            sqlval, kpival, empty, ambiguous=False, out_of_scope=True,
            query_intent=None, sql="", plan=plan, plan_report=report)
        decision = Decision(ABSTAIN, reason)
        evidence = build_evidence(question, "", None, {}, empty)
        analysis = Analysis(summary=reason)
        diagnostics = {
            "question": question,
            "dataset": {"id": getattr(plan, "table", ""),
                         "kind": "unknown", "table": plan.table},
            "plan": plan.as_trace(),
            "plan_validation": {"ok": False, "fidelity": 0.0,
                                 "issues": [{"kind": "safety",
                                              "severity": "error",
                                              "message": reason}]},
            "sql": "", "sql_validation": {"ok": False, "issues": [reason]},
            "fidelity": {"ok": False, "score": 0.0, "checks": []},
            "execution": {"ok": False, "n_rows": 0, "error": reason},
            "result_validation": {"ok": False, "score": 0.0, "issues": []},
            "kpi_validation": {"recognised": False, "rules_passed": False,
                                "score": 0.0, "issues": [reason]},
            "confidence": {"score": confidence.score,
                            "signals": dict(confidence.signals)},
            "decision": {"action": decision.action,
                         "reason": decision.reason},
            "failure_category": FailureCategory.UNSUPPORTED_DATA,
            "safety": {"destructive": True, "reason": reason},
        }
        return InsightResponse(
            question=question, sql="", intent=plan.intent_kind,
            decision=decision, confidence=confidence, analysis=analysis,
            evidence=evidence, result=empty, explanation=reason,
            recommendation=None, chart={"kind": "none"},
            notes=[reason], plan_trace=plan.as_trace(),
            failure_category=FailureCategory.UNSUPPORTED_DATA,
            diagnostics=diagnostics,
        )

    # ==================================================================
    def _unanswerable_response(self, question: str, plan: AnalyticalPlan,
                                report: ValidationReport, reason: str,
                                explanation: Optional[str] = None
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
        explanation = explanation or self._clarify_message_from_plan(plan, report)
        failure = classify_failure(
            plan, report, "", ValidationResult(ok=False, score=0.0,
                                                 issues=[reason]),
            None, empty, kpival=kpival, result_ok=False,
        )
        diagnostics = {
            "question": question,
            "dataset": {"id": getattr(plan, "table", ""),
                         "kind": "unknown", "table": plan.table},
            "plan": plan.as_trace(),
            "plan_validation": {"ok": report.ok, "fidelity": report.fidelity,
                                 "issues": [{"kind": i.kind,
                                              "severity": i.severity,
                                              "message": i.message}
                                             for i in report.issues]},
            "sql": "", "sql_validation": {"ok": False, "issues": [reason]},
            "fidelity": {"ok": False, "score": 0.0, "checks": []},
            "execution": {"ok": False, "n_rows": 0, "error": reason},
            "result_validation": {"ok": False, "score": 0.0, "issues": []},
            "kpi_validation": {"recognised": False, "rules_passed": False,
                                "score": 0.0, "issues": [reason]},
            "confidence": {"score": confidence.score,
                            "signals": dict(confidence.signals)},
            "decision": {"action": decision.action, "reason": decision.reason},
            "failure_category": failure,
        }
        return InsightResponse(
            question=question, sql="", intent=plan.intent_kind,
            decision=decision, confidence=confidence, analysis=analysis,
            evidence=evidence, result=empty, explanation=explanation,
            recommendation=None, chart={"kind": "none"},
            notes=[reason], plan_trace=plan.as_trace(),
            failure_category=failure, diagnostics=diagnostics,
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
            failure = FailureCategory.AMBIGUITY if is_vague else FailureCategory.UNSUPPORTED_DATA
            diagnostics = {
                "question": question,
                "dataset": {"id": ds.id, "kind": ds.kind, "table": ds.table},
                "plan": plan.as_trace(),
                "plan_validation": {"ok": report.ok,
                                     "fidelity": report.fidelity,
                                     "issues": []},
                "sql": "", "sql_validation": {"ok": False, "issues": []},
                "fidelity": {"ok": False, "score": 0.0, "checks": []},
                "execution": {"ok": False, "n_rows": 0, "error": ""},
                "result_validation": {"ok": False, "score": 0.0, "issues": []},
                "kpi_validation": {"recognised": False,
                                    "rules_passed": False, "score": 0.0,
                                    "issues": [reason]},
                "confidence": {"score": conf.score,
                                "signals": dict(conf.signals)},
                "decision": {"action": decision.action,
                              "reason": decision.reason},
                "failure_category": failure,
            }
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
                failure_category=failure, diagnostics=diagnostics,
            )

        sqlval = validate_sql(gen.sql)
        # Dialect check (same gate as the plan path). The LLM path is
        # the usual source of EXTRACT(), DATE_TRUNC(), etc.
        dialect = validate_dialect(gen.sql, dialect="sqlite")
        if sqlval.ok and not dialect.ok:
            sqlval = ValidationResult(
                ok=False, score=0.0,
                issues=list(sqlval.issues) + list(dialect.issues),
                referenced_tables=list(sqlval.referenced_tables),
            )
        if sqlval.ok:
            result = run_sql(gen.sql)
        else:
            result = QueryResult(
                error="SQL failed validation: " + "; ".join(sqlval.issues))
        kpival = validate_kpi(gen.kpi, result)
        # Semantic fulfilment vs. the plan the planner originally built
        # (not the legacy GenSQL, which has no structured intent beyond
        # month/dimension). This catches "LLM wrote SQL but it answers a
        # different question than the user asked" in the legacy path.
        legacy_fulfilment = validate_fulfilment(plan, result)
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

        # Semantic-fulfilment gate on the legacy / LLM path. Overrides
        # a would-be ANSWER when the executed SQL did not match the
        # planned intent (e.g. a trend question answered with a single
        # aggregate row, or a forecast question answered with history).
        if (not legacy_fulfilment.ok) and decision.action in (ANSWER, WARN):
            decision = Decision(
                WARN if legacy_fulfilment.score >= 0.4 else CLARIFY,
                "semantic fulfilment check failed: "
                + "; ".join(legacy_fulfilment.issues),
            )

        if decision.action in (ANSWER, WARN):
            explanation = explain(evidence, analysis, llm=self.llm, plan=plan)
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

        # A minimal diagnostic block for the legacy path — enough for
        # audit but doesn't fabricate fields it can't fill.
        failure = (classify_failure(
            plan, report, gen.sql, sqlval, None, result, kpival=kpival,
            result_ok=result.ok) if decision.action not in (ANSWER, WARN)
            else FailureCategory.NONE)
        diagnostics = {
            "question": question,
            "dataset": {"id": ds.id, "kind": ds.kind, "table": ds.table},
            "plan": plan.as_trace(),
            "plan_validation": {"ok": report.ok, "fidelity": report.fidelity,
                                 "issues": [{"kind": i.kind,
                                              "severity": i.severity,
                                              "message": i.message}
                                             for i in report.issues]},
            "sql": gen.sql,
            "sql_validation": {"ok": sqlval.ok, "issues": list(sqlval.issues),
                                "referenced_tables": list(sqlval.referenced_tables)},
            "fidelity": {"ok": True, "score": 1.0,
                          "checks": [], "note": "legacy path — not checked"},
            "execution": {"ok": result.ok, "n_rows": result.n_rows,
                           "error": result.error},
            "result_validation": {"ok": True, "score": 1.0, "issues": []},
            "kpi_validation": {"recognised": kpival.kpi_recognised,
                                "rules_passed": kpival.rules_passed,
                                "score": kpival.score,
                                "issues": list(kpival.issues)},
            "confidence": {"score": confidence.score,
                            "signals": dict(confidence.signals)},
            "decision": {"action": decision.action, "reason": decision.reason},
            "failure_category": failure,
        }
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
            failure_category=failure, diagnostics=diagnostics,
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
