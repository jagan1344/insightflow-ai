"use client";

import { useEffect, useState } from "react";
import { Download } from "lucide-react";

import { TopBar } from "@/components/shell/TopBar";
import { Panel, Pill } from "@/components/shell/Page";
import { Button } from "@/components/ui/Button";
import { fetchSummaryReport } from "@/lib/api";
import type { SummaryReport } from "@/lib/api";

export default function ReportsPage() {
  const [data, setData] = useState<SummaryReport | null>(null);

  useEffect(() => { fetchSummaryReport("markdown").then(setData).catch(() => {}); }, []);

  function download(ext: "md" | "html") {
    const md = data?.content?.markdown || "";
    const blob = ext === "html"
      ? new Blob([`<html><body><pre>${md.replace(/</g, "&lt;")}</pre></body></html>`], { type: "text/html" })
      : new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `insightflow_summary.${ext}`; a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <TopBar title="Reports"
              subtitle="Executive summary generated from real KPIs. Export as Markdown or HTML." />
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <Panel
          title={data?.content?.title || "Executive summary"}
          subtitle={data?.content?.generated_at ? `generated ${data.content.generated_at}` : ""}
          right={
            <div className="flex gap-2">
              <Pill tone="accent">source: {data?.source || "…"}</Pill>
              <Button variant="secondary" onClick={() => download("md")}>
                <Download size={14} /> .md
              </Button>
              <Button variant="secondary" onClick={() => download("html")}>
                <Download size={14} /> .html
              </Button>
            </div>
          }>
          <pre className="text-xs font-mono whitespace-pre-wrap text-ink">
            {data?.content?.markdown || "Generating report…"}
          </pre>
        </Panel>
      </div>
    </>
  );
}
