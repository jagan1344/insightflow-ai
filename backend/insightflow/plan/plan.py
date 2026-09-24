"""AnalyticalPlan — the intermediate representation between an NL question
and executable SQL.

The plan is a **structured description** of "what the user asked for",
grounded to columns that actually exist on the active dataset. It never
contains English prose or SQL fragments — only references.

Downstream:
    * `PlanValidator` checks that the plan is semantically sound on the
      current dataset (KPI defined, aggregation legal, grain expressible,
      dimensions/filters bound to real columns).
    * `SQLCompiler` lowers a validated plan to a SQL string.
    * `confidence.plan_fidelity` compares the SQL the compiler emitted
      against what the plan promised.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Intent kinds — a small, closed vocabulary. Each kind has a canonical
# lowering rule in the compiler; adding a new kind means adding a lowering,
# not a keyword branch.
# ---------------------------------------------------------------------------

class IntentKind:
    DIRECT_KPI       = "direct_kpi"          # "What's the revenue?"
    BREAKDOWN        = "breakdown"           # "Revenue by region"
    TREND            = "trend"               # "Revenue over time / by month"
    COMPARISON       = "comparison"          # "June vs July revenue"
    GROWTH           = "growth"              # "Revenue growth month-over-month"
    TOP_N            = "top_n"               # "Top 5 products by revenue"
    BOTTOM_N         = "bottom_n"            # "Bottom 3 regions by profit"
    SHARE_OF_TOTAL   = "share_of_total"      # "% of revenue by region"
    RATIO            = "ratio"               # "Profit per order"
    AVERAGE_AT_GRAIN = "average_at_grain"    # "Average monthly revenue"
    CONTRIBUTION     = "contribution"        # "Which region contributed most to the decline?"
    UNSUPPORTED      = "unsupported"         # dataset can't answer this
    AMBIGUOUS        = "ambiguous"           # question needs clarification


ALL_INTENT_KINDS = frozenset({
    IntentKind.DIRECT_KPI, IntentKind.BREAKDOWN, IntentKind.TREND,
    IntentKind.COMPARISON, IntentKind.GROWTH, IntentKind.TOP_N,
    IntentKind.BOTTOM_N, IntentKind.SHARE_OF_TOTAL, IntentKind.RATIO,
    IntentKind.AVERAGE_AT_GRAIN, IntentKind.CONTRIBUTION,
    IntentKind.UNSUPPORTED, IntentKind.AMBIGUOUS,
})


# ---------------------------------------------------------------------------
# Building-block references
# ---------------------------------------------------------------------------

@dataclass
class MeasureRef:
    """A measure the plan wants computed.

    `kpi_id` is a catalog key (e.g. "total_revenue", "profit",
    "avg_order_value") — the compiler resolves it to a formula via the
    KPI catalog, so the SQL is always the catalog's canonical form.
    """
    kpi_id: str
    display_name: str = ""
    # The catalog's formula and aggregation are cached here for the
    # compiler + explainer to read without re-fetching the catalog. Set
    # by `Planner.plan()` when the KPI is bound.
    formula: str = ""
    aggregation: str = ""    # sum | count | count_distinct | avg | ratio | derived
    unit: str = ""           # currency | count | ratio | percent | ""


@dataclass
class DimRef:
    """A dimension to group by."""
    column: str              # physical column name on the active dataset
    display_name: str = ""
    is_time: bool = False
    time_unit: str = ""      # "day" | "week" | "month" | "quarter" | "year"


@dataclass
class FilterExpr:
    """A structured filter. Kept as a small vocabulary so compiler can
    lower each one; free-form SQL is never injected."""
    kind: str                # "eq" | "range" | "in" | "time_range" | "metric_lt" | "metric_gt"
    column: str = ""
    value: object = None
    lo: object = None
    hi: object = None
    # For metric_lt / metric_gt:
    kpi_id: str = ""
    threshold: float = 0.0


@dataclass
class Grain:
    """The row-level unit of the plan."""
    kind: str                # "row" | "time" | "dim"
    time_unit: str = ""      # if kind == "time"
    time_column: str = ""    # physical date column, if kind == "time"


@dataclass
class ComparisonSpec:
    """Two-period comparison."""
    time_column: str
    base_period: str         # e.g. "2026-06"
    target_period: str       # e.g. "2026-07"
    mode: str = "delta"      # "delta" | "pct" | "ratio"


@dataclass
class ContributionSpec:
    """Contribution decomposition of a metric change across a dimension
    between two periods."""
    time_column: str
    base_period: str
    target_period: str
    dim_column: str
    direction: str = "any"   # "decline" | "gain" | "any"


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------

@dataclass
class AnalyticalPlan:
    intent_kind: str = IntentKind.DIRECT_KPI
    measures: List[MeasureRef] = field(default_factory=list)
    dims: List[DimRef] = field(default_factory=list)
    filters: List[FilterExpr] = field(default_factory=list)
    grain: Optional[Grain] = None
    comparison: Optional[ComparisonSpec] = None
    contribution: Optional[ContributionSpec] = None
    top_n: Optional[int] = None
    share_of_total: bool = False
    order_by: str = ""       # "measure_desc" | "measure_asc" | "time_asc" | ""
    # what the planner asked for but couldn't bind on the current dataset —
    # each entry is human-readable so the CLARIFY message can name it
    unavailable: List[str] = field(default_factory=list)
    # planner notes explaining WHY it chose this shape — surfaced by the
    # explainer as the evidence trace
    notes: List[str] = field(default_factory=list)
    # the original question, retained for the evidence trace
    question: str = ""
    # the dataset table this plan targets
    table: str = ""

    def is_answerable(self) -> bool:
        return (self.intent_kind not in (IntentKind.UNSUPPORTED,
                                          IntentKind.AMBIGUOUS)
                and not self.unavailable)

    def as_trace(self) -> dict:
        """A compact, JSON-friendly trace for the explainer."""
        return {
            "intent_kind": self.intent_kind,
            "table": self.table,
            "measures": [
                {"kpi_id": m.kpi_id, "formula": m.formula,
                 "aggregation": m.aggregation, "unit": m.unit}
                for m in self.measures
            ],
            "dims": [
                {"column": d.column, "is_time": d.is_time,
                 "time_unit": d.time_unit}
                for d in self.dims
            ],
            "filters": [
                {"kind": f.kind, "column": f.column, "value": f.value,
                 "lo": f.lo, "hi": f.hi, "kpi_id": f.kpi_id,
                 "threshold": f.threshold}
                for f in self.filters
            ],
            "grain": (None if self.grain is None else
                      {"kind": self.grain.kind,
                       "time_unit": self.grain.time_unit,
                       "time_column": self.grain.time_column}),
            "comparison": (None if self.comparison is None else
                           {"time_column": self.comparison.time_column,
                            "base": self.comparison.base_period,
                            "target": self.comparison.target_period,
                            "mode": self.comparison.mode}),
            "contribution": (None if self.contribution is None else
                             {"time_column": self.contribution.time_column,
                              "base": self.contribution.base_period,
                              "target": self.contribution.target_period,
                              "dim_column": self.contribution.dim_column,
                              "direction": self.contribution.direction}),
            "top_n": self.top_n,
            "share_of_total": self.share_of_total,
            "order_by": self.order_by,
            "unavailable": list(self.unavailable),
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Semantic validation types
# ---------------------------------------------------------------------------

@dataclass
class SemanticIssue:
    kind: str                # "missing_kpi" | "missing_column" | "bad_grain" |
                             # "bad_aggregation" | "bad_comparison" | "unbindable"
    message: str
    severity: str = "error"  # "error" | "warning"


@dataclass
class ValidationReport:
    ok: bool
    issues: List[SemanticIssue] = field(default_factory=list)
    fidelity: float = 1.0    # 0..1, how faithfully the plan can be executed
