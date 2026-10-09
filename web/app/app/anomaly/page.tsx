"use client";

import { useEffect, useState } from "react";
import {
  CartesianGrid, Line, LineChart, ReferenceDot, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";

import { TopBar } from "@/components/shell/TopBar";
import { Panel, Pill, EmptyState } from "@/components/shell/Page";
import { Button } from "@/components/ui/Button";
import { fetchAnomalies, fetchExplorerMeta } from "@/lib/api";
import type { AnomalyResponse, ExplorerMeta } from "@/lib/api";

export default function AnomalyPage() {
  const [meta, setMeta] = useState<ExplorerMeta | null>(null);
  const [kpi, setKpi] = useState("total_revenue");
  const [threshold, setThreshold] = useState(2.0);
  const [data, setData] = useState<AnomalyResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { fetchExplorerMeta().then(setMeta).catch(() => {}); }, []);
  useEffect(() => { reload(); /* eslint-disable-next-line */ }, [kpi, threshold]);

  async function reload() {
    setLoading(true);
    try { setData(await fetchAnomalies(kpi, threshold)); }
    catch { setData({ unavailable: true, reason: "request failed" }); }
    finally { setLoading(false); }
  }

  const series = data?.series || [];
  const anomaliesByPeriod = new Map((data?.anomalies || []).map(a => [a.period, a]));

  return (
    <>
      <TopBar title="Anomaly Detection"
              subtitle="Z-score detector on the active dataset's monthly series. Threshold tunable." />
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs text-ink-muted">KPI</label>
          <select value={kpi} onChange={(e) => setKpi(e.target.value)}
            className="bg-bg-soft border border-panel-border rounded-lg px-2 py-1.5 text-sm">
            {(meta?.kpis || []).map(k => (
              <option key={k.id} value={k.id}>{k.name}</option>
            ))}
          </select>
          <label className="text-xs text-ink-muted ml-3">|z| ≥</label>
          <input type="number" step="0.1" min="1" max="5" value={threshold}
            onChange={(e) => setThreshold(parseFloat(e.target.value) || 2)}
            className="w-20 bg-bg-soft border border-panel-border rounded-lg px-2 py-1.5 text-sm" />
          <Button variant="secondary" onClick={reload}>{loading ? "Loading…" : "Rerun"}</Button>
        </div>

        <Panel title={data?.name ? `${data.name} — monthly` : "Series"}
               subtitle={data?.mean != null ? `mean ${data.mean?.toLocaleString()} · stdev ${data.stdev?.toLocaleString()}` : undefined}>
          {data?.unavailable ? (
            <EmptyState title="Unavailable" body={data.reason || "This KPI can't be analysed on the active dataset."} />
          ) : series.length < 2 ? (
            <EmptyState title="Not enough history" body={data?.note || "Need at least a few monthly points."} />
          ) : (
            <div style={{ width: "100%", height: 280 }}>
              <ResponsiveContainer>
                <LineChart data={series}>
                  <CartesianGrid stroke="#1E3A44" strokeDasharray="3 3" />
                  <XAxis dataKey="period" tick={{ fontSize: 12, fill: "#8FA6AE" }} />
                  <YAxis tick={{ fontSize: 12, fill: "#8FA6AE" }} />
                  <Tooltip contentStyle={{ background: "#0E1E2A", border: "1px solid #1E3A44", borderRadius: 10 }} />
                  <Line type="monotone" dataKey="value" stroke="#22D3B7" strokeWidth={2} dot={{ r: 3 }} />
                  {(data?.anomalies || []).map(a => (
                    <ReferenceDot key={a.period} x={a.period} y={a.value}
                                   r={6}
                                   fill={a.severity === "high" ? "#F43F5E" : "#F59E0B"}
                                   stroke="none" />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>

        <Panel title={`Flagged periods (${(data?.anomalies || []).length})`}
               subtitle="z-score outside the configured threshold">
          {!data?.anomalies || data.anomalies.length === 0 ? (
            <EmptyState title="No anomalies at this threshold" />
          ) : (
            <table className="w-full text-xs">
              <thead className="text-ink-muted">
                <tr>
                  <th className="text-left px-3 py-2">Period</th>
                  <th className="text-right px-3 py-2">Value</th>
                  <th className="text-right px-3 py-2">Expected</th>
                  <th className="text-right px-3 py-2">Δ</th>
                  <th className="text-right px-3 py-2">z-score</th>
                  <th className="text-left px-3 py-2">Severity</th>
                </tr>
              </thead>
              <tbody>
                {data.anomalies.map(a => (
                  <tr key={a.period} className="border-t border-panel-border">
                    <td className="px-3 py-2">{a.period}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{a.value.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{a.expected.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{a.deviation > 0 ? "+" : ""}{a.deviation.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{a.z_score.toFixed(2)}</td>
                    <td className="px-3 py-2"><Pill tone={a.severity === "high" ? "abstain" : "warn"}>{a.severity}</Pill></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <div className="text-xs text-ink-faint">
          Method: z-score ((value − mean) / stdev). This is a statistical score, not a calibrated probability.
        </div>
      </div>
    </>
  );
}
