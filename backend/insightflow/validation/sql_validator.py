"""SQL validation: single SELECT, read-only, existing tables/columns."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Set

from ..knowledge.schema_agent import get_schema


MUTATING_KEYWORDS = {
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "replace", "attach", "detach", "pragma", "grant", "revoke", "vacuum",
    "merge", "call", "exec",
}


@dataclass
class ValidationResult:
    ok: bool
    score: float
    issues: List[str] = field(default_factory=list)
    referenced_tables: List[str] = field(default_factory=list)


def _find_referenced_tables(sql: str) -> Set[str]:
    """Best-effort table detection from FROM and JOIN clauses.
    Supports quoted identifiers ("table_name", [table_name], `table_name`)
    and plain ones."""
    tables: Set[str] = set()
    # Plain identifier
    for m in re.finditer(r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)",
                         sql, flags=re.I):
        tables.add(m.group(1).lower())
    # Double-quoted
    for m in re.finditer(r'\b(?:from|join)\s+"([^"]+)"', sql, flags=re.I):
        tables.add(m.group(1).lower())
    # Backtick
    for m in re.finditer(r"\b(?:from|join)\s+`([^`]+)`", sql, flags=re.I):
        tables.add(m.group(1).lower())
    return tables


def _find_qualified_columns(sql: str) -> Set[str]:
    return {m.group(0).lower()
            for m in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\b", sql)}


def validate_sql(sql: str) -> ValidationResult:
    issues: List[str] = []
    text = (sql or "").strip().rstrip(";").strip()

    if not text:
        return ValidationResult(ok=False, score=0.0, issues=["empty SQL"])

    # single statement
    if ";" in text:
        issues.append("multiple statements are not allowed")

    # must start with SELECT (allow leading WITH ... SELECT)
    head = text.lower().lstrip()
    if not (head.startswith("select") or head.startswith("with")):
        issues.append("only SELECT statements are allowed")

    # must contain SELECT
    if not re.search(r"\bselect\b", text, flags=re.I):
        issues.append("SELECT keyword missing")

    # no mutating keywords
    lowered = text.lower()
    tokens = set(re.findall(r"[a-z]+", lowered))
    hits = MUTATING_KEYWORDS & tokens
    if hits:
        issues.append(f"forbidden keyword(s): {sorted(hits)}")

    # schema checks
    schema = get_schema()
    schema_tables = {t.lower() for t in schema.tables.keys()}
    referenced = _find_referenced_tables(text)
    unknown_tables = referenced - schema_tables
    if unknown_tables:
        issues.append(f"unknown table(s): {sorted(unknown_tables)}")

    # column existence for qualified columns
    known_cols = {c.lower() for c in schema.all_columns()}
    qualified = _find_qualified_columns(text)
    for qc in qualified:
        table, col = qc.split(".", 1)
        if table not in schema_tables:
            continue  # already reported
        if qc not in known_cols:
            issues.append(f"unknown column: {qc}")

    score = max(0.0, 1.0 - 0.34 * len(issues))
    ok = len(issues) == 0
    return ValidationResult(
        ok=ok, score=score, issues=issues, referenced_tables=sorted(referenced),
    )
