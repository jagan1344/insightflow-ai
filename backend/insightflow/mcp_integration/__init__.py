"""MCP (Model Context Protocol) integration for InsightFlow AI.

Public surface:

    * `load_config()`     — read the YAML registry at backend/mcp_config.yaml.
    * `MCPClientManager`  — connects to approved servers, discovers tools,
                             invokes them with timeouts + policy checks.
    * `ToolInvocation`    — typed response (success, error, metadata).

Nothing here starts a server implicitly. Servers are only launched when a
caller explicitly requests one via `MCPClientManager.connect(name)` with a
name present in the config file.
"""
from .config import MCPConfig, MCPServerConfig, load_config
from .policy import PolicyGuard, PolicyError
from .client_manager import (
    MCPClientManager, ToolInvocation, MCPError, get_manager, reset_manager,
)
from .agent_tools import AgentMCP, AgentToolTrace

__all__ = [
    "MCPConfig", "MCPServerConfig", "load_config",
    "PolicyGuard", "PolicyError",
    "MCPClientManager", "ToolInvocation", "MCPError",
    "get_manager", "reset_manager",
    "AgentMCP", "AgentToolTrace",
]
