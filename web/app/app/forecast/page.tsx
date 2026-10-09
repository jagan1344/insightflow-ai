"use client";

import { useEffect, useState } from "react";
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { TopBar } from "@/components/shell/TopBar";
import { Panel, Pill, EmptyState } from "@/components/shell/Page";
import { Button } from "@/components/ui/Button";
import { fetchExplorerMeta, fetchForecast } from "@/lib/api";
import type { ExplorerMeta, ForecastResponse } from "@/lib/api";

export default function ForecastPage() {
  const [meta, setMeta] = useState<ExplorerMeta | null>(null);
  const [kpi, setKpi] = useState("total_revenue");
  const [horizon, setHorizon] = useState(3);
  const [baseline, setBaseline] = useState("last_value");
  const [data, setData] = useState<ForecastResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { fetchExplorerMeta().then(setMeta).catch(() => {}); }, []);
  useEffect(() => { reload(); /* eslint-disable-next-line */ }, [kpi, horizon, baseline]);

  async function reload() {
    setLoading(true);
    try { setData(await fetchForecast(kpi, horizon, baseline)); }
    catch { setData({ unavailable: true, reason: "request failed" }); }
    finally { setLoading(false); }
  }

  const series = [
    ...(data?.history || []).map(p => ({ period: p.period, actual: p.value, forecast: null as number | null })),
    ...(data?.forecast || []).map(p => ({ period: p.period, actual: null as number | null, forecast: p.value })),
  ];

  return (
    <>
      <TopBar title="Forecasting"
              subtitle="Naive baseline (last-value / mean / trailing-mean). Shows holdout MAE and future points." />
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs text-ink-muted">KPI</label>
          <select value={kpi} onChange={(e) => setKpi(e.target.value)}
            className="bg-bg-soft border border-panel-border rounded-lg px-2 py-1.5 text-sm">
            {(meta?.kpis || []).map(k => <option key={k.id} value={k.id}>{k.name}</option>)}
          </select>
          <label className="text-xs text-ink-muted ml-3">Baseline</label>
          <select value={baseline} onChange={(e) => setBaseline(e.target.value)}
            className="bg-bg-soft border border-panel-border rounded-lg px-2 py-1.5 text-sm">
            <option value="last_value">last_value</option>
            <option value="mean">mean</option>
            <option value="trailing_mean">trailing_mean</option>
          </select>
          <label className="text-xs text-ink-muted ml-3">Horizon</label>
          <input type="number" min="1" max="12" value={horizon}
            onChange={(e) => setHorizon(parseInt(e.target.value, 10) || 3)}
            className="w-20 bg-bg-soft border border-panel-border rounded-lg px-2 py-1.5 text-sm" />
          <Button variant="secondary" onClick={reload}>{loading ? "Loading…" : "Rerun"}</Button>
        </div>

        <Panel title={data?.name ? `${data.name} — history + ${horizon}-step forecast` : "Forecast"}
               right={data?.mae != null ? <Pill>MAE {data.mae.toFixed(2)}</Pill> : undefined}>
          {data?.unavailable ? (
            <EmptyState title="Unavailable" body={data.reason || "Not enough history to forecast."} />
          ) : (
            <div style={{ width: "100%", height: 300 }}>
              <ResponsiveContainer>
                <LineChart data={series}>
                  <CartesianGrid stroke="#1E3A44" strokeDasharray="3 3" />
                  <XAxis dataKey="period" tick={{ fontSize: 12, fill: "#8FA6AE" }} />
                  <YAxis tick={{ fontSize: 12, fill: "#8FA6AE" }} />
                  <Tooltip contentStyle={{ background: "#0E1E2A", border: "1px solid #1E3A44", borderRadius: 10 }} />
                  <Line type="monotone" dataKey="actual" stroke="#22D3B7" strokeWidth={2} dot={{ r: 3 }} connectNulls={false} />
                  <Line type="monotone" dataKey="forecast" stroke="#F97316" strokeWidth={2} strokeDasharray="5 4" dot={{ r: 3 }} connectNulls={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>

        <div className="text-xs text-ink-faint">
          Baseline-only forecast. Use for sanity-check, not operational planning. MAE is on an 80/20 holdout.
        </div>
      </div>
    </>
  );
}
