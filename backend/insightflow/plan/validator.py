"""Semantic validation of an AnalyticalPlan against the active dataset.

Structural SQL validation is done by `validation/sql_validator.py`. This
module answers a different question: "is the plan semantically well-formed
against the dataset — does the KPI it wants exist, are its required
columns present, is its aggregation legal, is its grain expressible?"

A plan that fails structural validation is refused. A plan with only
warnings still compiles, but its `fidelity` score is capped, which flows
into `confidence.plan_fidelity` and downgrades the decision.
"""
from __future__ import annotations

from typing import List

from ..knowledge.dataset_registry import ActiveDataset
from ..knowledge.kpi_catalog import KPICatalog
from .plan import (
    AnalyticalPlan, IntentKind, SemanticIssue, ValidationReport,
)


class PlanValidator:
    def __init__(self, ds: ActiveDataset, catalog: KPICatalog):
        self.ds = ds
        self.catalog = catalog

    def validate(self, plan: AnalyticalPlan) -> ValidationReport:
        issues: List[SemanticIssue] = []

        if plan.intent_kind == IntentKind.AMBIGUOUS:
            return ValidationReport(ok=False, fidelity=0.0, issues=[
                SemanticIssue("ambiguous", "Question is too vague to plan.",
                              severity="warning"),
            ])

        if plan.intent_kind == IntentKind.UNSUPPORTED:
            for u in plan.unavailable:
                issues.append(SemanticIssue(
                    "unbindable",
                    f"Dataset {self.ds.name!r} cannot satisfy: {u}",
                ))
            return ValidationReport(ok=False, fidelity=0.0, issues=issues)

        # A plan that carries unavailable items but has been given a
        # bindable shape (say, "revenue by state" → total_revenue with
        # dimension:state unavailable) is only PARTIALLY answerable —
        # flag as error so the decision path CLARIFIES and the fidelity
        # signal drops.
        if plan.unavailable:
            for u in plan.unavailable:
                issues.append(SemanticIssue(
                    "unbindable",
                    f"Dataset {self.ds.name!r} cannot satisfy: {u}",
                ))
            return ValidationReport(ok=False, fidelity=0.0, issues=issues)

        # ---------- KPIs ----------
        for m in plan.measures:
            kpi = self.catalog.get(m.kpi_id)
            if kpi is None:
                issues.append(SemanticIssue(
                    "missing_kpi",
                    f"KPI '{m.kpi_id}' not defined for dataset "
                    f"{self.ds.name!r}",
                ))
                continue
            # required columns present?
            for c in kpi.required_columns:
                if c not in self.ds.columns:
                    issues.append(SemanticIssue(
                        "missing_column",
                        f"KPI '{kpi.kpi_id}' needs column '{c}' — not present",
                    ))
            # aggregation ↔ column-type sanity
            if kpi.aggregation in ("sum", "avg") and kpi.required_columns:
                col = kpi.required_columns[0]
                info = self.ds.columns.get(col)
                if info is not None and not info.is_numeric:
                    issues.append(SemanticIssue(
                        "bad_aggregation",
                        f"KPI '{kpi.kpi_id}' aggregates '{col}' with "
                        f"{kpi.aggregation.upper()}, but '{col}' is not numeric",
                    ))
            # formula must match the catalog's canonical form (guards
            # against a mutated MeasureRef.formula).
            if m.formula and m.formula != kpi.formula:
                issues.append(SemanticIssue(
                    "bad_aggregation",
                    f"KPI '{kpi.kpi_id}' formula deviates from catalog: "
                    f"plan uses {m.formula!r} vs catalog {kpi.formula!r}",
                    severity="warning",
                ))

        # ---------- Dims ----------
        for d in plan.dims:
            if d.column not in self.ds.columns:
                issues.append(SemanticIssue(
                    "missing_column",
                    f"Dimension column '{d.column}' not present in "
                    f"dataset {self.ds.name!r}",
                ))

        # ---------- Grain ----------
        if plan.grain and plan.grain.kind == "time":
            col = plan.grain.time_column
            if col not in self.ds.columns:
                issues.append(SemanticIssue(
                    "bad_grain",
                    f"Time grain requires date column '{col}', not present",
                ))
            elif self.ds.columns[col].role != "date":
                issues.append(SemanticIssue(
                    "bad_grain",
                    f"Column '{col}' is not a date column",
                    severity="warning",
                ))

        # ---------- Comparison / contribution ----------
        for spec_name, spec in (("comparison", plan.comparison),
                                 ("contribution", plan.contribution)):
            if spec is None:
                continue
            if spec.time_column not in self.ds.columns:
                issues.append(SemanticIssue(
                    "bad_comparison",
                    f"{spec_name}: date column '{spec.time_column}' not present",
                ))

        # ---------- Filters ----------
        for f in plan.filters:
            if f.column and f.column not in self.ds.columns:
                issues.append(SemanticIssue(
                    "missing_column",
                    f"Filter references missing column '{f.column}'",
                ))
            if f.kind in ("metric_lt", "metric_gt"):
                if not self.catalog.get(f.kpi_id):
                    issues.append(SemanticIssue(
                        "missing_kpi",
                        f"Filter references undefined KPI '{f.kpi_id}'",
                    ))

        # ---------- Fidelity ----------
        errors = [i for i in issues if i.severity == "error"]
        warns = [i for i in issues if i.severity == "warning"]
        if errors:
            fidelity = 0.0
        elif warns:
            fidelity = max(0.4, 1.0 - 0.15 * len(warns))
        else:
            fidelity = 1.0
        return ValidationReport(ok=(not errors), fidelity=fidelity,
                                issues=issues)
