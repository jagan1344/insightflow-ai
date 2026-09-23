"use client";

import { useEffect, useState } from "react";
import { Database, ChevronDown, Check } from "lucide-react";
import clsx from "clsx";
import {
  fetchActiveDataset, fetchDatasets, activateDataset,
  type ActiveDataset, type DatasetSummary,
} from "@/lib/api";

interface Props {
  onChange?: (ds: ActiveDataset) => void;
  refreshKey?: number;
}

export function DatasetPicker({ onChange, refreshKey }: Props) {
  const [active, setActive] = useState<ActiveDataset | null>(null);
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchActiveDataset().then(setActive).catch(() => setActive(null));
    fetchDatasets().then(setDatasets).catch(() => setDatasets([]));
  }, [refreshKey]);

  async function pick(id: string) {
    setBusy(true);
    try {
      await activateDataset(id);
      const ds = await fetchActiveDataset();
      setActive(ds);
      setOpen(false);
      onChange?.(ds);
    } finally {
      setBusy(false);
      fetchDatasets().then(setDatasets).catch(() => {});
    }
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        disabled={busy}
        className={clsx(
          "inline-flex items-center gap-2 rounded-full border border-panel-border",
          "bg-panel/70 px-3 py-1 text-xs hover:bg-panel",
          "text-ink transition-colors",
        )}
        title="Currently-active dataset"
      >
        <Database size={12} className="text-brand-glow" />
        <span className="tabular-nums">
          {active ? active.name : "…"}
        </span>
        <span className="text-ink-muted text-[10px]">
          {active ? `(${active.kind})` : ""}
        </span>
        <ChevronDown size={12} className="text-ink-muted" />
      </button>

      {open && (
        <div className="absolute right-0 top-full z-30 mt-1 w-72 rounded-xl border border-panel-border bg-panel/95 shadow-panel backdrop-blur">
          <div className="px-3 pb-2 pt-3 text-xs uppercase tracking-wider text-ink-muted">
            Switch dataset
          </div>
          <div className="max-h-64 overflow-y-auto">
            {datasets.map((d) => (
              <button
                key={d.id}
                onClick={() => pick(d.id)}
                className={clsx(
                  "flex w-full items-center justify-between px-3 py-2 text-left text-sm",
                  d.is_active ? "text-brand-glow" : "text-ink hover:bg-white/5",
                )}
              >
                <span>
                  <span className="font-medium">{d.name}</span>
                  <span className="ml-2 text-[10px] uppercase tracking-wider text-ink-muted">
                    {d.kind}
                  </span>
                </span>
                {d.is_active && <Check size={14} />}
              </button>
            ))}
            {datasets.length === 0 && (
              <div className="px-3 py-4 text-sm text-ink-muted">
                No datasets registered yet.
              </div>
            )}
          </div>
          {active && (
            <div className="border-t border-panel-border/70 px-3 py-2 text-[11px] text-ink-muted">
              Table: <code className="text-ink">{active.table}</code>
              <div className="mt-1 line-clamp-2">
                Columns:{" "}
                {active.columns.map((c) => c.name).slice(0, 6).join(", ")}
                {active.columns.length > 6 ? "…" : ""}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
