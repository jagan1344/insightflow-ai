"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";

export function MarginBar({ data }: { data: { category: string; value: number }[] }) {
  const rows = data.map((d) => ({ category: d.category, value: +(d.value * 100).toFixed(1) }));
  return (
    <Card>
      <CardHeader><div className="text-sm font-medium">Gross margin by category</div></CardHeader>
      <CardBody>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={rows} margin={{ top: 10, right: 8, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1E3A44" />
            <XAxis dataKey="category" tick={{ fill: "#8FA6AE", fontSize: 12 }} stroke="#1E3A44" />
            <YAxis
              tick={{ fill: "#8FA6AE", fontSize: 12 }}
              stroke="#1E3A44"
              width={44}
              tickFormatter={(v) => `${v}%`}
            />
            <Tooltip
              contentStyle={{ background: "#0E1E2A", border: "1px solid #1E3A44", borderRadius: 12 }}
              formatter={(v: number) => `${v.toFixed(1)}%`}
            />
            <Bar dataKey="value" fill="#38BDF8" radius={[6, 6, 0, 0]} isAnimationActive animationDuration={600} />
          </BarChart>
        </ResponsiveContainer>
      </CardBody>
    </Card>
  );
}
