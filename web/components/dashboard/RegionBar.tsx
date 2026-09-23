"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { REGION_COLORS } from "@/lib/format";

export function RegionBar({ data }: { data: { region: string; value: number }[] }) {
  return (
    <Card>
      <CardHeader><div className="text-sm font-medium">Revenue by region</div></CardHeader>
      <CardBody>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={data} margin={{ top: 10, right: 8, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1E3A44" />
            <XAxis dataKey="region" tick={{ fill: "#8FA6AE", fontSize: 12 }} stroke="#1E3A44" />
            <YAxis tick={{ fill: "#8FA6AE", fontSize: 12 }} stroke="#1E3A44" width={44} />
            <Tooltip
              contentStyle={{ background: "#0E1E2A", border: "1px solid #1E3A44", borderRadius: 12 }}
              formatter={(v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            />
            <Bar dataKey="value" radius={[6, 6, 0, 0]} isAnimationActive animationDuration={600}>
              {data.map((_, i) => (
                <Cell key={i} fill={REGION_COLORS[i % REGION_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardBody>
    </Card>
  );
}
