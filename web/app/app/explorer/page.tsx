"use client";

import { useEffect, useState } from "react";
import { Download, Play } from "lucide-react";

import { TopBar } from "@/components/shell/TopBar";
import { Panel, Pill, EmptyState } from "@/components/shell/Page";
import { Button } from "@/components/ui/Button";
import { askQuestion, fetchExplorerMeta } from "@/lib/api";
import type { AskResponse } from "@/lib/types";
import type { ExplorerMeta } from "@/lib/api";
import { ChartInline } from "@/components/chat/ChartInline";

export default function ExplorerPage() {
  const [meta, setMeta] = useState<ExplorerMeta | null>(null);
  const [q, setQ] = useState("");
  const [running, setRunning] = useState(false);
  const [resp, setResp] = useState<AskResponse | null>(null);

  useEffect(() => { fetchExplorerMeta().then(setMeta).catch(() => {}); }, []);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setRunning(true);
    try { setResp(await askQuestion(q)); }
    finally { setRunning(false); }
  }

  function toCsv(): string {
    if (!resp) return "";
    const rows = [resp.result_columns, ...resp.result_rows.map(r => r.map(c => String(c ?? "")))];
    return rows.map(r => r.map(cell => (/[\n",]/.test(cell) ? `"${cell.replace(/"/g, '""')}"` : cell)).join(",")).join("\n");
  }
  function download() {
    const blob = new Blob([toCsv()], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "explorer_results.csv"; a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <TopBar title="Analytics Explorer"
              subtitle="Browse columns, KPIs and run ad-hoc analytical queries." />
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <div className="grid lg:grid-cols-[2fr_1fr] gap-4">
          <Panel title="Ask a question">
            <form onSubmit={run} className="flex gap-2">
              <input
                className="flex-1 bg-bg-soft border border-panel-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-accent/40"
                placeholder="e.g. revenue by region, top 5 products by profit, …"
                value={q} onChange={(e) => setQ(e.target.value)} />
              <Button type="submit" variant="primary">
                <Play size={14} /> {running ? "Running…" : "Run"}
              </Button>
            </form>
            {meta?.suggested_questions?.length ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {meta.suggested_questions.map(s => (
                  <button key={s}
                    onClick={() => setQ(s)}
                    className="text-xs px-2 py-1 rounded-md bg-panel-border/40 text-ink-muted hover:text-ink">
                    {s}
                  </button>
                ))}
              </div>
            ) : null}
            {resp && (
              <div className="mt-5 space-y-3">
                <div className="flex items-center gap-2">
                  <Pill tone={resp.decision.action === "ANSWER" ? "answer"
                            : resp.decision.action === "WARN" ? "warn"
                            : resp.decision.action === "CLARIFY" ? "clarify"
                            : "abstain"}>
                    {resp.decision.action} · {resp.confidence.score.toFixed(2)}
                  </Pill>
                  {resp.kpi && <Pill tone="accent">KPI: {resp.kpi}</Pill>}
                  <div className="ml-auto">
                    <Button variant="secondary" onClick={download} disabled={!resp.result_rows.length}>
                      <Download size={14} /> CSV
                    </Button>
                  </div>
                </div>
                <div className="text-sm text-ink whitespace-pre-wrap">{resp.explanation}</div>
                <pre className="text-[11px] font-mono bg-bg-soft border border-panel-border rounded-lg p-3 overflow-x-auto">{resp.sql}</pre>
                <ChartInline resp={resp} />
                {resp.result_rows.length > 0 && (
                  <div className="overflow-x-auto border border-panel-border rounded-lg">
                    <table className="w-full text-xs">
                      <thead className="bg-bg-soft text-ink-muted">
                        <tr>{resp.result_columns.map(c => <th key={c} className="px-3 py-2 text-left">{c}</th>)}</tr>
                      </thead>
                      <tbody>
                        {resp.result_rows.slice(0, 50).map((r, i) => (
                          <tr key={i} className="border-t border-panel-border">
                            {r.map((v, j) => <td key={j} className="px-3 py-1.5 tabular-nums">{String(v)}</td>)}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </Panel>
          <Panel title="Dataset schema"
                 subtitle={meta ? `${meta.dataset.name} · ${meta.dataset.kind}` : ""}>
            {!meta ? <EmptyState title="Loading…" /> : (
              <div className="space-y-3 text-xs">
                <div>
                  <div className="text-ink-muted mb-1">Measures</div>
                  <div className="flex flex-wrap gap-1">
                    {meta.measures.length ? meta.measures.map(m => <Pill key={m}>{m}</Pill>) : <span className="text-ink-faint">—</span>}
                  </div>
                </div>
                <div>
                  <div className="text-ink-muted mb-1">Dimensions</div>
                  <div className="flex flex-wrap gap-1">
                    {meta.dimensions.length ? meta.dimensions.map(m => <Pill key={m}>{m}</Pill>) : <span className="text-ink-faint">—</span>}
                  </div>
                </div>
                <div>
                  <div className="text-ink-muted mb-1">Dates</div>
                  <div className="flex flex-wrap gap-1">
                    {meta.dates.length ? meta.dates.map(m => <Pill key={m}>{m}</Pill>) : <span className="text-ink-faint">—</span>}
                  </div>
                </div>
                <div>
                  <div className="text-ink-muted mb-1">KPIs ({meta.kpis.length})</div>
                  <ul className="space-y-1">
                    {meta.kpis.slice(0, 10).map(k => (
                      <li key={k.id} className="truncate">
                        <span className="text-ink">{k.name}</span>
                        <span className="text-ink-faint"> · {k.aggregation}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}
