"""Assemble the deterministic, inspectable semantic catalog the frozen pipeline uses for a dataset, from its
existing components (schema discovery, relational context, KPI catalogue, abbreviations, vocabulary rules).
Read-only: it adds no behaviour. usage: python semantic_catalog.py <db_path> <db@anchor> <out.json>"""
import json, os, re, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from insightflow.config import settings
from insightflow.execution.executor import reset_engine
from insightflow.knowledge.dataset_registry import register_relational, set_active, bootstrap, get_active_dataset
from insightflow.knowledge.schema_agent import refresh_schema
from insightflow.knowledge.kpi_catalog import build_catalog
from insightflow.knowledge.abbrev import ABBREV, canon_tokens
from insightflow.knowledge import vocabulary as V
from insightflow.plan.planner import _is_money_kpi, _FLAG_POLARITY

db, spec, out = sys.argv[1:4]
settings.database_url = f"sqlite:///{db}"; os.environ.pop("INSIGHTFLOW_METRICS_FILE", None)
reset_engine(); bootstrap(); i = register_relational(spec, spec.split("@")[1]); reset_engine(); refresh_schema(); set_active(i)
ds = get_active_dataset(); cat = build_catalog(ds); rel = ds.rel
MONEY = {"amt", "amount", "price", "fare", "cost", "fee", "revenue", "usd", "premium", "prem", "tip", "value"}
cols = {}
for c, info in ds.columns.items():
    toks = [t for t in re.split(r"[^a-z0-9]+", c.lower()) if t]
    src = rel.source(c) if rel else None
    sem = ("flag" if c in (ds.flag_columns or []) else "id" if info.role == "id" else "date" if info.role == "date"
           else "money" if info.role == "measure" and set(toks) & MONEY else "quantity" if info.role == "measure"
           else "category")
    cols[c] = dict(table=(src.table if src else ds.table), physical=(src.column if src else c), role=info.role,
                   sql_type=getattr(info, "sql_type", ""), semantic_type=sem, canonical_words=canon_tokens(c),
                   unit=next((t for t in toks if t in {"kwh", "km", "min", "mins", "hrs", "kg", "usd", "pct", "cnt", "m", "sq"}), None),
                   join=(None if src is None else dict(kind=src.kind, nullable=src.nullable,
                                                       path=[f"{s.edge.child_table}.{s.edge.child_col}->{s.edge.parent_table}.{s.edge.parent_col}" for s in src.steps])),
                   flag_polarity=("normal-condition name" if sem == "flag" and set(toks) & _FLAG_POLARITY else
                                  "positive name" if sem == "flag" else None),
                   aggregations=(["COUNT(DISTINCT)"] if sem == "id" else ["filter = 0 / = 1 (never SUM/AVG)"] if sem == "flag"
                                 else ["SUM", "AVG", "MIN", "MAX"] if sem in ("money", "quantity") else ["GROUP BY", "filter"]))
catalog = dict(
    dataset=spec, anchor=ds.table,
    tables={t: dict(columns=ti.columns, primary_key=list(ti.pk), not_null=sorted(ti.not_null)) for t, ti in rel.schema.tables.items()} if rel else {},
    relationships=[dict(child=f"{e.child_table}.{e.child_col}", parent=f"{e.parent_table}.{e.parent_col}", status=e.status,
                        nullable=e.nullable) for e in rel.schema.edges] if rel else [],
    columns=cols,
    metrics={k: dict(formula=v.formula, aggregation=v.aggregation, money_like=_is_money_kpi(v), aliases=v.aliases)
             for k, v in cat.kpis.items()},
    vocabulary=dict(abbreviations={k: v for k, v in ABBREV.items()}, units=V._UNITS,
                    synonym_groups=[sorted(g) for g in V._SYNONYMS],
                    note="rewrites apply only when the target exists in this schema; interpretive rewrites are stated in answers"),
    descriptions="none in the schema; no business definitions are invented")
json.dump(catalog, open(out, "w"), indent=1, default=str)
print(out, len(cols), "columns", len(catalog["metrics"]), "metrics", len(catalog["relationships"]), "relationships")
