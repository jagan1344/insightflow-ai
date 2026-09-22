"use client";

import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";

export function RevenueTrend({ data }: { data: { month: string; value: number }[] }) {
  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <div className="text-sm font-medium">Revenue by month</div>
        <span className="text-xs text-ink-muted">2026</span>
      </CardHeader>
      <CardBody>
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={data} margin={{ top: 10, right: 8, left: -10, bottom: 0 }}>
            <defs>
              <linearGradient id="dashRev" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor="#22D3B7" stopOpacity={0.65} />
                <stop offset="100%" stopColor="#22D3B7" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1E3A44" />
            <XAxis dataKey="month" tick={{ fill: "#8FA6AE", fontSize: 12 }} stroke="#1E3A44" />
            <YAxis tick={{ fill: "#8FA6AE", fontSize: 12 }} stroke="#1E3A44" width={44} />
            <Tooltip
              contentStyle={{ background: "#0E1E2A", border: "1px solid #1E3A44", borderRadius: 12 }}
              labelStyle={{ color: "#E6EEF0" }}
              formatter={(v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke="#22D3B7"
              fill="url(#dashRev)"
              strokeWidth={2}
              isAnimationActive
              animationDuration={600}
            />
          </AreaChart>
        </ResponsiveContainer>
      </CardBody>
    </Card>
  );
}
