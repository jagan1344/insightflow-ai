"""Business-terminology and KPI governance.

Optional JSON file (path in env INSIGHTFLOW_METRICS_FILE) layered over the
auto-derived KPI catalog:

{
 "tables": {
   "visits": {
     "date_default": "visit_date",
     "metrics": [
       {"id": "net_fee", "name": "Net Fee", "expression": "SUM(fee - copay)",
        "synonyms": ["net revenue", "revenue"], "unit": "currency"}
     ]
   }
 }
}

Rules
  * expressions are validated: only SUM/AVG/COUNT/MIN/MAX/NULLIF/COALESCE/
    ROUND/ABS, numbers, + - * / and parentheses, and column names of the
    anchor table. Anything else (subqueries, ;, comments, other functions)
    is rejected, so a config file cannot introduce unsafe SQL.
  * a synonym claimed by more than one metric (configured or auto-derived)
    is a CONFLICT: it is removed from every alias list and recorded in
    `catalog.conflicts`, so the planner clarifies instead of picking one.
  * `date_default` resolves which date column a time question uses when the
    table has several.
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional, Tuple

_ALLOWED_FUNCS = {"sum", "avg", "count", "min", "max", "nullif", "coalesce",
                  "round", "abs", "distinct"}


def load_config(path: Optional[str] = None) -> dict:
    path = path or os.environ.get("INSIGHTFLOW_METRICS_FILE", "")
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def validate_expression(expr: str, columns: List[str]) -> Tuple[Optional[str], str]:
    """-> (sql with quoted columns | None, error)."""
    if not isinstance(expr, str) or not expr.strip():
        return None, "empty expression"
    if re.search(r"[;`]|--|/\*|\bselect\b|\bfrom\b|\bunion\b|\battach\b|\bpragma\b",
                 expr, re.I):
        return None, "forbidden token"
    cols = {c.lower(): c for c in columns}
    out, pos = [], 0
    for m in re.finditer(r"[A-Za-z_]\w*|\d+(?:\.\d+)?|[()+\-*/,\s]|\"[^\"]+\"|.", expr):
        tok = m.group(0)
        if re.fullmatch(r"\s|[()+\-*/,]|\d+(?:\.\d+)?", tok):
            out.append(tok); continue
        name = tok.strip('"')
        if tok[0] == '"':
            if name.lower() in cols:
                out.append('"%s"' % cols[name.lower()]); continue
            return None, f"unknown column {name!r}"
        if tok.lower() in _ALLOWED_FUNCS:
            out.append(tok.upper()); continue
        if name.lower() in cols:
            out.append('"%s"' % cols[name.lower()]); continue
        return None, f"unknown identifier {tok!r}"
    return "".join(out), ""


def apply(ds, kpis: dict, KPIDefinition) -> Dict[str, List[str]]:
    """Merge configured metrics into `kpis` (mutates) and return the
    alias-conflict map {alias: [kpi_id, ...]}. Invalid definitions are
    skipped and listed under conflicts['__invalid__'] for visibility."""
    cfg = load_config().get("tables", {}).get(ds.table, {})
    invalid: List[str] = []
    for m in cfg.get("metrics", []):
        try:
            mid = re.sub(r"\W+", "_", str(m["id"]).lower()).strip("_")
            sql, err = validate_expression(m["expression"], list(ds.columns))
        except (KeyError, TypeError):
            invalid.append("malformed metric entry"); continue
        if sql is None:
            invalid.append(f"{m.get('id')}: {err}"); continue
        syns = [str(x).lower() for x in m.get("synonyms", [])]
        name = str(m.get("name", mid))
        kpis[mid] = KPIDefinition(
            kpi_id=mid, display_name=name, aggregation="derived",
            formula=sql, required_columns=[], unit=str(m.get("unit", "")),
            aliases=sorted({name.lower(), mid.replace("_", " ")} | set(syns)),
            description="configured metric")
    # auto-derived collision: several revenue-like measure columns
    claims: Dict[str, List[str]] = {}
    for kid, k in kpis.items():
        for a in k.aliases:
            claims.setdefault(a.lower(), []).append(kid)
    conflicts = {}
    for a, ids in claims.items():
        ids = sorted(set(ids))
        # same formula under two ids is a duplicate, not a conflict
        if len({re.sub(r"\s+", "", kpis[i].formula) for i in ids}) > 1:
            conflicts[a] = ids
    rev_like = [c for c, i in ds.columns.items()
                if i.role == "measure" and any(
                    t in c.lower() for t in ("revenue", "sales", "amount",
                                              "turnover", "gross"))]
    if len(rev_like) > 1 and "total_revenue" in kpis and \
            not any("revenue" in c.lower() for c in cfg.get("metrics", [])
                    if isinstance(c, str)):
        cands = [f"sum_{c.lower()}" for c in rev_like if f"sum_{c.lower()}" in kpis]
        if len(cands) > 1 and not any(
                "revenue" in (m.get("synonyms") or []) for m in cfg.get("metrics", [])):
            conflicts.setdefault("revenue", sorted(set(cands + ["total_revenue"])))
    for alias, ids in conflicts.items():
        for kid in ids:
            k = kpis[kid]
            k.aliases = [a for a in k.aliases if a.lower() != alias]
    if invalid:
        conflicts["__invalid__"] = invalid
    return conflicts


def date_default(table: str) -> Optional[str]:
    return load_config().get("tables", {}).get(table, {}).get("date_default")
