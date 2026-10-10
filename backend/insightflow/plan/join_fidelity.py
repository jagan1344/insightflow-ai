"""Static join-cardinality guard for aggregate business metrics.

This guard is intentionally conservative. It verifies known demo star-schema
joins against declared FK/PK relationships. It does not claim to prove
cardinality for arbitrary SQL or unknown schemas; those joins are flagged as
unverified so the caller can lower confidence rather than silently trust them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

@dataclass
class JoinCheck:
    name: str
    passed: bool
    detail: str

@dataclass
class JoinFidelityReport:
    ok: bool
    checks: List[JoinCheck] = field(default_factory=list)

# Each pair is (table, key-column); both directions are accepted.
_SAFE_RELATIONSHIPS = {
    frozenset((("orders", "region_id"), ("regions", "region_id"))),
    frozenset((("orders", "product_id"), ("products", "product_id"))),
    frozenset((("orders", "customer_id"), ("customers", "customer_id"))),
    frozenset((("customers", "region_id"), ("regions", "region_id"))),
}
_KNOWN_TABLES = {"orders", "regions", "products", "customers"}
_CLAUSE_END = re.compile(
    r"\s+(?:(?:LEFT|RIGHT|FULL|INNER|CROSS)\s+)?JOIN\b|"
    r"\s+(?:WHERE|GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT|UNION)\b",
    re.IGNORECASE,
)
_TABLE_RE = re.compile(
    r"\b(FROM|JOIN)\s+[\"'`\[]?([a-zA-Z_][\w]*)[\"'`\]]?"
    r"(?:\s+(?:AS\s+)?(?!ON\b|USING\b|WHERE\b|JOIN\b|LEFT\b|RIGHT\b|INNER\b|FULL\b|CROSS\b|GROUP\b|ORDER\b|LIMIT\b)([a-zA-Z_]\w*))?",
    re.IGNORECASE,
)
_JOIN_RE = re.compile(
    r"\bJOIN\s+[\"'`\[]?([a-zA-Z_][\w]*)[\"'`\]]?"
    r"(?:\s+(?:AS\s+)?(?!ON\b|USING\b|WHERE\b|JOIN\b|LEFT\b|RIGHT\b|INNER\b|FULL\b|CROSS\b|GROUP\b|ORDER\b|LIMIT\b)([a-zA-Z_]\w*))?\s+ON\b",
    re.IGNORECASE,
)
_EQ_RE = re.compile(r"([a-zA-Z_]\w*)\.([a-zA-Z_]\w*)\s*=\s*([a-zA-Z_]\w*)\.([a-zA-Z_]\w*)", re.IGNORECASE)

def _extract_cte_bodies(sql: str) -> dict[str, str]:
    """Extract top-level WITH CTE bodies using balanced parentheses."""
    out: dict[str, str] = {}
    with_match = re.search(r"\bWITH\b", sql, re.IGNORECASE)
    if not with_match:
        return out
    pos = with_match.end()
    while pos < len(sql):
        match = re.match(
            r"\s*,?\s*([a-zA-Z_]\w*)\s+AS\s*\(",
            sql[pos:], re.IGNORECASE,
        )
        if not match:
            break
        name = match.group(1).lower()
        body_start = pos + match.end()
        depth = 1
        quote = None
        i = body_start
        while i < len(sql) and depth:
            ch = sql[i]
            if quote:
                if ch == quote:
                    if i + 1 < len(sql) and sql[i + 1] == quote:
                        i += 1
                    else:
                        quote = None
            elif ch in ("'", '"', "`"):
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        if depth:
            break
        out[name] = sql[body_start:i - 1]
        pos = i
        # Another CTE starts with a comma; otherwise the WITH clause ended.
        probe = re.match(r"\s*,", sql[pos:])
        if not probe:
            break
        pos += probe.end()
    return out


def _cte_join_is_one_to_one(sql: str, condition: str,
                            referenced_ctes: set[str],
                            cte_bodies: dict[str, str]) -> bool:
    """Certify joins between grouped CTEs only when join keys are grouped."""
    if len(referenced_ctes) < 2 or not referenced_ctes.issubset(cte_bodies):
        return False
    if re.search(r"\bOR\b", condition, re.IGNORECASE):
        return False
    equalities = list(_EQ_RE.finditer(condition))
    if not equalities:
        return False
    for name in referenced_ctes:
        body = cte_bodies[name]
        group = re.search(
            r"\bGROUP\s+BY\b(.*?)(?:\bHAVING\b|\bORDER\s+BY\b|\bLIMIT\b|$)",
            body, re.IGNORECASE | re.DOTALL,
        )
        if not group:
            return False
        group_clause = group.group(1)
        relevant_cols = []
        for eq in equalities:
            left_alias, left_col, right_alias, right_col = (
                eq.group(1).lower(), eq.group(2).lower(),
                eq.group(3).lower(), eq.group(4).lower(),
            )
            if left_alias == name:
                relevant_cols.append(left_col)
            if right_alias == name:
                relevant_cols.append(right_col)
        if not relevant_cols or any(
            not re.search(rf"\b{re.escape(col)}\b", group_clause, re.IGNORECASE)
            for col in relevant_cols
        ):
            return False
    return True


def check_join_fidelity(sql: str) -> JoinFidelityReport:
    """Check joins for known safe key relationships; unknown joins fail closed."""
    if not sql or not re.search(r"\bJOIN\b", sql, re.IGNORECASE):
        return JoinFidelityReport(ok=True, checks=[
            JoinCheck("join_cardinality", True, "No JOIN clause; no join fan-out risk.")
        ])

    cte_bodies = _extract_cte_bodies(sql)
    cte_names = set(cte_bodies)
    aliases = {}
    for match in _TABLE_RE.finditer(sql):
        table = match.group(2).lower()
        alias = (match.group(3) or table).lower()
        aliases[alias] = table
        aliases[table] = table

    checks = []
    for index, match in enumerate(_JOIN_RE.finditer(sql), start=1):
        joined_table = match.group(1).lower()
        condition_start = match.end()
        next_clause = _CLAUSE_END.search(sql, condition_start)
        condition = sql[condition_start:next_clause.start() if next_clause else len(sql)]
        relationships = set()
        for eq in _EQ_RE.finditer(condition):
            left_alias, left_col, right_alias, right_col = (
                eq.group(1).lower(), eq.group(2).lower(),
                eq.group(3).lower(), eq.group(4).lower()
            )
            left_table = aliases.get(left_alias, left_alias)
            right_table = aliases.get(right_alias, right_alias)
            relationships.add(frozenset(((left_table, left_col), (right_table, right_col))))

        known_tables_in_condition = {
            aliases.get(a.lower(), a.lower())
            for a in re.findall(r"\b([a-zA-Z_]\w*)\.[a-zA-Z_]\w*\b", condition)
        }
        # The compiler deliberately joins grouped CTEs for comparisons and
        # contribution analysis. Certify these only when every participating
        # CTE is grouped by the exact equality key; otherwise fail closed.
        if joined_table in cte_names:
            cte_refs = known_tables_in_condition & cte_names
            cte_safe = _cte_join_is_one_to_one(
                sql, condition, cte_refs, cte_bodies,
            )
            checks.append(JoinCheck(
                f"join_{index}_cardinality", cte_safe,
                ("Join between grouped CTEs uses grouped equality keys."
                 if cte_safe else
                 f"Join to CTE {joined_table!r} has unverified cardinality; aggregate totals cannot be certified.")
            ))
            continue

        if joined_table not in _KNOWN_TABLES or not known_tables_in_condition.issubset(_KNOWN_TABLES):
            checks.append(JoinCheck(
                f"join_{index}_cardinality", False,
                f"Join to {joined_table!r} uses unknown schema/cardinality; aggregate totals cannot be certified."
            ))
            continue

        # OR can bypass a key equality (e.g. FK=PK OR 1=1), so do not
        # certify the join even if one safe equality is also present.
        has_or = bool(re.search(r"\bOR\b", condition, re.IGNORECASE))
        safe_relationships = {
            rel for rel in relationships
            if rel in _SAFE_RELATIONSHIPS
            and joined_table in {table for table, _column in rel}
        }
        safe = bool(safe_relationships) and not has_or
        checks.append(JoinCheck(
            f"join_{index}_cardinality", safe,
            (f"Join to {joined_table!r} uses a known FK/PK relationship."
             if safe else
             f"Join to {joined_table!r} does not match a declared FK/PK relationship; it may multiply fact rows."
            )
        ))
    if not checks:
        checks.append(JoinCheck("join_cardinality", False,
                                "JOIN syntax could not be parsed safely."))
    return JoinFidelityReport(ok=all(c.passed for c in checks), checks=checks)
