"""Agent-friendly facade over the MCP client manager.

This is the ONE place in the agent orchestrator that talks to MCP. It
exposes a small set of narrow helpers (`list_available_tools()`,
`call_analytics_tool()`, etc.) rather than a generic "LLM decides which
tool to run" loop, which keeps the agent bounded and auditable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .client_manager import MCPClientManager, ToolInvocation, get_manager


@dataclass
class AgentToolTrace:
    """Record of every MCP call made in service of one agent run.
    Surfaced in the response's `diagnostics` for auditability."""
    calls: List[Dict[str, Any]] = field(default_factory=list)

    def record(self, inv: ToolInvocation) -> None:
        self.calls.append({
            "server": inv.server, "tool": inv.tool,
            "ok": inv.ok, "duration_ms": inv.duration_ms,
            "error": inv.error if not inv.ok else None,
        })

    def as_dict(self) -> list[dict]:
        return list(self.calls)


class AgentMCP:
    """Thin wrapper around MCPClientManager with per-run tracing."""

    def __init__(self, manager: Optional[MCPClientManager] = None):
        self.mgr = manager or get_manager()
        self.trace = AgentToolTrace()

    # ------------------------------------------------------------------
    def available_servers(self) -> List[str]:
        return self.mgr.available_servers()

    def ensure_connected(self, servers: Optional[List[str]] = None) -> None:
        for name in servers or self.mgr.available_servers():
            try:
                self.mgr.connect(name)
            except Exception:
                # tolerated — the agent can run without MCP
                pass

    def list_available_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        """Shape used by the frontend's Semantic Models + Settings pages."""
        return {
            srv: [{"name": t.name, "description": t.description,
                     "input_schema": t.input_schema}
                     for t in tools]
            for srv, tools in self.mgr.list_tools().items()
        }

    # ------------------------------------------------------------------
    def call(self, server: str, tool: str,
              arguments: Optional[Dict[str, Any]] = None) -> ToolInvocation:
        inv = self.mgr.call(server, tool, arguments or {})
        self.trace.record(inv)
        return inv
