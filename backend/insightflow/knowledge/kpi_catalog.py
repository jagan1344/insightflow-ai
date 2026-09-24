"""Dataset-derived KPI catalog.

The catalog is **built per active dataset**. For the demo star schema it
is seeded with the seven KPIs from `kpi.py`; for uploaded datasets it is
derived from column roles + name hints + sample content so that any KPI
that is *actually computable* from the columns present is available,
without hardcoded per-dataset rules.

Each catalog entry (`KPIDefinition`) carries the canonical formula, the
aggregation kind, the required columns and a set of aliases the planner
matches against user text. When the SQL compiler emits SQL for a KPI, it
always uses the catalog's `formula` — the SQL text is therefore always
the KPI's canonical form, and `plan_fidelity` can check that.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .dataset_registry import ActiveDataset, ColumnInfo
from .kpi import KPIS as _DEMO_KPIS


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class KPIDefinition:
    kpi_id: str                     # stable key, e.g. "total_revenue"
    display_name: str
    aggregation: str                # sum | count | count_distinct | avg | ratio | derived
    formula: str                    # SQL expression, using DOUBLE-QUOTED physical column names
    required_columns: List[str] = field(default_factory=list)
    unit: str = ""                  # currency | count | ratio | percent | ""
    higher_is_better: bool = True
    non_negative: bool = True
    ratio_0_1: bool = False
    aliases: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class KPICatalog:
    dataset_id: str
    table: str
    kpis: Dict[str, KPIDefinition] = field(default_factory=dict)
    # measures / dims / dates carried through for the planner's convenience
    measures: List[str] = field(default_factory=list)
    dimensions: List[str] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)
    id_columns: List[str] = field(default_factory=list)

    def get(self, kpi_id: str) -> Optional[KPIDefinition]:
        return self.kpis.get(kpi_id)

    def all_ids(self) -> List[str]:
        return list(self.kpis.keys())

    def match_alias(self, text: str) -> Optional[KPIDefinition]:
        """Return the KPI whose LONGEST alias matches the given lowercased text.

        This is a substring match, not a regex — the planner already
        tokenises the question. Longest-match wins so 'average order
        value' beats 'value'.
        """
        t = " " + text.lower() + " "
        best: Tuple[int, Optional[KPIDefinition]] = (-1, None)
        for k in self.kpis.values():
            for alias in k.aliases:
                a = alias.lower()
                if len(a) <= best[0]:
                    continue
                if f" {a} " in t or f" {a}" == t[-(len(a)+1):] \
                        or f"{a} " == t[:len(a)+1]:
                    best = (len(a), k)
        return best[1]


# ---------------------------------------------------------------------------
# Alias vocabulary — used for BOTH demo and derived catalogs. This is
# LANGUAGE knowledge (what words users say for which measure), NOT dataset
# knowledge. Adding an alias here does not add a KPI; a KPI only exists
# if the dataset provides its required_columns.
# ---------------------------------------------------------------------------

_MEASURE_ALIASES: Dict[str, List[str]] = {
    "revenue":  ["revenue", "sales", "total sales", "gross sales", "turnover",
                 "gross revenue", "total revenue", "amount", "gross"],
    "profit":   ["profit", "net profit", "earnings"],
    "cost":     ["cost", "cogs", "expense", "expenses", "spend"],
    "discount": ["discount", "discounts", "markdown"],
    "quantity": ["quantity", "units", "units sold", "volume", "qty",
                 "items sold"],
    "orders":   ["orders", "order count", "number of orders",
                 "transactions", "transaction count"],
    "margin":   ["margin", "gross margin", "profit margin", "profitability",
                 "margins"],
    "aov":      ["average order value", "avg order value", "aov",
                 "average order size"],
    "discount_rate": ["discount rate", "discounting"],
    "profit_per_order": ["profit per order", "profit/order"],
    "avg_quantity_per_order": ["units per order", "quantity per order",
                                "average units per order"],
    "customer_count":  ["customer count", "number of customers",
                        "unique customers", "distinct customers"],
    "product_count":   ["product count", "distinct products",
                        "number of products", "unique products"],
    "row_count":       ["row count", "number of rows", "records",
                        "number of records"],
}


# ---------------------------------------------------------------------------
# Column hint tables — reused from the dataset_registry vocabulary
# ---------------------------------------------------------------------------

_REV_TOKS   = ("revenue", "sales", "amount", "turnover", "gross")
_PROFIT_TOKS= ("profit",)
_COST_TOKS  = ("cost", "cogs", "expense")
_DISC_TOKS  = ("discount",)
_QTY_TOKS   = ("quantity", "qty", "units")


def _find_column_by_tokens(ds: ActiveDataset, tokens: Tuple[str, ...],
                            role: Optional[str] = None) -> Optional[str]:
    """First column whose name contains one of the tokens; role-filtered
    when `role` is provided."""
    for name, info in ds.columns.items():
        if role is not None and info.role != role:
            continue
        lname = name.lower().replace(" ", "_").replace("-", "_")
        for tok in tokens:
            if tok in lname:
                return name
    return None


def _quote(col: str) -> str:
    return f'"{col}"'


# ---------------------------------------------------------------------------
# Catalog construction
# ---------------------------------------------------------------------------

def _seed_from_demo(ds: ActiveDataset) -> Dict[str, KPIDefinition]:
    """The demo star schema seed. Keeps the historical KPI IDs / formulas
    so all pre-existing tests keep passing."""
    out: Dict[str, KPIDefinition] = {}

    # revenue
    if "revenue" in ds.columns:
        out["total_revenue"] = KPIDefinition(
            kpi_id="total_revenue", display_name="Total Revenue",
            aggregation="sum", formula="SUM(revenue)",
            required_columns=["revenue"], unit="currency",
            aliases=_MEASURE_ALIASES["revenue"] + ["total_revenue"],
            description="Total gross revenue.",
        )
    if True:
        out["order_count"] = KPIDefinition(
            kpi_id="order_count", display_name="Order Count",
            aggregation="count", formula="COUNT(*)",
            required_columns=[], unit="count",
            aliases=_MEASURE_ALIASES["orders"] + ["order_count"],
        )
    if "quantity" in ds.columns:
        out["units_sold"] = KPIDefinition(
            kpi_id="units_sold", display_name="Units Sold",
            aggregation="sum", formula="SUM(quantity)",
            required_columns=["quantity"], unit="count",
            aliases=_MEASURE_ALIASES["quantity"] + ["units_sold"],
        )
    if "revenue" in ds.columns:
        out["avg_order_value"] = KPIDefinition(
            kpi_id="avg_order_value", display_name="Average Order Value",
            aggregation="ratio", formula="SUM(revenue)*1.0/COUNT(*)",
            required_columns=["revenue"], unit="currency",
            aliases=_MEASURE_ALIASES["aov"] + ["avg_order_value"],
        )
    if "revenue" in ds.columns and "cost" in ds.columns:
        out["gross_margin"] = KPIDefinition(
            kpi_id="gross_margin", display_name="Gross Margin",
            aggregation="ratio",
            formula="SUM(revenue-cost)*1.0/SUM(revenue)",
            required_columns=["revenue", "cost"], unit="ratio",
            ratio_0_1=True,
            aliases=_MEASURE_ALIASES["margin"] + ["gross_margin"],
        )
        out["profit"] = KPIDefinition(
            kpi_id="profit", display_name="Profit",
            aggregation="derived", formula="SUM(revenue-cost)",
            required_columns=["revenue", "cost"], unit="currency",
            non_negative=False,
            aliases=_MEASURE_ALIASES["profit"] + ["profit"],
        )
    if "discount" in ds.columns and "revenue" in ds.columns:
        out["discount_rate"] = KPIDefinition(
            kpi_id="discount_rate", display_name="Discount Rate",
            aggregation="ratio",
            formula="SUM(discount)*1.0/(SUM(revenue)+SUM(discount))",
            required_columns=["discount", "revenue"], unit="ratio",
            higher_is_better=False, ratio_0_1=True,
            aliases=_MEASURE_ALIASES["discount_rate"] + ["discounts",
                                                          "discount"],
        )
    return out


def _derive_from_uploaded(ds: ActiveDataset) -> Dict[str, KPIDefinition]:
    """For an uploaded (single-table) dataset, derive every KPI that the
    columns actually support. Nothing else."""
    out: Dict[str, KPIDefinition] = {}

    rev  = _find_column_by_tokens(ds, _REV_TOKS,    role="measure")
    prof = _find_column_by_tokens(ds, _PROFIT_TOKS, role="measure")
    cost = _find_column_by_tokens(ds, _COST_TOKS,   role="measure")
    disc = _find_column_by_tokens(ds, _DISC_TOKS,   role="measure")
    qty  = _find_column_by_tokens(ds, _QTY_TOKS,    role="measure")

    # Row count is always available.
    out["row_count"] = KPIDefinition(
        kpi_id="row_count", display_name="Row Count",
        aggregation="count", formula="COUNT(*)",
        required_columns=[], unit="count",
        aliases=_MEASURE_ALIASES["row_count"] + ["row_count",
                                                  "record count",
                                                  "records"],
    )
    # Order count is the same expression when the dataset is order-shaped;
    # we still expose it under the "orders" aliases so users can ask
    # naturally. Which one wins is decided by longest-alias-match in the
    # planner; if the dataset has neither an "order_id" nor an "orders"
    # column, treat row_count as the answer to "how many orders" too.
    out["order_count"] = KPIDefinition(
        kpi_id="order_count", display_name="Order Count",
        aggregation="count", formula="COUNT(*)",
        required_columns=[], unit="count",
        aliases=_MEASURE_ALIASES["orders"] + ["order_count"],
    )

    # Revenue-shaped SUMs — one per numeric measure that "looks like" a
    # revenue-ish quantity.
    if rev:
        out["total_revenue"] = KPIDefinition(
            kpi_id="total_revenue",
            display_name=f"Total {rev.title()}",
            aggregation="sum", formula=f"SUM({_quote(rev)})",
            required_columns=[rev], unit="currency",
            aliases=_MEASURE_ALIASES["revenue"] + ["total_revenue", rev],
            description=f"Sum of the '{rev}' column.",
        )
        out["avg_order_value"] = KPIDefinition(
            kpi_id="avg_order_value", display_name="Average Order Value",
            aggregation="ratio",
            formula=f"SUM({_quote(rev)})*1.0/COUNT(*)",
            required_columns=[rev], unit="currency",
            aliases=_MEASURE_ALIASES["aov"] + ["avg_order_value"],
            description=f"Average '{rev}' per row.",
        )
    if qty:
        out["units_sold"] = KPIDefinition(
            kpi_id="units_sold",
            display_name=f"Total {qty.title()}",
            aggregation="sum", formula=f"SUM({_quote(qty)})",
            required_columns=[qty], unit="count",
            aliases=_MEASURE_ALIASES["quantity"] + ["units_sold", qty],
        )
    if disc:
        out["total_discount"] = KPIDefinition(
            kpi_id="total_discount", display_name=f"Total {disc.title()}",
            aggregation="sum", formula=f"SUM({_quote(disc)})",
            required_columns=[disc], unit="currency",
            aliases=[disc] + _MEASURE_ALIASES["discount"],
        )
        out["avg_discount"] = KPIDefinition(
            kpi_id="avg_discount", display_name=f"Average {disc.title()}",
            aggregation="avg", formula=f"AVG({_quote(disc)})",
            required_columns=[disc], unit="currency",
            aliases=[f"average {disc}", "avg discount",
                     "average discount"],
        )
    if cost:
        out["total_cost"] = KPIDefinition(
            kpi_id="total_cost", display_name=f"Total {cost.title()}",
            aggregation="sum", formula=f"SUM({_quote(cost)})",
            required_columns=[cost], unit="currency",
            aliases=[cost] + _MEASURE_ALIASES["cost"],
        )

    # Profit — prefer explicit column, else derive from rev-cost.
    if prof:
        out["profit"] = KPIDefinition(
            kpi_id="profit", display_name="Total Profit",
            aggregation="sum", formula=f"SUM({_quote(prof)})",
            required_columns=[prof], unit="currency",
            non_negative=False,
            aliases=_MEASURE_ALIASES["profit"] + ["total_profit", prof],
        )
    elif rev and cost:
        out["profit"] = KPIDefinition(
            kpi_id="profit", display_name="Total Profit",
            aggregation="derived",
            formula=f"SUM({_quote(rev)} - {_quote(cost)})",
            required_columns=[rev, cost], unit="currency",
            non_negative=False,
            aliases=_MEASURE_ALIASES["profit"] + ["total_profit"],
        )

    # Gross margin
    if prof and rev:
        out["gross_margin"] = KPIDefinition(
            kpi_id="gross_margin", display_name="Gross Margin",
            aggregation="ratio",
            formula=f"SUM({_quote(prof)})*1.0/SUM({_quote(rev)})",
            required_columns=[prof, rev], unit="ratio", ratio_0_1=True,
            aliases=_MEASURE_ALIASES["margin"] + ["gross_margin"],
        )
    elif rev and cost:
        out["gross_margin"] = KPIDefinition(
            kpi_id="gross_margin", display_name="Gross Margin",
            aggregation="ratio",
            formula=(f"SUM({_quote(rev)} - {_quote(cost)}) * 1.0 / "
                     f"SUM({_quote(rev)})"),
            required_columns=[rev, cost], unit="ratio", ratio_0_1=True,
            aliases=_MEASURE_ALIASES["margin"] + ["gross_margin"],
        )

    # Discount rate
    if disc and rev:
        out["discount_rate"] = KPIDefinition(
            kpi_id="discount_rate", display_name="Discount Rate",
            aggregation="ratio",
            formula=(f"SUM({_quote(disc)}) * 1.0 / "
                     f"(SUM({_quote(rev)}) + SUM({_quote(disc)}))"),
            required_columns=[disc, rev], unit="ratio",
            higher_is_better=False, ratio_0_1=True,
            aliases=_MEASURE_ALIASES["discount_rate"] + ["discount rate"],
        )

    # Distinct-count KPIs — one per id-column the dataset advertises.
    for name, info in ds.columns.items():
        if info.role != "id":
            continue
        lname = name.lower()
        aliases: List[str] = []
        if "customer" in lname or "client" in lname:
            aliases = _MEASURE_ALIASES["customer_count"]
            kid = "customer_count"; disp = "Distinct Customers"
        elif "product" in lname or "sku" in lname or "item" in lname:
            aliases = _MEASURE_ALIASES["product_count"]
            kid = "product_count"; disp = "Distinct Products"
        elif "order" in lname or "transaction" in lname:
            aliases = ["distinct orders", "unique orders"]
            kid = "distinct_orders"; disp = "Distinct Orders"
        else:
            kid = f"distinct_{name.lower()}"
            disp = f"Distinct {name.title()}"
            aliases = [f"distinct {name.lower()}",
                       f"unique {name.lower()}",
                       f"number of {name.lower()}"]
        if kid not in out:
            out[kid] = KPIDefinition(
                kpi_id=kid, display_name=disp,
                aggregation="count_distinct",
                formula=f"COUNT(DISTINCT {_quote(name)})",
                required_columns=[name], unit="count",
                aliases=aliases,
            )

    # Generic AVG(col) for every numeric measure that isn't already the
    # subject of a specific KPI — enables "average X" for any column.
    already_avged: set = set()
    for k in out.values():
        if k.aggregation in ("avg", "ratio"):
            already_avged.update(k.required_columns)
    for name, info in ds.columns.items():
        if info.role != "measure" or name in already_avged:
            continue
        kid = f"avg_{name.lower()}"
        if kid in out:
            continue
        out[kid] = KPIDefinition(
            kpi_id=kid, display_name=f"Average {name.title()}",
            aggregation="avg", formula=f"AVG({_quote(name)})",
            required_columns=[name], unit=info.sql_type.lower(),
            aliases=[f"average {name.lower()}", f"avg {name.lower()}",
                     f"mean {name.lower()}"],
        )
        # And a plain SUM alias for the column too — safe fallback so
        # "what's the total <col>" works.
        sid = f"sum_{name.lower()}"
        if sid not in out:
            out[sid] = KPIDefinition(
                kpi_id=sid, display_name=f"Total {name.title()}",
                aggregation="sum", formula=f"SUM({_quote(name)})",
                required_columns=[name], unit="",
                aliases=[f"total {name.lower()}", name.lower(),
                         f"sum of {name.lower()}"],
            )

    return out


def build_catalog(ds: ActiveDataset) -> KPICatalog:
    """Build the KPI catalog for the given dataset."""
    if ds.kind == "demo":
        kpis = _seed_from_demo(ds)
    else:
        kpis = _derive_from_uploaded(ds)

    cat = KPICatalog(
        dataset_id=ds.id,
        table=ds.table,
        kpis=kpis,
        measures=list(ds.measures),
        dimensions=list(ds.dimensions),
        dates=list(ds.dates),
        id_columns=[n for n, c in ds.columns.items() if c.role == "id"],
    )
    return cat
