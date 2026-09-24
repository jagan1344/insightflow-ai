"""Analytical Plan pipeline — the general reasoning layer.

Public entry points:

    from insightflow.plan import Planner, AnalyticalPlan, plan_and_compile

The pipeline is:

    question + ActiveDataset + KPICatalog
        → Planner.plan()      → AnalyticalPlan
        → PlanValidator       → ValidationReport (adds semantic issues)
        → SQLCompiler.compile → sql string

Everything is dataset-agnostic. There are no hardcoded question templates
and no hardcoded KPI names outside the demo seed inside `kpi_catalog.py`.
"""
from .plan import (
    AnalyticalPlan, MeasureRef, DimRef, FilterExpr,
    Grain, ComparisonSpec, ContributionSpec, RelativeStatSpec, IntentKind,
    ValidationReport, SemanticIssue,
)
from .planner import Planner
from .compiler import SQLCompiler
from .validator import PlanValidator
from .fidelity import FidelityValidator, FidelityReport, FidelityCheck
from .failure import FailureCategory, classify_failure

__all__ = [
    "AnalyticalPlan", "MeasureRef", "DimRef", "FilterExpr",
    "Grain", "ComparisonSpec", "ContributionSpec", "RelativeStatSpec",
    "IntentKind", "ValidationReport", "SemanticIssue",
    "Planner", "SQLCompiler", "PlanValidator",
    "FidelityValidator", "FidelityReport", "FidelityCheck",
    "FailureCategory", "classify_failure",
]
