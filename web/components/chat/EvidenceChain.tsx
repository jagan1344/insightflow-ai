"use client";

import { useState } from "react";
import type { Evidence } from "@/lib/types";
import { ChevronDown } from "lucide-react";
import clsx from "clsx";

export function EvidenceChain({ evidence }: { evidence: Evidence }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-panel-border bg-[#0E1E2A]/50">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-sm text-ink-muted hover:text-ink"
      >
        <span>Evidence chain · {evidence.row_count} row(s)</span>
        <ChevronDown size={16} className={clsx("transition", open && "rotate-180")} />
      </button>
      {open && (
        <div className="grid gap-2 border-t border-panel-border/60 px-4 py-3 text-sm">
          {evidence.chain.map((step, i) => (
            <div key={i}>
              <div className="text-xs uppercase tracking-wider text-brand-glow">{step.step}</div>
              <div className="mt-0.5 whitespace-pre-wrap break-words rounded-md bg-panel/70 p-2 font-mono text-xs text-ink">
                {typeof step.value === "string" ? step.value : JSON.stringify(step.value, null, 2)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
