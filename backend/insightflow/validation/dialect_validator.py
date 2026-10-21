"""SQL dialect compatibility check.

The pipeline executes against SQLite by default. An LLM-backed text-to-
SQL (configured via ``LLM_PROVIDER`` + ``LLM_MODEL``) often returns
Postgres-flavoured SQL — most commonly ``EXTRACT(... FROM date)`` —
which SQLite cannot execute. The structural ``sql_validator`` catches
mutating keywords and syntactic nonsense but does not catch
dialect-specific functions.

``validate_dialect`` scans for the dialect-incompatible constructs we
have actually observed in the wild and returns a crisp issue list. On a
negative verdict, the orchestrator refuses to execute (saving a
confusing engine error) and routes the question to ABSTAIN with a
helpful reason.

This is intentionally conservative: it names each incompatible token
and leaves anything it doesn't recognise alone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


# Each entry is (regex, dialect, replacement_hint).
_INCOMPATIBILITIES: List[tuple[str, str, str]] = [
    # ---- Postgres / standard SQL date functions ----
    (r"\bextract\s*\(\s*(?:year|month|day|week|quarter|dow|doy|hour|minute)\s+from\b",
     "postgres",
     "SQLite has no EXTRACT(); use substr(date, start, len) or strftime()."),
    (r"\bdate_trunc\s*\(", "postgres",
     "SQLite has no DATE_TRUNC(); use substr(date, 1, 7) for monthly, substr(date, 1, 4) for yearly."),
    (r"\bto_char\s*\(", "postgres",
     "SQLite has no TO_CHAR(); use substr() or strftime() for formatting."),
    (r"\bto_date\s*\(", "postgres",
     "SQLite has no TO_DATE(); dates are stored as ISO text."),
    (r"\bdate_part\s*\(", "postgres",
     "SQLite has no DATE_PART(); use substr() or strftime()."),
    (r"\binterval\s+'[^']+'", "postgres",
     "SQLite has no INTERVAL literal; use date() arithmetic: date(col, '+1 month')."),
    (r"\bage\s*\(", "postgres", "SQLite has no AGE(); use julianday() arithmetic."),
    (r"\bnow\s*\(\s*\)", "postgres",
     "SQLite uses CURRENT_TIMESTAMP, not now()."),
    (r"\bgenerate_series\s*\(", "postgres",
     "SQLite has no generate_series; use a recursive CTE or join against the data."),
    (r"\bunnest\s*\(", "postgres", "SQLite has no UNNEST()."),
    (r"\blateral\b", "postgres", "SQLite has no LATERAL joins."),
    (r"\bfilter\s*\(\s*where\b", "postgres/standard",
     "SQLite 3.30+ supports FILTER(WHERE ...). Older builds do not — prefer CASE WHEN instead."),
    (r"\bwithin\s+group\b", "postgres", "SQLite has no WITHIN GROUP."),
    (r"\bdistinct\s+on\s*\(", "postgres", "SQLite has no DISTINCT ON; use GROUP BY + MIN/MAX."),
    # ---- SQL Server syntax ----
    (r"\bdateadd\s*\(", "mssql", "SQLite uses date(col, '+N days'), not DATEADD()."),
    (r"\bdatediff\s*\(", "mssql", "SQLite uses julianday() differences, not DATEDIFF()."),
    (r"\beomonth\s*\(", "mssql", "SQLite has no EOMONTH(); use date(..., 'start of month', '+1 month', '-1 day')."),
    (r"\bgetdate\s*\(\s*\)", "mssql", "SQLite uses CURRENT_TIMESTAMP, not GETDATE()."),
    (r"\btop\s+\d+\s", "mssql", "SQLite uses LIMIT N, not TOP N."),
    (r"\bconvert\s*\(", "mssql", "SQLite uses CAST(... AS ...)."),
    # ---- MySQL syntax ----
    (r"\bdate_format\s*\(", "mysql", "SQLite uses strftime(fmt, date), not DATE_FORMAT()."),
    (r"\bstr_to_date\s*\(", "mysql", "SQLite has no STR_TO_DATE()."),
    (r"\byearweek\s*\(", "mysql", "SQLite has no YEARWEEK(); use strftime('%Y-%W', date)."),
]


@dataclass
class DialectReport:
    ok: bool
    dialect: str = "sqlite"
    issues: List[str] = field(default_factory=list)
    offending_tokens: List[str] = field(default_factory=list)


def validate_dialect(sql: str, dialect: str = "sqlite") -> DialectReport:
    """Return a report on whether the SQL is compatible with the target
    dialect. Only SQLite is validated against today; the function returns
    `ok=True` for any other dialect so it never falsely rejects.
    """
    if not sql or dialect.lower() != "sqlite":
        return DialectReport(ok=True, dialect=dialect)
    text = sql.lower()
    issues: List[str] = []
    tokens: List[str] = []
    for pattern, foreign, hint in _INCOMPATIBILITIES:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            tokens.append(m.group(0))
            issues.append(
                f"SQL uses {foreign} syntax ('{m.group(0).strip()}') "
                f"that SQLite cannot execute. {hint}")
    if issues:
        return DialectReport(ok=False, dialect=dialect, issues=issues,
                              offending_tokens=tokens)
    return DialectReport(ok=True, dialect=dialect)
