"""Shared helpers for InsightFlow MCP server modules.

The modern mcp 2.x SDK uses `MCPServer` with `@app.tool()` decorators —
schema is inferred from the function signature, result from the return
value. We keep this helper module tiny.
"""
from __future__ import annotations

import re
from typing import Any, Dict


_DANGEROUS = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|replace|"
    r"attach|detach|pragma|grant|revoke|vacuum|merge|exec|call)\b",
    re.IGNORECASE,
)


def ensure_readonly_sql(sql: str) -> None:
    """Reject anything that isn't a single SELECT/WITH statement."""
    s = (sql or "").strip()
    if not s:
        raise ValueError("empty SQL")
    head = s.lstrip("(").lstrip().lower().split(None, 1)[0] if s else ""
    if head not in ("select", "with"):
        raise ValueError(f"only SELECT/WITH statements allowed; saw {head!r}")
    if _DANGEROUS.search(s):
        raise ValueError("SQL contains a disallowed keyword")
    if ";" in s.rstrip(";"):
        raise ValueError("multiple statements are not allowed")


def table_allowed(name: str, allowed_prefixes: list[str] | tuple[str, ...]) -> bool:
    lname = (name or "").lower()
    return any(lname == p.lower() or lname.startswith(p.lower().strip())
               for p in allowed_prefixes if p.strip())
