"""FastAPI application entry-point."""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import realtime
from .routes_chat import router as chat_router
from .routes_dashboard import router as dashboard_router
from .routes_research import router as research_router
from .routes_upload import router as upload_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(realtime.watcher_loop(poll_seconds=2.0))
    try:
        yield
    finally:
        task.cancel()
        try:
            realtime.simulator.stop()
        except Exception:
            pass


app = FastAPI(
    title="InsightFlow AI",
    version="0.2.0",
    description="Confidence-aware conversational BI backend.",
    lifespan=lifespan,
)

# CORS — allow the Next.js dev origin
_default_origins = "http://localhost:3000,http://127.0.0.1:3000"
_origins = os.environ.get("CORS_ORIGINS", _default_origins).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(dashboard_router)
app.include_router(research_router)
app.include_router(upload_router)


@app.get("/api/health")
def health():
    return {"ok": True, "version": realtime.state.version,
            "connections": len(realtime._clients)}  # type: ignore[attr-defined]


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    await realtime.register(ws)
    # Push initial state on connect
    try:
        from .routes_dashboard import build_dashboard
        payload = build_dashboard(version=realtime.state.version)
        await ws.send_json({"type": "dashboard_update",
                            "version": realtime.state.version,
                            "data": payload})
    except Exception:
        pass
    try:
        while True:
            # We don't expect client messages, but keep the loop alive
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await realtime.unregister(ws)
