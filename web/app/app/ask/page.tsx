"use client";

import { TopBar } from "@/components/shell/TopBar";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { useDashboardSocket } from "@/lib/useDashboardSocket";

export default function AskPage() {
  const { live, version } = useDashboardSocket();
  return (
    <>
      <TopBar
        title="Ask AI"
        subtitle="Multi-turn questions grounded in the active dataset — with inspectable evidence."
        live={live}
        version={version}
      />
      <div className="flex-1 overflow-hidden">
        <ChatPanel />
      </div>
    </>
  );
}
