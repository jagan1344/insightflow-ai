"""KPI / business definitions — the semantic layer."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class KPI:
    key: str
    name: str
    sql_expr: str
    description: str
    unit: str = ""
    higher_is_better: bool = True
    non_negative: bool = True
    ratio_0_1: bool = False


KPIS: Dict[str, KPI] = {
    "total_revenue": KPI(
        key="total_revenue",
        name="Total Revenue",
        sql_expr="SUM(revenue)",
        description="Total gross revenue across matching orders.",
        unit="currency",
    ),
    "order_count": KPI(
        key="order_count",
        name="Order Count",
        sql_expr="COUNT(*)",
        description="Number of orders matching the filter.",
        unit="count",
    ),
    "units_sold": KPI(
        key="units_sold",
        name="Units Sold",
        sql_expr="SUM(quantity)",
        description="Total quantity of items sold.",
        unit="count",
    ),
    "avg_order_value": KPI(
        key="avg_order_value",
        name="Average Order Value",
        sql_expr="SUM(revenue)*1.0/COUNT(*)",
        description="Average revenue per order.",
        unit="currency",
    ),
    "gross_margin": KPI(
        key="gross_margin",
        name="Gross Margin",
        sql_expr="SUM(revenue-cost)*1.0/SUM(revenue)",
        description="(Revenue - Cost) / Revenue, as a ratio between 0 and 1.",
        unit="ratio",
        ratio_0_1=True,
    ),
    # Profit is a signed currency KPI (can be negative — e.g. loss-making
    # sub-categories). Non-negative rule is disabled so `HAVING profit < 0`
    # queries don't trip the KPI validator.
    "profit": KPI(
        key="profit",
        name="Profit",
        sql_expr="SUM(revenue-cost)",
        description="Total profit (revenue - cost). Can be negative.",
        unit="currency",
        non_negative=False,
    ),
    "discount_rate": KPI(
        key="discount_rate",
        name="Discount Rate",
        sql_expr="SUM(discount)*1.0/(SUM(revenue)+SUM(discount))",
        description="Share of gross value given away as discount.",
        unit="ratio",
        higher_is_better=False,
        ratio_0_1=True,
    ),
}


# Longest match wins in resolve_kpi
SYNONYMS: Dict[str, str] = {
    # revenue
    "total revenue": "total_revenue",
    "revenue": "total_revenue",
    "sales": "total_revenue",
    "turnover": "total_revenue",
    # orders
    "order count": "order_count",
    "orders": "order_count",
    "number of orders": "order_count",
    # units
    "units sold": "units_sold",
    "units": "units_sold",
    "quantity": "units_sold",
    "volume": "units_sold",
    # aov
    "average order value": "avg_order_value",
    "avg order value": "avg_order_value",
    "aov": "avg_order_value",
    # margin — "profit margin" resolves to gross_margin, plain "profit" to profit
    "gross margin": "gross_margin",
    "profit margin": "gross_margin",
    "profit margins": "gross_margin",
    "margins": "gross_margin",
    "margin": "gross_margin",
    "profitability": "gross_margin",
    # profit (signed) — cash flow / loss-making phrases
    "profit": "profit",
    "losing money": "profit",
    "draining cash": "profit",
    "loss making": "profit",
    "loss-making": "profit",
    "unprofitable": "profit",
    # discount
    "discount rate": "discount_rate",
    "discounting": "discount_rate",
    "discounts": "discount_rate",
    "discount": "discount_rate",
}


def resolve_kpi(text: str) -> Optional[KPI]:
    """Return the KPI whose longest synonym matches the text (case-insensitive)."""
    if not text:
        return None
    t = text.lower()
    # sort synonyms by length desc so "average order value" beats "value"
    for syn in sorted(SYNONYMS.keys(), key=len, reverse=True):
        if syn in t:
            return KPIS[SYNONYMS[syn]]
    return None
