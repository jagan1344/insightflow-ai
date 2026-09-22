"""Evidence + provenance chain."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..execution.executor import QueryResult
from ..knowledge.kpi import KPI


@dataclass
class Evidence:
    question: str
    sql: str
    kpi: Optional[KPI]
    filters: Dict[str, Any] = field(default_factory=dict)
    sample_rows: List[Dict[str, Any]] = field(default_factory=list)
    row_count: int = 0

    def as_chain(self) -> List[Dict[str, Any]]:
        chain: List[Dict[str, Any]] = [
            {"step": "question", "value": self.question},
            {"step": "sql", "value": self.sql},
        ]
        if self.kpi is not None:
            chain.append({
                "step": "kpi_definition",
                "value": {
                    "key": self.kpi.key,
                    "name": self.kpi.name,
                    "sql_expr": self.kpi.sql_expr,
                    "description": self.kpi.description,
                    "unit": self.kpi.unit,
                    "non_negative": self.kpi.non_negative,
                    "ratio_0_1": self.kpi.ratio_0_1,
                },
            })
        if self.filters:
            chain.append({"step": "filters", "value": self.filters})
        chain.append({"step": "row_count", "value": self.row_count})
        if self.sample_rows:
            chain.append({"step": "sample_rows", "value": self.sample_rows})
        return chain


def build_evidence(question: str, sql: str, kpi: Optional[KPI],
                   filters: Optional[Dict[str, Any]], result: QueryResult,
                   sample_n: int = 5) -> Evidence:
    sample = result.to_dicts()[:sample_n] if result.ok else []
    return Evidence(
        question=question,
        sql=sql,
        kpi=kpi,
        filters=dict(filters or {}),
        sample_rows=sample,
        row_count=result.n_rows if result.ok else 0,
    )
