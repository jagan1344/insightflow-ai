"""MCP introspection + invocation endpoints.

Used by the frontend's Settings, Data Sources, Semantic Models and
Reports pages to inspect connected MCP servers and call tools without
having to run their own stdio client.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/mcp", tags=["mcp"])


# ---------------------------------------------------------------------------
# Lazy manager — created on first request, kept warm across requests.
# ---------------------------------------------------------------------------

def _mgr():
    try:
        from insightflow.mcp_integration import get_manager
    except Exception as e:
        raise HTTPException(status_code=503,
                             detail=f"MCP integration unavailable: {e}")
    return get_manager()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ServerStatus(BaseModel):
    name: str
    enabled: bool
    connected: bool
    transport: str
    tool_count: int
    tools: List[str]
    allowed_tools: Optional[List[str]] = None
    error: Optional[str] = None


class ToolCallRequest(BaseModel):
    server: str = Field(..., min_length=1)
    tool: str = Field(..., min_length=1)
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(BaseModel):
    ok: bool
    server: str
    tool: str
    content: Any = None
    raw_text: str = ""
    error: str = ""
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/servers", response_model=List[ServerStatus])
def list_servers() -> List[ServerStatus]:
    """Status of every MCP server listed in `backend/mcp_config.yaml`."""
    mgr = _mgr()
    cfg = mgr.config
    out: List[ServerStatus] = []
    connected = set(mgr.connected_servers())
    for s in cfg.servers:
        tools: List[str] = []
        err = None
        if s.name in connected:
            try:
                tools = [t.name for t in mgr.list_tools(s.name).get(s.name, [])]
            except Exception as e:
                err = str(e)
        out.append(ServerStatus(
            name=s.name, enabled=s.enabled,
            connected=(s.name in connected),
            transport=s.transport,
            tool_count=len(tools), tools=tools,
            allowed_tools=s.allowed_tools, error=err,
        ))
    return out


@router.post("/connect/{name}", response_model=ServerStatus)
def connect_server(name: str) -> ServerStatus:
    mgr = _mgr()
    try:
        mgr.connect(name, timeout=15)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    tools = [t.name for t in mgr.list_tools(name).get(name, [])]
    cfg = mgr.config.server(name)
    assert cfg is not None
    return ServerStatus(
        name=name, enabled=cfg.enabled, connected=True,
        transport=cfg.transport, tool_count=len(tools), tools=tools,
        allowed_tools=cfg.allowed_tools,
    )


@router.post("/connect_all", response_model=Dict[str, str])
def connect_all_servers() -> Dict[str, str]:
    mgr = _mgr()
    return mgr.connect_all(timeout=20)


@router.get("/tools")
def list_tools(server: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Discovered tool list, per server. Includes JSON Schema inputs."""
    mgr = _mgr()
    out: Dict[str, List[Dict[str, Any]]] = {}
    for srv_name, tools in mgr.list_tools(server).items():
        out[srv_name] = [{
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
        } for t in tools]
    return out


@router.post("/call", response_model=ToolCallResponse)
def call_tool(req: ToolCallRequest) -> ToolCallResponse:
    mgr = _mgr()
    inv = mgr.call(req.server, req.tool, req.arguments)
    return ToolCallResponse(
        ok=inv.ok, server=inv.server, tool=inv.tool,
        content=inv.content, raw_text=inv.raw_text,
        error=inv.error, duration_ms=inv.duration_ms,
    )
