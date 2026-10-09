"""Load and validate the MCP server registry from `backend/mcp_config.yaml`."""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MCPServerConfig:
    name: str
    enabled: bool = True
    transport: str = "stdio"
    command: List[str] = field(default_factory=list)
    cwd: Optional[str] = None
    allowed_tools: Optional[List[str]] = None     # None = all discovered
    call_timeout_seconds: float = 15.0
    startup_timeout_seconds: float = 10.0


@dataclass
class MCPConfig:
    servers: List[MCPServerConfig] = field(default_factory=list)
    max_rows: int = 10_000
    max_response_chars: int = 200_000
    allowed_sql_verbs: List[str] = field(
        default_factory=lambda: ["select", "with"])
    allowed_table_prefixes: List[str] = field(default_factory=list)

    def server(self, name: str) -> Optional[MCPServerConfig]:
        for s in self.servers:
            if s.name == name:
                return s
        return None


def _default_config_path() -> pathlib.Path:
    # backend/mcp_config.yaml relative to this file:
    here = pathlib.Path(__file__).resolve()
    return here.parents[2] / "mcp_config.yaml"


def load_config(path: Optional[str] = None) -> MCPConfig:
    """Read the YAML registry. Falls back to an empty, safe config if the
    file is missing — the agent will still work (just without MCP tools).
    """
    p = pathlib.Path(path) if path else _default_config_path()
    if not p.exists():
        return MCPConfig()

    try:
        import yaml  # type: ignore
    except ImportError:
        # YAML parser missing — fall back to a hand-rolled subset that
        # supports the two shapes we actually use. Avoids a hard dep.
        return _hand_parse_yaml(p.read_text(encoding="utf-8"))

    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    servers: List[MCPServerConfig] = []
    for row in (data.get("servers") or []):
        servers.append(MCPServerConfig(
            name=str(row["name"]),
            enabled=bool(row.get("enabled", True)),
            transport=str(row.get("transport", "stdio")),
            command=list(row.get("command") or []),
            cwd=row.get("cwd"),
            allowed_tools=(list(row["allowed_tools"])
                            if "allowed_tools" in row else None),
            call_timeout_seconds=float(row.get("call_timeout_seconds", 15.0)),
            startup_timeout_seconds=float(
                row.get("startup_timeout_seconds", 10.0)),
        ))
    policy = data.get("policy") or {}
    return MCPConfig(
        servers=servers,
        max_rows=int(policy.get("max_rows", 10_000)),
        max_response_chars=int(policy.get("max_response_chars", 200_000)),
        allowed_sql_verbs=[s.lower() for s in
                            (policy.get("allowed_sql_verbs") or ["select", "with"])],
        allowed_table_prefixes=list(
            policy.get("allowed_table_prefixes") or []),
    )


def _hand_parse_yaml(text: str) -> MCPConfig:
    """Minimal YAML parser for the subset we use. Only kicks in when
    PyYAML isn't installed. Supports the config shape in mcp_config.yaml
    verbatim (lists of dicts under `servers:` + a flat `policy:` block)."""
    import re
    import ast
    servers: list[MCPServerConfig] = []
    policy: dict = {}
    lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    i = 0
    section = None
    cur: Optional[dict] = None
    cur_list_key: Optional[str] = None
    policy_list_key: Optional[str] = None
    def flush():
        nonlocal cur
        if cur is None:
            return
        servers.append(MCPServerConfig(
            name=str(cur.get("name", "")),
            enabled=bool(cur.get("enabled", True)),
            transport=str(cur.get("transport", "stdio")),
            command=list(cur.get("command") or []),
            cwd=cur.get("cwd"),
            allowed_tools=(list(cur["allowed_tools"])
                            if "allowed_tools" in cur else None),
            call_timeout_seconds=float(cur.get("call_timeout_seconds", 15.0)),
            startup_timeout_seconds=float(
                cur.get("startup_timeout_seconds", 10.0)),
        ))
        cur = None
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped == "servers:":
            section = "servers"; i += 1; continue
        if stripped == "policy:":
            flush(); section = "policy"; i += 1; continue
        if section == "servers":
            if stripped.startswith("- name:"):
                flush()
                cur = {"name": stripped.split(":", 1)[1].strip()}
                cur_list_key = None
            elif ":" in stripped and cur is not None and not stripped.startswith("-"):
                k, v = stripped.split(":", 1); k, v = k.strip(), v.strip()
                if v == "":
                    cur_list_key = k; cur[k] = []
                else:
                    try:    val = ast.literal_eval(v)
                    except Exception: val = v
                    cur[k] = val
                    cur_list_key = None
            elif stripped.startswith("-") and cur_list_key is not None and cur is not None:
                item = stripped[1:].strip()
                try:    item = ast.literal_eval(item)
                except Exception: pass
                cur[cur_list_key].append(item)
        elif section == "policy":
            if ":" in stripped and not stripped.startswith("-"):
                k, v = stripped.split(":", 1); k, v = k.strip(), v.strip()
                if v == "":
                    policy_list_key = k; policy[k] = []
                else:
                    try: val = ast.literal_eval(v)
                    except Exception: val = v
                    policy[k] = val
                    policy_list_key = None
            elif stripped.startswith("-") and policy_list_key is not None:
                item = stripped[1:].strip()
                try: item = ast.literal_eval(item)
                except Exception: pass
                policy[policy_list_key].append(item)
        i += 1
    flush()
    return MCPConfig(
        servers=servers,
        max_rows=int(policy.get("max_rows", 10_000)),
        max_response_chars=int(policy.get("max_response_chars", 200_000)),
        allowed_sql_verbs=[s.lower() for s in
                            (policy.get("allowed_sql_verbs") or ["select", "with"])],
        allowed_table_prefixes=list(
            policy.get("allowed_table_prefixes") or []),
    )
