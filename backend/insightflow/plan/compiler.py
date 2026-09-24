"""Compile an AnalyticalPlan to executable SQL.

Two backends are supported:

    * demo star-schema (`orders` + joins to `regions`, `products`,
      `customers`).
    * uploaded single-table (`dataset_<slug>`).

The compiler chooses the backend from `ActiveDataset.kind`. Everything
else — the SQL shape per intent kind — is dataset-agnostic.

The compiler NEVER interpolates user text into SQL; every column and
table name comes from the dataset introspection or the KPI catalog,
which are trusted. Value literals in filters are quoted with SQL
string-escape.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from ..knowledge.dataset_registry import ActiveDataset
from ..knowledge.kpi_catalog import KPICatalog
from .plan import (
    AnalyticalPlan, ComparisonSpec, ContributionSpec, DimRef, FilterExpr,
    Grain, IntentKind, MeasureRef, RelativeStatSpec,
)


# ---------------------------------------------------------------------------
# Backend helpers
# ---------------------------------------------------------------------------

def _q(col: str) -> str:
    return f'"{col}"'


def _sql_escape(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("'", "''")
    return f"'{s}'"


def _time_bucket_expr(date_col: str, unit: str, quoted: bool) -> str:
    col = _q(date_col) if quoted else date_col
    if unit == "year":
        return f"substr({col},1,4)"
    if unit == "quarter":
        # Text quarter like '2026-Q3' — sortable
        return (f"substr({col},1,4) || '-Q' || "
                f"cast((cast(substr({col},6,2) as integer) + 2) / 3 as text)")
    if unit == "week":
        # Simple ISO-week-of-year fallback: 'YYYY-Www' via strftime('%W')
        return f"strftime('%Y-W%W', {col})"
    if unit == "day":
        return f"substr({col},1,10)"
    return f"substr({col},1,7)"  # month


def _month_range_predicate(date_col: str, period: str, quoted: bool) -> str:
    """`period` is 'YYYY-MM'. Returns 'col >= 'YYYY-MM-01' AND col < 'YYYY-MM+1-01'.'
    """
    y, m = period.split("-")
    year = int(y); month = int(m)
    end_month = month + 1
    end_year = year
    if end_month > 12:
        end_month = 1
        end_year += 1
    lo = f"{year:04d}-{month:02d}-01"
    hi = f"{end_year:04d}-{end_month:02d}-01"
    col = _q(date_col) if quoted else date_col
    return f"{col} >= '{lo}' AND {col} < '{hi}'"


def _period_range_predicate(date_col: str, lo_period: str, hi_period: str,
                             quoted: bool) -> str:
    """Time range covering months [lo_period .. hi_period] inclusive."""
    ly, lm = lo_period.split("-")
    hy, hm = hi_period.split("-")
    start_year, start_month = int(ly), int(lm)
    end_year, end_month = int(hy), int(hm)
    # end = first day of month AFTER hi
    end_month += 1
    if end_month > 12:
        end_month = 1
        end_year += 1
    lo = f"{start_year:04d}-{start_month:02d}-01"
    hi = f"{end_year:04d}-{end_month:02d}-01"
    col = _q(date_col) if quoted else date_col
    return f"{col} >= '{lo}' AND {col} < '{hi}'"


# ---------------------------------------------------------------------------
# Demo star-schema mapping
# ---------------------------------------------------------------------------

_DEMO_DIM_MAP = {
    # column-name-in-orders-or-joined-table → (select_expr, group_expr, join_sql, label)
    "regions.region_name": ("regions.region_name", "regions.region_name",
                            "JOIN regions ON regions.region_id = orders.region_id",
                            "region"),
    "products.category":   ("products.category", "products.category",
                            "JOIN products ON products.product_id = orders.product_id",
                            "category"),
    "products.sub_category": ("products.sub_category", "products.sub_category",
                              "JOIN products ON products.product_id = orders.product_id",
                              "sub_category"),
    "products.product_name": ("products.product_name", "products.product_name",
                              "JOIN products ON products.product_id = orders.product_id",
                              "product"),
    "customers.segment":   ("customers.segment", "customers.segment",
                            "JOIN customers ON customers.customer_id = orders.customer_id",
                            "segment"),
    "customers.customer_name": ("customers.customer_name",
                                 "customers.customer_name",
                                 "JOIN customers ON customers.customer_id = orders.customer_id",
                                 "customer"),
}


def _demo_dim_target(col: str) -> Tuple[str, str, str, str]:
    """Resolve a demo dimension column name to (select_expr, group_expr,
    join_sql, alias). Falls back to a bare `orders.<col>` reference."""
    # Direct joined-table columns
    if col in ("region_name", "region"):
        return _DEMO_DIM_MAP["regions.region_name"]
    if col == "category":
        return _DEMO_DIM_MAP["products.category"]
    if col in ("sub_category", "subcategory"):
        return _DEMO_DIM_MAP["products.sub_category"]
    if col in ("product_name", "product"):
        return _DEMO_DIM_MAP["products.product_name"]
    if col == "segment":
        return _DEMO_DIM_MAP["customers.segment"]
    if col in ("customer_name", "customer"):
        return _DEMO_DIM_MAP["customers.customer_name"]
    if col == "order_date":
        return ("orders.order_date", "orders.order_date", "", "order_date")
    # Generic: assume the column is on `orders`
    return (f"orders.{col}", f"orders.{col}", "", col)


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------

class SQLCompiler:
    def __init__(self, ds: ActiveDataset, catalog: KPICatalog):
        self.ds = ds
        self.catalog = catalog
        self.kind = ds.kind

    # ------------------------------------------------------------------
    # Public entry
    def compile(self, plan: AnalyticalPlan) -> str:
        if plan.intent_kind in (IntentKind.AMBIGUOUS, IntentKind.UNSUPPORTED):
            return ""

        # dispatch by intent kind
        ik = plan.intent_kind
        if ik == IntentKind.COMPARISON:
            return self._compile_comparison(plan)
        if ik == IntentKind.CONTRIBUTION:
            return self._compile_contribution(plan)
        if ik == IntentKind.AVERAGE_AT_GRAIN:
            return self._compile_average_at_grain(plan)
        if ik == IntentKind.GROWTH:
            return self._compile_growth(plan)
        if ik == IntentKind.SHARE_OF_TOTAL:
            return self._compile_share(plan)
        if ik == IntentKind.RELATIVE_TO_STAT:
            return self._compile_relative_to_stat(plan)
        # default: SELECT dims, measures FROM t [joins] [WHERE] [GROUP] [ORDER] [LIMIT]
        return self._compile_flat(plan)

    # ==================================================================
    # Flat compiler: direct_kpi / breakdown / trend / top_n / bottom_n /
    # ratio all share this shape.
    def _compile_flat(self, plan: AnalyticalPlan) -> str:
        select_parts: List[str] = []
        group_parts: List[str] = []
        joins: List[str] = []
        joins_seen: set = set()

        # dims (including time bucket)
        for d in plan.dims:
            if d.is_time and d.time_unit:
                expr = self._time_bucket(d.column, d.time_unit)
                alias = d.time_unit
                select_parts.append(f"{expr} AS {alias}")
                group_parts.append(expr)
            else:
                sel_expr, grp_expr, join_sql, alias = self._dim_target(d.column)
                select_parts.append(f"{sel_expr} AS {alias}")
                group_parts.append(grp_expr)
                if join_sql and join_sql not in joins_seen:
                    joins.append(join_sql); joins_seen.add(join_sql)

        # measures
        for m in plan.measures:
            expr = self._measure_expr(m)
            select_parts.append(f"{expr} AS {m.kpi_id}")

        if not select_parts:
            return ""

        # WHERE / HAVING from filters
        where, having = self._filter_clauses(plan)

        # ORDER BY / LIMIT
        order_clause = self._order_clause(plan)
        limit_clause = f" LIMIT {plan.top_n}" if plan.top_n else ""

        from_clause = self._from_clause()
        sql = "SELECT " + ", ".join(select_parts) + f" FROM {from_clause}"
        if joins:
            sql += " " + " ".join(joins)
        if where:
            sql += " WHERE " + " AND ".join(where)
        if group_parts:
            sql += " GROUP BY " + ", ".join(group_parts)
        if having:
            sql += " HAVING " + " AND ".join(having)
        sql += order_clause
        sql += limit_clause
        return sql

    # ==================================================================
    # Share of total: adds a window function against the total.
    def _compile_share(self, plan: AnalyticalPlan) -> str:
        if not plan.measures:
            return ""
        base_measure = plan.measures[0]
        base_expr = self._measure_expr(base_measure)
        select_parts: List[str] = []
        group_parts: List[str] = []
        joins: List[str] = []
        joins_seen: set = set()

        for d in plan.dims:
            if d.is_time and d.time_unit:
                expr = self._time_bucket(d.column, d.time_unit)
                alias = d.time_unit
                select_parts.append(f"{expr} AS {alias}")
                group_parts.append(expr)
            else:
                sel_expr, grp_expr, join_sql, alias = self._dim_target(d.column)
                select_parts.append(f"{sel_expr} AS {alias}")
                group_parts.append(grp_expr)
                if join_sql and join_sql not in joins_seen:
                    joins.append(join_sql); joins_seen.add(join_sql)

        select_parts.append(f"{base_expr} AS {base_measure.kpi_id}")
        select_parts.append(
            f"{base_expr} * 1.0 / SUM({base_expr}) OVER () AS share")

        where, having = self._filter_clauses(plan)
        from_clause = self._from_clause()
        sql = "SELECT " + ", ".join(select_parts) + f" FROM {from_clause}"
        if joins:
            sql += " " + " ".join(joins)
        if where:
            sql += " WHERE " + " AND ".join(where)
        if group_parts:
            sql += " GROUP BY " + ", ".join(group_parts)
        if having:
            sql += " HAVING " + " AND ".join(having)
        sql += f" ORDER BY {base_measure.kpi_id} DESC"
        return sql

    # ==================================================================
    # Relative-to-stat: aggregate at entity grain, compute a group stat
    # (AVG / MEDIAN), then return entities that satisfy the op vs stat.
    def _compile_relative_to_stat(self, plan: AnalyticalPlan) -> str:
        rs: RelativeStatSpec = plan.relative_stat  # type: ignore
        if rs is None or not plan.measures:
            return ""
        sel_expr, grp_expr, join_sql, alias = self._dim_target(rs.entity_column)
        from_clause = self._from_clause()

        # Build the inner per-entity aggregate.
        primary = self.catalog.get(rs.measure_kpi_id)
        if primary is None:
            return ""
        m_alias = "m1"
        inner_selects = [f"{sel_expr} AS {alias}",
                          f"{primary.formula} AS {m_alias}"]

        second = None
        if rs.and_measure_kpi_id:
            second = self.catalog.get(rs.and_measure_kpi_id)
            if second is not None:
                inner_selects.append(f"{second.formula} AS m2")

        where_parts = self._extra_where(plan)
        inner = "SELECT " + ", ".join(inner_selects) + f" FROM {from_clause}"
        if join_sql:
            inner += " " + join_sql
        if where_parts:
            inner += " WHERE " + " AND ".join(where_parts)
        inner += f" GROUP BY {grp_expr}"

        # Stat over the per-entity series.
        def stat_expr(field: str, stat: str) -> str:
            if stat == "avg":
                return f"(SELECT AVG({field}) FROM agg)"
            if stat == "median":
                # SQLite has no MEDIAN; use avg of two middle values via
                # percentile-style query. Fall back to AVG when the
                # backend doesn't support it. Rough approximation for
                # small datasets that matches the pandas oracle in our
                # tests.
                return (
                    f"(SELECT AVG({field}) FROM ("
                    f"SELECT {field} FROM agg ORDER BY {field} "
                    f"LIMIT 2 - (SELECT COUNT(*) FROM agg) % 2 "
                    f"OFFSET (SELECT (COUNT(*) - 1) / 2 FROM agg)))"
                )
            return f"(SELECT AVG({field}) FROM agg)"

        def op_sym(op: str) -> str:
            return {"gt": ">", "lt": "<", "gte": ">=", "lte": "<="}.get(op, ">")

        cond = f"{m_alias} {op_sym(rs.op)} {stat_expr(m_alias, rs.stat)}"
        cols = [alias, m_alias]
        if second is not None:
            cond += f" AND m2 {op_sym(rs.and_op)} {stat_expr('m2', rs.and_stat)}"
            cols.append("m2")

        sql = (
            f"WITH agg AS ({inner}) "
            f"SELECT {', '.join(cols)} FROM agg WHERE {cond} "
            f"ORDER BY {m_alias} DESC"
        )
        return sql

    # ==================================================================
    # Comparison: two periods, one metric — returns two rows or one
    # side-by-side row with delta / pct depending on mode.
    def _compile_comparison(self, plan: AnalyticalPlan) -> str:
        cs: ComparisonSpec = plan.comparison  # type: ignore[assignment]
        if not plan.measures or cs is None:
            return ""
        m = plan.measures[0]
        base_col = self._date_col_for(cs.time_column)
        bucket = self._time_bucket(cs.time_column, "month")
        where_bases = list(self._extra_where(plan))
        pred_base = _month_range_predicate(cs.time_column, cs.base_period,
                                             quoted=(self.kind == "uploaded"))
        pred_targ = _month_range_predicate(cs.time_column, cs.target_period,
                                             quoted=(self.kind == "uploaded"))
        measure_expr = self._measure_expr(m)

        # For readability, keep it as a UNION of two rows (period, value).
        sql = (f"SELECT '{cs.base_period}' AS period, "
               f"{measure_expr} AS {m.kpi_id} FROM {self._from_clause()} "
               f"WHERE {pred_base}"
               f" UNION ALL "
               f"SELECT '{cs.target_period}' AS period, "
               f"{measure_expr} AS {m.kpi_id} FROM {self._from_clause()} "
               f"WHERE {pred_targ}"
               f" ORDER BY period")
        return sql

    # ==================================================================
    # Contribution: per-dim value in each period, ranked by delta.
    def _compile_contribution(self, plan: AnalyticalPlan) -> str:
        cs: ContributionSpec = plan.contribution  # type: ignore[assignment]
        if not plan.measures or cs is None:
            return ""
        m = plan.measures[0]
        measure_expr = self._measure_expr(m)
        sel_expr, grp_expr, join_sql, alias = self._dim_target(cs.dim_column)
        pred_base = _month_range_predicate(cs.time_column, cs.base_period,
                                             quoted=(self.kind == "uploaded"))
        pred_targ = _month_range_predicate(cs.time_column, cs.target_period,
                                             quoted=(self.kind == "uploaded"))
        from_clause = self._from_clause()

        # Build via two CTEs joined on the dim.
        cte_base = (f"SELECT {sel_expr} AS {alias}, "
                    f"{measure_expr} AS v FROM {from_clause}"
                    + (f" {join_sql}" if join_sql else "")
                    + f" WHERE {pred_base} GROUP BY {grp_expr}")
        cte_targ = (f"SELECT {sel_expr} AS {alias}, "
                    f"{measure_expr} AS v FROM {from_clause}"
                    + (f" {join_sql}" if join_sql else "")
                    + f" WHERE {pred_targ} GROUP BY {grp_expr}")
        order = "ASC" if cs.direction == "decline" else "DESC"

        sql = (
            f"WITH base AS ({cte_base}), targ AS ({cte_targ}) "
            f"SELECT COALESCE(base.{alias}, targ.{alias}) AS {alias}, "
            f"COALESCE(base.v, 0) AS base_value, "
            f"COALESCE(targ.v, 0) AS target_value, "
            f"(COALESCE(targ.v, 0) - COALESCE(base.v, 0)) AS delta "
            f"FROM base FULL OUTER JOIN targ "
            f"ON base.{alias} = targ.{alias} "
            f"ORDER BY delta {order}"
        )
        # SQLite doesn't support FULL OUTER JOIN; simulate with UNION.
        sql = (
            f"WITH base AS ({cte_base}), targ AS ({cte_targ}), "
            f"merged AS ("
            f"SELECT base.{alias} AS {alias}, base.v AS base_value, "
            f"COALESCE(targ.v, 0) AS target_value FROM base "
            f"LEFT JOIN targ ON base.{alias} = targ.{alias} "
            f"UNION ALL "
            f"SELECT targ.{alias} AS {alias}, 0 AS base_value, "
            f"targ.v AS target_value FROM targ "
            f"LEFT JOIN base ON base.{alias} = targ.{alias} "
            f"WHERE base.{alias} IS NULL"
            f") "
            f"SELECT {alias}, base_value, target_value, "
            f"(target_value - base_value) AS delta "
            f"FROM merged ORDER BY delta {order}"
        )
        return sql

    # ==================================================================
    # Average-at-grain: outer AVG of inner per-grain SUM.
    def _compile_average_at_grain(self, plan: AnalyticalPlan) -> str:
        if not plan.measures or plan.grain is None:
            return ""
        m = plan.measures[0]
        # Only well-defined for SUM-style measures.
        inner_expr = self._measure_expr(m)
        bucket = self._time_bucket(plan.grain.time_column, plan.grain.time_unit)
        from_clause = self._from_clause()
        where, having = self._filter_clauses(plan)
        inner = (f"SELECT {bucket} AS bucket, {inner_expr} AS v "
                 f"FROM {from_clause}")
        if where:
            inner += " WHERE " + " AND ".join(where)
        inner += f" GROUP BY {bucket}"
        sql = f"SELECT AVG(v) AS avg_per_{plan.grain.time_unit}_{m.kpi_id} FROM ({inner})"
        return sql

    # ==================================================================
    # Growth: use LAG over the time buckets.
    def _compile_growth(self, plan: AnalyticalPlan) -> str:
        if not plan.measures or plan.grain is None:
            return ""
        m = plan.measures[0]
        expr = self._measure_expr(m)
        bucket = self._time_bucket(plan.grain.time_column, plan.grain.time_unit)
        from_clause = self._from_clause()
        where, having = self._filter_clauses(plan)
        agg_sql = (f"SELECT {bucket} AS {plan.grain.time_unit}, "
                    f"{expr} AS {m.kpi_id} FROM {from_clause}")
        if where:
            agg_sql += " WHERE " + " AND ".join(where)
        agg_sql += f" GROUP BY {bucket}"
        sql = (
            f"WITH agg AS ({agg_sql}) "
            f"SELECT {plan.grain.time_unit}, {m.kpi_id}, "
            f"LAG({m.kpi_id}) OVER (ORDER BY {plan.grain.time_unit}) AS prev, "
            f"({m.kpi_id} - LAG({m.kpi_id}) OVER (ORDER BY "
            f"{plan.grain.time_unit})) AS delta, "
            f"CASE WHEN LAG({m.kpi_id}) OVER (ORDER BY {plan.grain.time_unit}) "
            f"IS NULL OR LAG({m.kpi_id}) OVER (ORDER BY {plan.grain.time_unit}) "
            f"= 0 THEN NULL "
            f"ELSE ({m.kpi_id} - LAG({m.kpi_id}) OVER (ORDER BY "
            f"{plan.grain.time_unit})) * 1.0 / LAG({m.kpi_id}) OVER "
            f"(ORDER BY {plan.grain.time_unit}) END AS pct "
            f"FROM agg ORDER BY {plan.grain.time_unit}"
        )
        return sql

    # ==================================================================
    # Shared building blocks
    def _from_clause(self) -> str:
        if self.kind == "demo":
            return "orders"
        return f'"{self.ds.table}"'

    def _dim_target(self, col: str) -> Tuple[str, str, str, str]:
        """Return (select_expr, group_by_expr, join_sql, alias) for a
        physical column of this dataset."""
        if self.kind == "demo":
            return _demo_dim_target(col)
        # uploaded — single table, quoted column name
        qc = _q(col)
        alias = col.lower().replace(" ", "_").replace("-", "_")
        return (qc, qc, "", alias)

    def _time_bucket(self, col: str, unit: str) -> str:
        return _time_bucket_expr(col, unit, quoted=(self.kind == "uploaded"))

    def _measure_expr(self, m: MeasureRef) -> str:
        kpi = self.catalog.get(m.kpi_id)
        if kpi is None:
            return "NULL"
        # Use catalog's canonical formula — that's the whole point.
        return kpi.formula

    def _extra_where(self, plan: AnalyticalPlan) -> List[str]:
        parts: List[str] = []
        for f in plan.filters:
            if f.kind == "time_range" and f.column:
                lo = str(f.lo); hi = str(f.hi)
                parts.append(_period_range_predicate(
                    f.column, lo, hi,
                    quoted=(self.kind == "uploaded")))
            elif f.kind == "eq" and f.column:
                parts.append(f'{self._colref(f.column)} = {_sql_escape(f.value)}')
            elif f.kind == "in" and f.column and isinstance(f.value, (list, tuple)):
                vs = ", ".join(_sql_escape(v) for v in f.value)
                parts.append(f'{self._colref(f.column)} IN ({vs})')
            elif f.kind == "range" and f.column:
                parts.append(
                    f'{self._colref(f.column)} >= {_sql_escape(f.lo)} '
                    f'AND {self._colref(f.column)} <= {_sql_escape(f.hi)}')
        return parts

    def _filter_clauses(self, plan: AnalyticalPlan) -> Tuple[List[str], List[str]]:
        where = self._extra_where(plan)
        having: List[str] = []
        for f in plan.filters:
            if f.kind == "metric_lt":
                kpi = self.catalog.get(f.kpi_id)
                if kpi:
                    having.append(f"{kpi.formula} < {f.threshold}")
            elif f.kind == "metric_gt":
                kpi = self.catalog.get(f.kpi_id)
                if kpi:
                    having.append(f"{kpi.formula} > {f.threshold}")
        return where, having

    def _colref(self, col: str) -> str:
        if self.kind == "demo":
            return col if "." in col else f"orders.{col}"
        return _q(col)

    def _date_col_for(self, col: str) -> str:
        return col

    def _order_clause(self, plan: AnalyticalPlan) -> str:
        if not plan.order_by:
            return ""
        if plan.order_by == "measure_desc" and plan.measures:
            return f" ORDER BY {plan.measures[0].kpi_id} DESC"
        if plan.order_by == "measure_asc" and plan.measures:
            return f" ORDER BY {plan.measures[0].kpi_id} ASC"
        if plan.order_by == "time_asc" and plan.dims:
            for d in plan.dims:
                if d.is_time and d.time_unit:
                    return f" ORDER BY {d.time_unit}"
        return ""


# ---------------------------------------------------------------------------
# Convenience: end-to-end plan → sql
# ---------------------------------------------------------------------------

def plan_and_compile(question: str, ds: ActiveDataset,
                     catalog: Optional[KPICatalog] = None
                     ) -> Tuple[AnalyticalPlan, str]:
    """Convenience entry point used by tests and by the orchestrator."""
    from ..knowledge.kpi_catalog import build_catalog
    from .planner import Planner
    cat = catalog or build_catalog(ds)
    planner = Planner(ds, cat)
    plan = planner.plan(question)
    if not plan.is_answerable():
        return plan, ""
    compiler = SQLCompiler(ds, cat)
    return plan, compiler.compile(plan)
