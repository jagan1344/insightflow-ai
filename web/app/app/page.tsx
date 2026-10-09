"use client";

import { useEffect, useState } from "react";
import { PlayCircle, RefreshCw, Square } from "lucide-react";

import { TopBar } from "@/components/shell/TopBar";
import { Button } from "@/components/ui/Button";
import { Dashboard } from "@/components/dashboard/Dashboard";

import { reseed, startSimulate, stopSimulate } from "@/lib/api";
import { useDashboardSocket } from "@/lib/useDashboardSocket";

export default function OverviewPage() {
  const [simulating, setSimulating] = useState(false);
  const [datasetVersion, setDatasetVersion] = useState(0);
  const { data, live, lastUpdateAt, version } = useDashboardSocket();

  useEffect(() => {
    fetch("/api/simulate/status")
      .then((r) => r.json())
      .then((s) => setSimulating(s.detail === "running"))
      .catch(() => {});
  }, []);

  async function toggleSimulate() {
    if (simulating) { await stopSimulate(); setSimulating(false); }
    else { await startSimulate(); setSimulating(true); }
  }
  async function onReseed() { await reseed(); setDatasetVersion(v => v + 1); }

  return (
    <>
      <TopBar
        title="Executive Overview"
        subtitle="Real-time KPIs and dashboards for the active dataset"
        live={live}
        version={version}
      />
      <div className="px-6 py-4 flex items-center gap-2 border-b border-panel-border bg-bg-soft/40">
        <Button variant={simulating ? "danger" : "primary"} onClick={toggleSimulate}>
          {simulating ? <><Square size={14} /> Stop simulation</>
                       : <><PlayCircle size={14} /> Simulate live data</>}
        </Button>
        <Button variant="secondary" onClick={onReseed}>
          <RefreshCw size={14} /> Reseed demo
        </Button>
        {lastUpdateAt && (
          <div className="ml-auto text-xs text-ink-muted">
            last update {new Date(lastUpdateAt).toLocaleTimeString()}
          </div>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-6">
        <Dashboard data={data} key={datasetVersion} />
      </div>
    </>
  );
}
