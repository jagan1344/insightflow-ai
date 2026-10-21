"use client";

import { useEffect, useState } from "react";
import { Upload, Download } from "lucide-react";

import { TopBar } from "@/components/shell/TopBar";
import { Panel, Pill, EmptyState } from "@/components/shell/Page";
import { Button } from "@/components/ui/Button";
import { UploadDialog } from "@/components/dashboard/UploadDialog";
import { fetchSources, SAMPLE_CSV_URL } from "@/lib/api";
import type { SourcesInfo } from "@/lib/api";

export default function SourcesPage() {
  const [data, setData] = useState<SourcesInfo | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);

  function refresh() {
    fetchSources().then(setData).catch(() => {});
  }
  useEffect(() => { refresh(); }, []);

  return (
    <>
      <TopBar title="Data Sources"
              subtitle="Configured database + registered datasets. No credentials shown." />
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <Panel title="Upload a dataset"
               subtitle="CSV, XLSX, or XLS. Becomes active immediately."
               right={<Pill tone="answer">ready</Pill>}>
          <div className="flex items-center justify-between gap-4">
            <div className="text-sm text-ink-muted">
              Required column: <code>revenue</code>. Optional: <code>order_date</code>,{" "}
              <code>region</code>, <code>category</code>, <code>product</code>,{" "}
              <code>customer</code>, <code>segment</code>, <code>quantity</code>,{" "}
              <code>cost</code>, <code>discount</code>. The Tableau Superstore workbook
              works — the backend maps common column aliases.
            </div>
            <div className="flex gap-2 shrink-0">
              <a href={SAMPLE_CSV_URL}
                 className="inline-flex items-center gap-1.5 text-xs text-ink-muted hover:text-ink">
                <Download size={12} /> Sample CSV
              </a>
              <Button onClick={() => setUploadOpen(true)}>
                <Upload size={14} /> Upload dataset
              </Button>
            </div>
          </div>
        </Panel>

        <Panel title="Database connection"
               right={<Pill tone="answer">connected</Pill>}>
          {!data ? <EmptyState title="Loading…" /> : (
            <dl className="grid grid-cols-2 gap-4 text-sm">
              <div><dt className="text-ink-muted">Dialect</dt><dd className="font-medium">{data.database.dialect}</dd></div>
              <div><dt className="text-ink-muted">Tables</dt><dd className="font-medium">{data.database.table_count}</dd></div>
              <div className="col-span-2">
                <dt className="text-ink-muted mb-1">Visible tables</dt>
                <dd className="flex flex-wrap gap-1">
                  {data.database.tables.map(t => <Pill key={t}>{t}</Pill>)}
                </dd>
              </div>
            </dl>
          )}
        </Panel>

        <Panel title="Registered datasets"
               subtitle={data?.active_dataset ? `active: ${data.active_dataset.name}` : ""}>
          {!data?.datasets?.length ? <EmptyState title="No datasets" /> : (
            <table className="w-full text-xs">
              <thead className="text-ink-muted"><tr>
                <th className="text-left px-3 py-2">Name</th>
                <th className="text-left px-3 py-2">Kind</th>
                <th className="text-left px-3 py-2">Table</th>
                <th className="text-left px-3 py-2">Uploaded</th>
                <th className="text-left px-3 py-2">Active</th>
              </tr></thead>
              <tbody>
                {data.datasets.map(d => (
                  <tr key={d.id} className="border-t border-panel-border">
                    <td className="px-3 py-2">{d.name}</td>
                    <td className="px-3 py-2">{d.kind}</td>
                    <td className="px-3 py-2 font-mono">{d.table}</td>
                    <td className="px-3 py-2 text-ink-muted">{d.uploaded_at || "—"}</td>
                    <td className="px-3 py-2">{d.is_active ? <Pill tone="answer">active</Pill> : <span className="text-ink-faint">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <Panel title="Active dataset shape">
          {!data?.active_dataset ? <EmptyState title="None" /> : (
            <dl className="grid grid-cols-2 gap-4 text-sm">
              <div><dt className="text-ink-muted">Measures</dt><dd className="flex flex-wrap gap-1 mt-1">{data.active_dataset.measures.map(m => <Pill key={m}>{m}</Pill>)}</dd></div>
              <div><dt className="text-ink-muted">Dimensions</dt><dd className="flex flex-wrap gap-1 mt-1">{data.active_dataset.dimensions.map(m => <Pill key={m}>{m}</Pill>)}</dd></div>
              <div><dt className="text-ink-muted">Dates</dt><dd className="flex flex-wrap gap-1 mt-1">{data.active_dataset.dates.map(m => <Pill key={m}>{m}</Pill>)}</dd></div>
            </dl>
          )}
        </Panel>
      </div>

      <UploadDialog open={uploadOpen}
                    onClose={() => setUploadOpen(false)}
                    onSuccess={() => { refresh(); }} />
    </>
  );
}
