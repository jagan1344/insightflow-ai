"""Realtime watcher, WebSocket broadcaster, and in-process simulator."""
from __future__ import annotations

import asyncio
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Set

from fastapi import WebSocket
from sqlalchemy import text

from insightflow.execution.executor import get_engine


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

@dataclass
class State:
    version: int = 0
    last_signature: tuple = field(default_factory=tuple)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def mark_changed(self):
        with self._lock:
            self.version += 1
            self.last_signature = tuple()


state = State()

_clients: Set[WebSocket] = set()
_clients_lock = asyncio.Lock()
_main_loop: Optional[asyncio.AbstractEventLoop] = None


# ---------------------------------------------------------------------------
# WebSocket registry
# ---------------------------------------------------------------------------

async def register(ws: WebSocket) -> None:
    async with _clients_lock:
        _clients.add(ws)


async def unregister(ws: WebSocket) -> None:
    async with _clients_lock:
        _clients.discard(ws)


async def broadcast(message: dict) -> None:
    dead: list[WebSocket] = []
    async with _clients_lock:
        snapshot = list(_clients)
    for ws in snapshot:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    if dead:
        async with _clients_lock:
            for ws in dead:
                _clients.discard(ws)


# ---------------------------------------------------------------------------
# Signature / change detection
# ---------------------------------------------------------------------------

def compute_signature() -> tuple:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT COUNT(*), COALESCE(MAX(order_id),0), "
                "ROUND(COALESCE(SUM(revenue),0), 2) FROM orders"
            )).fetchone()
        return (int(row[0]), int(row[1]), float(row[2]))
    except Exception:
        return tuple()


# ---------------------------------------------------------------------------
# Watcher task
# ---------------------------------------------------------------------------

async def watcher_loop(poll_seconds: float = 2.0):
    global _main_loop
    _main_loop = asyncio.get_running_loop()

    # prime signature so we don't broadcast a spurious update at startup
    state.last_signature = compute_signature()
    last_heartbeat = 0.0
    from .routes_dashboard import build_dashboard  # local to avoid cycle

    while True:
        try:
            sig = compute_signature()
            if sig != state.last_signature:
                state.last_signature = sig
                state.version += 1
                payload = build_dashboard(version=state.version)
                await broadcast({"type": "dashboard_update", "version": state.version,
                                 "data": payload})
            now = time.time()
            if now - last_heartbeat > 10:
                last_heartbeat = now
                await broadcast({"type": "heartbeat", "version": state.version,
                                 "ts": int(now)})
        except Exception:
            # Never let the watcher die
            pass
        await asyncio.sleep(poll_seconds)


# ---------------------------------------------------------------------------
# In-process simulator (drives realtime for demos)
# ---------------------------------------------------------------------------

class _Simulator:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._rng = random.Random(1234)

    # -- lifecycle --
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, rate_seconds: float = 2.0, batch: int = 3) -> bool:
        if self.is_running():
            return False
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(rate_seconds, batch), daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> bool:
        if not self.is_running():
            return False
        self._stop.set()
        self._thread.join(timeout=3.0)
        self._thread = None
        return True

    # -- worker --
    def _run(self, rate_seconds: float, batch: int) -> None:
        engine = get_engine()
        # cache lookups
        with engine.connect() as conn:
            customer_ids = [r[0] for r in conn.execute(text(
                "SELECT customer_id FROM customers")).fetchall()]
            products = [(r[0], r[1]) for r in conn.execute(text(
                "SELECT product_id, category FROM products")).fetchall()]
            customers = {r[0]: r[1] for r in conn.execute(text(
                "SELECT customer_id, region_id FROM customers")).fetchall()}

        price_bands = {
            "Electronics": (400, 1600, 0.70),
            "Furniture":   (150, 900,  0.65),
            "Office":      (5,   80,   0.55),
            "Software":    (50,  600,  0.35),
        }

        while not self._stop.is_set():
            try:
                rows = []
                for _ in range(batch):
                    cust = self._rng.choice(customer_ids)
                    pid, cat = self._rng.choice(products)
                    region_id = customers[cust]
                    lo, hi, cost_frac = price_bands.get(cat, (10, 100, 0.5))
                    unit_price = self._rng.uniform(lo, hi)
                    qty = self._rng.randint(1, 6)
                    revenue = round(unit_price * qty, 2)
                    cost = round(revenue * cost_frac * self._rng.uniform(0.95, 1.05), 2)
                    discount = round(revenue * self._rng.uniform(0.0, 0.08), 2)
                    # pick a recent date within the current data range
                    order_date = "2026-09-30"  # append to the end of the demo period
                    rows.append((cust, pid, region_id, order_date, qty, revenue, cost, discount))

                with engine.begin() as conn:
                    for row in rows:
                        conn.execute(text(
                            "INSERT INTO orders(customer_id, product_id, region_id, "
                            "order_date, quantity, revenue, cost, discount) "
                            "VALUES (:c,:p,:r,:d,:q,:rev,:cost,:disc)"
                        ), {"c": row[0], "p": row[1], "r": row[2], "d": row[3],
                            "q": row[4], "rev": row[5], "cost": row[6], "disc": row[7]})
            except Exception:
                pass
            # sleep, but wake early on stop
            self._stop.wait(timeout=rate_seconds)


simulator = _Simulator()
