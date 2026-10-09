"use client";

import { useEffect, useState } from "react";

import { TopBar } from "@/components/shell/TopBar";
import { Panel, Pill, EmptyState } from "@/components/shell/Page";
import { Button } from "@/components/ui/Button";
import {
  connectMCPServers, fetchMCPServers, fetchSettings,
} from "@/lib/api";
import type { MCPServerStatus, SettingsInfo } from "@/lib/api";

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsInfo | null>(null);
  const [mcp, setMcp] = useState<MCPServerStatus[]>([]);
  const [connecting, setConnecting] = useState(false);

  useEffect(() => { reload(); }, []);
  async function reload() {
    try { setSettings(await fetchSettings()); } catch { /* */ }
    try { setMcp(await fetchMCPServers()); } catch { setMcp([]); }
  }
  async function connectAll() {
    setConnecting(true);
    try { await connectMCPServers(); } finally { setConnecting(false); }
    await reload();
  }

  return (
    <>
      <TopBar title="Settings"
              subtitle="Runtime + MCP server status. No secrets shown." />
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <Panel title="Runtime">
          {!settings ? <EmptyState title="Loading…" /> : (
            <dl className="grid grid-cols-2 gap-4 text-sm">
              <div><dt className="text-ink-muted">Python</dt><dd>{settings.python_version}</dd></div>
              <div><dt className="text-ink-muted">DATABASE_URL set</dt><dd>{settings.database_url_configured ? "yes" : "default"}</dd></div>
              <div><dt className="text-ink-muted">LLM provider</dt><dd>{settings.llm_provider}</dd></div>
              <div><dt className="text-ink-muted">CORS origins</dt><dd className="font-mono text-xs">{settings.cors_origins || "default"}</dd></div>
            </dl>
          )}
        </Panel>

        <Panel title="MCP servers"
               subtitle="Click 'Connect all' to spawn stdio servers (first use may take ~1s each)."
               right={<Button variant="primary" onClick={connectAll}>{connecting ? "Connecting…" : "Connect all"}</Button>}>
          {!mcp.length ? <EmptyState title="No MCP servers configured" body="Add entries to backend/mcp_config.yaml." /> : (
            <table className="w-full text-xs">
              <thead className="text-ink-muted"><tr>
                <th className="text-left px-3 py-2">Name</th>
                <th className="text-left px-3 py-2">Transport</th>
                <th className="text-left px-3 py-2">Status</th>
                <th className="text-right px-3 py-2">Tools</th>
                <th className="text-left px-3 py-2">Allowed</th>
              </tr></thead>
              <tbody>
                {mcp.map(s => (
                  <tr key={s.name} className="border-t border-panel-border">
                    <td className="px-3 py-2 font-mono">{s.name}</td>
                    <td className="px-3 py-2">{s.transport}</td>
                    <td className="px-3 py-2">
                      {s.connected ? <Pill tone="answer">connected</Pill>
                                   : s.enabled ? <Pill tone="warn">idle</Pill>
                                   : <Pill tone="abstain">disabled</Pill>}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{s.tool_count}</td>
                    <td className="px-3 py-2 text-ink-muted">{(s.allowed_tools || []).slice(0, 4).join(", ") || "(all)"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <Panel title="Confidence policy">
          {!settings ? <EmptyState title="Loading…" /> : (
            <div className="space-y-3 text-sm">
              <div className="flex gap-4">
                <div><span className="text-ink-muted">ANSWER ≥</span> {settings.confidence_thresholds.threshold_high}</div>
                <div><span className="text-ink-muted">WARN ≥</span> {settings.confidence_thresholds.threshold_low}</div>
              </div>
              <div>
                <div className="text-ink-muted mb-1">Signal weights</div>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-1 text-xs">
                  {Object.entries(settings.confidence_weights).map(([k, v]) => (
                    <div key={k} className="flex justify-between">
                      <span>{k}</span><span className="tabular-nums text-ink-muted">{(v as number).toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}
