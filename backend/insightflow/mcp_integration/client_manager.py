"""MCP client manager.

Maintains an asyncio ClientSession per approved server. Starts the
server as a stdio subprocess, keeps the session open across tool
invocations, exposes a `call(server, tool, args)` method that enforces
timeouts and policy, and cleans up on shutdown.

Design notes
    * One manager instance per process; `get_manager()` returns it.
    * All I/O is async. Sync entry points (`call_sync`, `invoke_sync`)
      wrap `asyncio.run_coroutine_threadsafe` against a dedicated
      background event loop so FastAPI / pytest callers aren't forced to
      go async.
    * The background event loop is created lazily on first use, so
      merely importing this module is free.
    * `connect(name)` / `connect_all()` are idempotent — a second call
      with the same name re-uses the live session.
    * `shutdown()` closes every session and joins the loop thread.
    * Failures are reported via `ToolInvocation.ok=False`; never raised,
      so a misbehaving MCP server can't take down the agent.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import threading
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional  # noqa: F401

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except Exception:  # pragma: no cover
    ClientSession = None  # type: ignore
    StdioServerParameters = None  # type: ignore
    stdio_client = None  # type: ignore

from .config import MCPConfig, MCPServerConfig, load_config
from .policy import PolicyError, PolicyGuard


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class ToolDescriptor:
    name: str
    description: str
    input_schema: Dict[str, Any]


@dataclass
class ToolInvocation:
    ok: bool
    tool: str
    server: str
    content: Any = None            # structured result (parsed JSON when possible)
    raw_text: str = ""             # the server's string response
    error: str = ""
    duration_ms: int = 0
    is_error: bool = False         # server reported the call errored


class MCPError(RuntimeError):
    """Raised when the client manager itself fails (e.g. SDK missing)."""


# ---------------------------------------------------------------------------
# One connection
# ---------------------------------------------------------------------------

@dataclass
class _ServerConn:
    cfg: MCPServerConfig
    session: Any                    # ClientSession
    tools: Dict[str, ToolDescriptor] = field(default_factory=dict)
    # Task that owns the AsyncExitStack. Cancelling it closes the stdio
    # transport and the client session in the task that opened them,
    # which keeps anyio's cancel-scope invariant happy.
    runner_task: Any = None
    shutdown_event: Any = None


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class MCPClientManager:
    def __init__(self, config: Optional[MCPConfig] = None):
        self.config: MCPConfig = config or load_config()
        self.policy = PolicyGuard(self.config)
        self._conns: Dict[str, _ServerConn] = {}
        self._lock = threading.Lock()
        # Dedicated background loop so FastAPI (sync) and pytest can call
        # async MCP APIs without owning the loop themselves.
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_ready = threading.Event()

    # ------------------------------------------------------------------
    # Lifecycle
    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is not None and self._loop.is_running():
            return self._loop
        with self._lock:
            if self._loop is not None and self._loop.is_running():
                return self._loop
            self._loop_ready.clear()
            def _runner():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                self._loop_ready.set()
                try:
                    loop.run_forever()
                finally:
                    loop.close()
            t = threading.Thread(target=_runner, daemon=True,
                                  name="mcp-event-loop")
            t.start()
            self._loop_thread = t
            self._loop_ready.wait(timeout=5.0)
            assert self._loop is not None
            return self._loop

    def _run(self, coro, timeout: Optional[float] = None):
        loop = self._ensure_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        return fut.result(timeout=timeout)

    # ------------------------------------------------------------------
    # Public API
    def available_servers(self) -> List[str]:
        return [s.name for s in self.config.servers if s.enabled]

    def connected_servers(self) -> List[str]:
        return list(self._conns.keys())

    def connect_all(self, timeout: Optional[float] = None) -> Dict[str, str]:
        """Connect every enabled server. Returns {name: status}."""
        out: Dict[str, str] = {}
        for s in self.config.servers:
            if not s.enabled:
                out[s.name] = "disabled"
                continue
            try:
                self.connect(s.name, timeout=timeout)
                out[s.name] = "connected"
            except Exception as e:  # noqa
                out[s.name] = f"error: {e}"
        return out

    def connect(self, name: str, timeout: Optional[float] = None) -> None:
        if ClientSession is None:
            raise MCPError("mcp SDK is not installed")
        if name in self._conns:
            return
        cfg = self.config.server(name)
        if cfg is None or not cfg.enabled:
            raise MCPError(f"server {name!r} not found or disabled")
        self._run(self._connect(cfg),
                   timeout=(timeout or cfg.startup_timeout_seconds + 5.0))

    async def _connect(self, cfg: MCPServerConfig) -> None:
        if ClientSession is None or stdio_client is None:
            raise MCPError("mcp SDK is not installed")
        if cfg.transport != "stdio":
            raise MCPError(
                f"unsupported transport {cfg.transport!r} for server "
                f"{cfg.name!r}")
        if not cfg.command:
            raise MCPError(f"server {cfg.name!r} has no command")

        default_cwd = pathlib.Path(__file__).resolve().parents[2]
        cwd = cfg.cwd or str(default_cwd)
        env = os.environ.copy()
        env.setdefault("PYTHONPATH", str(default_cwd))

        params = StdioServerParameters(
            command=cfg.command[0], args=cfg.command[1:], cwd=cwd, env=env,
        )

        ready = asyncio.Event()
        shutdown = asyncio.Event()
        box: Dict[str, Any] = {}

        async def runner():
            try:
                async with AsyncExitStack() as stack:
                    read, write = await stack.enter_async_context(
                        stdio_client(params))
                    session = await stack.enter_async_context(
                        ClientSession(read, write))
                    await asyncio.wait_for(
                        session.initialize(),
                        timeout=cfg.startup_timeout_seconds)
                    tools_resp = await session.list_tools()
                    tools = {
                        t.name: ToolDescriptor(
                            name=t.name,
                            description=t.description or "",
                            input_schema=dict(getattr(t, "inputSchema", {}) or {}),
                        )
                        for t in getattr(tools_resp, "tools", []) or []
                    }
                    box["session"] = session
                    box["tools"] = tools
                    ready.set()
                    await shutdown.wait()
            except Exception as e:  # noqa
                box["error"] = e
                ready.set()

        task = asyncio.create_task(runner(),
                                    name=f"mcp-conn-{cfg.name}")
        try:
            await asyncio.wait_for(ready.wait(),
                                    timeout=cfg.startup_timeout_seconds + 2.0)
        except asyncio.TimeoutError:
            shutdown.set()
            raise MCPError(
                f"server {cfg.name!r} startup timed out after "
                f"{cfg.startup_timeout_seconds}s")
        if "error" in box:
            raise MCPError(f"server {cfg.name!r}: {box['error']}")

        self._conns[cfg.name] = _ServerConn(
            cfg=cfg,
            session=box["session"],
            tools=box["tools"],
            runner_task=task,
            shutdown_event=shutdown,
        )
        log.info("MCP connected: %s (%d tools)",
                  cfg.name, len(box["tools"]))

    # ------------------------------------------------------------------
    def list_tools(self, server: Optional[str] = None
                    ) -> Dict[str, List[ToolDescriptor]]:
        """Return discovered tools, keyed by server name."""
        if server is None:
            return {name: list(c.tools.values())
                     for name, c in self._conns.items()}
        c = self._conns.get(server)
        return {server: list(c.tools.values())} if c else {server: []}

    # ------------------------------------------------------------------
    def call(self, server: str, tool: str,
              arguments: Optional[Dict[str, Any]] = None,
              timeout: Optional[float] = None) -> ToolInvocation:
        arguments = arguments or {}
        started = time.monotonic()
        if server not in self._conns:
            try:
                self.connect(server)
            except Exception as e:  # noqa
                return ToolInvocation(
                    ok=False, server=server, tool=tool,
                    error=f"connect failed: {e}",
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
        conn = self._conns[server]
        try:
            self.policy.allow_tool(conn.cfg, tool)
            self.policy.check_arguments(conn.cfg, tool, arguments)
        except PolicyError as e:
            return ToolInvocation(
                ok=False, server=server, tool=tool,
                error=f"policy: {e}",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        try:
            raw = self._run(
                self._call(conn, tool, arguments),
                timeout=(timeout or conn.cfg.call_timeout_seconds + 5.0),
            )
        except asyncio.TimeoutError:
            return ToolInvocation(
                ok=False, server=server, tool=tool,
                error=f"timeout after {conn.cfg.call_timeout_seconds}s",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except Exception as e:  # noqa
            return ToolInvocation(
                ok=False, server=server, tool=tool, error=str(e),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        # Policy on response size
        try:
            self.policy.check_response(raw.raw_text)
        except PolicyError as e:
            raw.ok = False
            raw.error = f"policy: {e}"
        raw.duration_ms = int((time.monotonic() - started) * 1000)
        return raw

    async def _call(self, conn: _ServerConn, tool: str,
                     arguments: Dict[str, Any]) -> ToolInvocation:
        session = conn.session
        try:
            result = await asyncio.wait_for(
                session.call_tool(tool, arguments),
                timeout=conn.cfg.call_timeout_seconds,
            )
        except Exception as e:  # noqa
            return ToolInvocation(ok=False, server=conn.cfg.name,
                                   tool=tool, error=str(e))
        # Flatten content list; prefer text blocks
        parts: List[str] = []
        for c in getattr(result, "content", []) or []:
            t = getattr(c, "text", None)
            if t is not None:
                parts.append(str(t))
            else:
                parts.append(str(c))
        text = "\n".join(parts) if parts else ""
        structured = None
        if text.strip():
            try:
                structured = json.loads(text)
            except Exception:
                structured = text
        is_error = bool(getattr(result, "isError", False))
        error_text = ""
        # Many servers return a 200 response carrying `{"error": "..."}`
        # as the structured content. Treat that as a tool-level failure
        # so callers see `ok=False` without having to inspect `content`
        # themselves.
        if (not is_error and isinstance(structured, dict)
                and set(structured.keys()) >= {"error"}
                and (len(structured) == 1
                     or structured.get("ok") is False)):
            is_error = True
            error_text = str(structured["error"])
        return ToolInvocation(
            ok=not is_error,
            server=conn.cfg.name,
            tool=tool,
            content=structured,
            raw_text=text,
            error=error_text,
            is_error=is_error,
        )

    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        if not self._conns and self._loop is None:
            return
        try:
            self._run(self._shutdown(), timeout=10.0)
        except Exception:
            pass
        loop = self._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if self._loop_thread and self._loop_thread.is_alive():
            self._loop_thread.join(timeout=5.0)
        self._loop = None
        self._loop_thread = None
        self._conns.clear()

    async def _shutdown(self) -> None:
        # Signal every runner to exit its own context — the runner then
        # closes the stdio transport + session in the same task that
        # opened them, so anyio's cancel scope stays within one task.
        for name, conn in list(self._conns.items()):
            try:
                if conn.shutdown_event is not None:
                    conn.shutdown_event.set()
            except Exception:
                pass
        for name, conn in list(self._conns.items()):
            task = conn.runner_task
            if task is None:
                continue
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except asyncio.TimeoutError:
                task.cancel()
                try: await task
                except Exception: pass
            except Exception as e:  # noqa
                log.warning("shutdown error for %s: %s", name, e)
        self._conns.clear()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_singleton: Optional[MCPClientManager] = None
_singleton_lock = threading.Lock()


def get_manager() -> MCPClientManager:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = MCPClientManager()
        return _singleton


def reset_manager() -> None:
    """Testing helper — tear down and re-create the singleton."""
    global _singleton
    with _singleton_lock:
        if _singleton is not None:
            _singleton.shutdown()
        _singleton = None
