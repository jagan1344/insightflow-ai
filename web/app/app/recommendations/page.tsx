"use client";

import { useEffect, useState } from "react";

import { TopBar } from "@/components/shell/TopBar";
import { Panel, Pill, EmptyState } from "@/components/shell/Page";
import { fetchRecommendations } from "@/lib/api";
import type { Recommendation } from "@/lib/api";

export default function RecommendationsPage() {
  const [items, setItems] = useState<Recommendation[]>([]);
  const [note, setNote] = useState<string | undefined>();
  useEffect(() => {
    fetchRecommendations()
      .then(r => { setItems(r.recommendations || []); setNote(r.note); })
      .catch(() => setNote("request failed"));
  }, []);
  return (
    <>
      <TopBar title="Recommendations"
              subtitle="Observations drawn from the data — never fabricated." />
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {items.length === 0 ? (
          <Panel title="No recommendations">
            <EmptyState title="Nothing surfaced right now" body={note || "The current dataset doesn't trigger any built-in rules."} />
          </Panel>
        ) : items.map((r, i) => (
          <Panel key={i} title={r.observation}
                 right={<Pill tone="accent">evidence attached</Pill>}>
            <div className="space-y-2 text-sm">
              <div><span className="text-ink-muted">Metric:</span> {r.metric}</div>
              <div><span className="text-ink-muted">Value:</span> {typeof r.value === "object" ? JSON.stringify(r.value) : String(r.value)}</div>
              <div><span className="text-ink-muted">Suggested action:</span> {r.suggested_action}</div>
              <div className="text-xs text-ink-faint">
                <span className="font-medium">Limitations:</span> {r.limitations}
              </div>
              <details>
                <summary className="text-xs text-ink-muted cursor-pointer">Evidence SQL</summary>
                <pre className="mt-2 text-[11px] font-mono bg-bg-soft border border-panel-border rounded-lg p-3 overflow-x-auto">{r.evidence_sql}</pre>
              </details>
            </div>
          </Panel>
        ))}
      </div>
    </>
  );
}
