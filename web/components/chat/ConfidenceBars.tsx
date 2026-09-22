"use client";

import { motion } from "framer-motion";

const LABELS: Record<string, string> = {
  sql_validity:        "SQL validity",
  schema_match:        "Schema match",
  kpi_match:           "KPI match",
  context_consistency: "Context consistency",
  data_completeness:   "Data completeness",
  evidence_strength:   "Evidence strength",
  result_consistency:  "Result consistency",
};

export function ConfidenceBars({ signals }: { signals: Record<string, number> }) {
  const entries = Object.entries(signals);
  return (
    <div className="grid gap-2">
      {entries.map(([k, v]) => (
        <div key={k}>
          <div className="mb-1 flex items-center justify-between text-xs">
            <span className="text-ink-muted">{LABELS[k] ?? k}</span>
            <span className="tabular-nums text-ink">{v.toFixed(2)}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-white/5">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${Math.max(0, Math.min(1, v)) * 100}%` }}
              transition={{ duration: 0.6, ease: "easeOut" }}
              className="h-full rounded-full bg-gradient-to-r from-brand-teal to-brand-glow"
            />
          </div>
        </div>
      ))}
    </div>
  );
}
