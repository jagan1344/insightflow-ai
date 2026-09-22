"use client";

import type { DashboardPayload } from "@/lib/types";
import { Skeleton } from "@/components/ui/Skeleton";
import { KpiCard } from "./KpiCard";
import { RevenueTrend } from "./RevenueTrend";
import { RegionBar } from "./RegionBar";
import { CategoryDonut } from "./CategoryDonut";
import { MarginBar } from "./MarginBar";

export function Dashboard({ data }: { data: DashboardPayload | null }) {
  if (!data) {
    return (
      <div className="grid gap-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-72" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Total Revenue"    value={data.kpis.total_revenue} />
        <KpiCard label="Orders"           value={data.kpis.order_count} />
        <KpiCard label="Avg Order Value"  value={data.kpis.avg_order_value} />
        <KpiCard label="Gross Margin"     value={data.kpis.gross_margin} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <RevenueTrend    data={data.revenue_by_month} />
        <RegionBar       data={data.revenue_by_region} />
        <CategoryDonut   data={data.revenue_by_category} />
        <MarginBar       data={data.margin_by_category} />
      </div>
    </div>
  );
}
