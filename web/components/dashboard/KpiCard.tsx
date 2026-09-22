"use client";

import { motion } from "framer-motion";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import type { KpiValue } from "@/lib/types";
import { fmtCurrency, fmtNumber, fmtPct, fmtRatio } from "@/lib/format";

export function KpiCard({
  label, value, previousValue,
}: {
  label: string;
  value: KpiValue;
  previousValue?: number;
}) {
  const changed = previousValue !== undefined && previousValue !== value.value;
  const up = value.delta_pct >= 0;

  const formatted =
    value.unit === "$"     ? fmtCurrency(value.value)
    : value.unit === "ratio" ? fmtRatio(value.value)
    :                          fmtNumber(Math.round(value.value));

  return (
    <motion.div
      layout
      className="rounded-2xl border border-panel-border bg-panel/70 p-5 shadow-panel"
    >
      <div className="text-xs uppercase tracking-wider text-ink-muted">{label}</div>
      <motion.div
        key={value.value}
        initial={changed ? { opacity: 0.4, y: -6 } : false}
        animate={{ opacity: 1, y: 0 }}
        className="mt-1 text-3xl font-semibold tabular-nums"
      >
        {formatted}
      </motion.div>
      <div className={`mt-2 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${up ? "bg-state-answer/10 text-state-answer" : "bg-state-abstain/10 text-state-abstain"}`}>
        {up ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
        {fmtPct(value.delta_pct)}
        <span className="ml-1 text-ink-muted">vs previous month</span>
      </div>
    </motion.div>
  );
}
