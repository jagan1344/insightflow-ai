"use client";

import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import type { AskResponse } from "@/lib/types";

export function ChartInline({ resp }: { resp: AskResponse }) {
  if (!resp.chart || resp.chart.kind === "none" || !resp.result_rows.length) return null;
  const rows = resp.result_rows.map((r) => {
    const obj: Record<string, string | number | null> = {};
    resp.result_columns.forEach((c, i) => (obj[c] = r[i]));
    return obj;
  });

  const kind = resp.chart.kind;
  const x = resp.chart.x || resp.result_columns[0];
  const y = resp.chart.y || resp.result_columns[resp.result_columns.length - 1];

  if (kind === "metric") {
    const v = rows[0]?.[y];
    return (
      <div className="mt-3 rounded-xl border border-panel-border bg-[#0E1E2A]/60 p-4 text-center">
        <div className="text-xs uppercase tracking-wider text-ink-muted">{y}</div>
        <div className="mt-1 text-3xl font-semibold text-brand-glow tabular-nums">
          {typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(v)}
        </div>
      </div>
    );
  }

  return (
    <div className="mt-3 rounded-xl border border-panel-border bg-[#0E1E2A]/60 p-3">
      <ResponsiveContainer width="100%" height={220}>
        {kind === "line" ? (
          <AreaChart data={rows} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
            <defs>
              <linearGradient id="ilRev" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor="#22D3B7" stopOpacity={0.6} />
                <stop offset="100%" stopColor="#22D3B7" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1E3A44" />
            <XAxis dataKey={x} tick={{ fill: "#8FA6AE", fontSize: 12 }} stroke="#1E3A44" />
            <YAxis tick={{ fill: "#8FA6AE", fontSize: 12 }} stroke="#1E3A44" width={44} />
            <Tooltip contentStyle={{ background: "#0E1E2A", border: "1px solid #1E3A44", borderRadius: 12 }} />
            <Area type="monotone" dataKey={y} stroke="#22D3B7" fill="url(#ilRev)" strokeWidth={2} />
          </AreaChart>
        ) : (
          <BarChart data={rows} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1E3A44" />
            <XAxis dataKey={x} tick={{ fill: "#8FA6AE", fontSize: 12 }} stroke="#1E3A44" />
            <YAxis tick={{ fill: "#8FA6AE", fontSize: 12 }} stroke="#1E3A44" width={44} />
            <Tooltip contentStyle={{ background: "#0E1E2A", border: "1px solid #1E3A44", borderRadius: 12 }} />
            <Bar dataKey={y} fill="#14B8A6" radius={[6, 6, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
