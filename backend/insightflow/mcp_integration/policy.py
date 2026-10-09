"""Client-side policy guard for MCP tool invocations.

Server-side policies (allowlists, read-only enforcement) still run.
This layer is defence-in-depth so a misbehaving or compromised server
can't bypass the client's own invariants.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict

from .config import MCPConfig, MCPServerConfig


class PolicyError(Exception):
    """Raised when a tool call is blocked by policy."""


_DANGEROUS_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|replace|"
    r"attach|detach|pragma|grant|revoke|vacuum|merge|exec|call)\b",
    re.IGNORECASE,
)


class PolicyGuard:
    def __init__(self, config: MCPConfig):
        self.config = config

    # ------------------------------------------------------------------
    def allow_tool(self, server: MCPServerConfig, tool_name: str) -> None:
        if server.allowed_tools is None:
            return
        if tool_name not in server.allowed_tools:
            raise PolicyError(
                f"tool {tool_name!r} is not in the allowlist for "
                f"server {server.name!r}: {server.allowed_tools}")

    # ------------------------------------------------------------------
    def check_arguments(self, server: MCPServerConfig, tool_name: str,
                         arguments: Dict[str, Any]) -> None:
        if not isinstance(arguments, dict):
            raise PolicyError("tool arguments must be a dict")

        # SQL guard — enforced on any argument literally named "sql"
        # or "query" regardless of server.
        for key in ("sql", "query"):
            if key in arguments and isinstance(arguments[key], str):
                self._check_sql(arguments[key])

        # Table guard — on arguments named "table" or "table_name"
        for key in ("table", "table_name"):
            if key in arguments and isinstance(arguments[key], str):
                self._check_table(arguments[key])

    def _check_sql(self, sql: str) -> None:
        s = (sql or "").strip().lstrip("(").lstrip().lower()
        verb = s.split(None, 1)[0] if s else ""
        if verb not in self.config.allowed_sql_verbs:
            raise PolicyError(
                f"SQL verb {verb!r} not in allowlist "
                f"{self.config.allowed_sql_verbs}")
        if _DANGEROUS_SQL.search(sql):
            raise PolicyError("SQL contains a disallowed keyword")
        if ";" in sql.rstrip(";"):
            raise PolicyError("multiple SQL statements are not allowed")

    def _check_table(self, name: str) -> None:
        if not self.config.allowed_table_prefixes:
            return
        lname = name.lower()
        for p in self.config.allowed_table_prefixes:
            if lname == p.lower() or lname.startswith(p.lower()):
                return
        raise PolicyError(
            f"table {name!r} is not in the allowlist "
            f"{self.config.allowed_table_prefixes}")

    # ------------------------------------------------------------------
    def check_response(self, response_text: str) -> None:
        """Cap response size so a misbehaving tool can't blow up memory."""
        if len(response_text) > self.config.max_response_chars:
            raise PolicyError(
                f"response size {len(response_text)} exceeds limit "
                f"{self.config.max_response_chars}")
