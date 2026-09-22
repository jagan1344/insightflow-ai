"use client";

import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { CATEGORY_COLORS } from "@/lib/format";

export function CategoryDonut({ data }: { data: { category: string; value: number }[] }) {
  return (
    <Card>
      <CardHeader><div className="text-sm font-medium">Revenue by category</div></CardHeader>
      <CardBody>
        <ResponsiveContainer width="100%" height={240}>
          <PieChart>
            <Tooltip
              contentStyle={{ background: "#0E1E2A", border: "1px solid #1E3A44", borderRadius: 12 }}
              formatter={(v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            />
            <Legend
              iconType="circle"
              wrapperStyle={{ fontSize: 12, color: "#8FA6AE" }}
            />
            <Pie
              data={data}
              dataKey="value"
              nameKey="category"
              innerRadius={55}
              outerRadius={90}
              paddingAngle={2}
              isAnimationActive
              animationDuration={600}
            >
              {data.map((_, i) => (
                <Cell key={i} fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]} stroke="#0B1620" />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </CardBody>
    </Card>
  );
}
