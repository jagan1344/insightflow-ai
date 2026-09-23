"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { LayoutDashboard, MessageSquare, PlayCircle, RefreshCw, Square, Upload } from "lucide-react";

import { Logo } from "@/components/ui/Logo";
import { Button } from "@/components/ui/Button";
import { Tabs } from "@/components/ui/Tabs";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { Dashboard } from "@/components/dashboard/Dashboard";
import { LiveIndicator } from "@/components/dashboard/LiveIndicator";
import { UploadDialog } from "@/components/dashboard/UploadDialog";
import { DatasetPicker } from "@/components/dashboard/DatasetPicker";

import { reseed, startSimulate, stopSimulate } from "@/lib/api";
import { useDashboardSocket } from "@/lib/useDashboardSocket";

export default function AppPage() {
  const [tab, setTab] = useState<"chat" | "dashboard">("dashboard");
  const [simulating, setSimulating] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [datasetVersion, setDatasetVersion] = useState(0);
  const { data, live, lastUpdateAt, version } = useDashboardSocket();

  useEffect(() => {
    fetch("/api/simulate/status")
      .then((r) => r.json())
      .then((s) => setSimulating(s.detail === "running"))
      .catch(() => {});
  }, []);

  async function toggleSimulate() {
    if (simulating) {
      await stopSimulate();
      setSimulating(false);
    } else {
      await startSimulate();
      setSimulating(true);
    }
  }

  async function onReseed() {
    await reseed();
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-panel-border/60 bg-[#0B1620]/70 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-5 py-3">
          <Link href="/" aria-label="Home"><Logo /></Link>

          <Tabs
            value={tab}
            onChange={(v) => setTab(v as "chat" | "dashboard")}
            tabs={[
              { key: "dashboard", label: "Live Dashboard", icon: <LayoutDashboard size={14} /> },
              { key: "chat",      label: "Chat",           icon: <MessageSquare size={14} /> },
            ]}
          />

          <div className="flex items-center gap-2">
            <DatasetPicker refreshKey={datasetVersion} />
            <LiveIndicator live={live} updatedAt={lastUpdateAt} />
            <Button
              variant={simulating ? "outline" : "primary"}
              size="sm"
              onClick={toggleSimulate}
            >
              {simulating ? <Square size={14} /> : <PlayCircle size={14} />}
              {simulating ? "Stop simulate" : "Simulate live data"}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setUploadOpen(true)}>
              <Upload size={14} /> Upload data
            </Button>
            <Button variant="ghost" size="sm" onClick={() => {
              onReseed();
              setDatasetVersion((v) => v + 1);
            }}>
              <RefreshCw size={14} /> Reseed
            </Button>
          </div>
        </div>
      </header>

      <UploadDialog
        open={uploadOpen}
        onClose={() => {
          setUploadOpen(false);
          setDatasetVersion((v) => v + 1);
        }}
      />

      <main className="mx-auto w-full max-w-7xl flex-1 px-5 py-6">
        {tab === "dashboard" ? (
          <>
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h1 className="text-xl font-semibold">Live Dashboard</h1>
                <p className="text-sm text-ink-muted">
                  Updates automatically over WebSocket. Click{" "}
                  <span className="text-brand-glow">Simulate live data</span> to see it move.
                </p>
              </div>
              <span className="hidden text-xs text-ink-faint sm:inline">v{version}</span>
            </div>
            <Dashboard data={data} />
          </>
        ) : (
          <div className="h-[calc(100vh-140px)]">
            <ChatPanel />
          </div>
        )}
      </main>
    </div>
  );
}
