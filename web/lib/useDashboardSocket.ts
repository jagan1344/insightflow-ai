"use client";

import { useEffect, useRef, useState } from "react";
import type { DashboardPayload, WsMessage } from "./types";

export interface DashboardSocketState {
  data: DashboardPayload | null;
  live: boolean;
  version: number;
  lastUpdateAt: number | null;
}

function wsUrl(): string {
  if (typeof window === "undefined") return "";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
}

export function useDashboardSocket(): DashboardSocketState {
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [live, setLive] = useState(false);
  const [version, setVersion] = useState(0);
  const [lastUpdateAt, setLastUpdateAt] = useState<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);

  useEffect(() => {
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      try {
        const socket = new WebSocket(wsUrl());
        wsRef.current = socket;

        socket.onopen = () => {
          attemptRef.current = 0;
          setLive(true);
        };
        socket.onclose = () => {
          setLive(false);
          const backoff = Math.min(15_000, 1_000 * 2 ** attemptRef.current);
          attemptRef.current += 1;
          setTimeout(connect, backoff);
        };
        socket.onerror = () => {
          socket.close();
        };
        socket.onmessage = (evt) => {
          try {
            const msg: WsMessage = JSON.parse(evt.data);
            if (msg.type === "dashboard_update" && msg.data) {
              setData(msg.data);
              setVersion(msg.version || 0);
              setLastUpdateAt(Date.now());
            }
          } catch {
            /* ignore */
          }
        };
      } catch {
        setTimeout(connect, 2000);
      }
    };

    connect();
    return () => {
      cancelled = true;
      wsRef.current?.close();
    };
  }, []);

  return { data, live, version, lastUpdateAt };
}
