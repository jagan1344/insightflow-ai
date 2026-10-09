"use client";

import { useEffect, useState } from "react";

import { TopBar } from "@/components/shell/TopBar";
import { Panel, Pill, EmptyState } from "@/components/shell/Page";
import { fetchSemanticModel } from "@/lib/api";
import type { SemanticModelResp } from "@/lib/api";

export default function SemanticPage() {
  const [data, setData] = useState<SemanticModelResp | null>(null);
  useEffect(() => { fetchSemanticModel().then(setData).catch(() => {}); }, []);
  const roleTone: Record<string, "default" | "accent"> = {
    measure: "accent", dimension: "default", date: "default", id: "default",
  };
  return (
    <>
      <TopBar title="Semantic Models"
              subtitle="Business metrics + inferred column semantics for the active dataset." />
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <Panel title="Dataset semantic model"
               right={data ? <Pill>{data.model.n_rows.toLocaleString()} rows · grain: {data.model.grain}</Pill> : undefined}>
          {!data ? <EmptyState title="Loading…" /> : (
            <table className="w-full text-xs">
              <thead className="text-ink-muted"><tr>
                <th className="text-left px-3 py-2">Column</th>
                <th className="text-left px-3 py-2">Role</th>
                <th className="text-left px-3 py-2">SQL type</th>
                <th className="text-right px-3 py-2">Distinct</th>
                <th className="text-right px-3 py-2">Null %</th>
                <th className="text-left px-3 py-2">Flags</th>
              </tr></thead>
              <tbody>
                {data.model.columns.map(c => (
                  <tr key={c.name} className="border-t border-panel-border">
                    <td className="px-3 py-2 font-medium">{c.name}</td>
                    <td className="px-3 py-2"><Pill tone={roleTone[c.role] || "default"}>{c.role}</Pill></td>
                    <td className="px-3 py-2 text-ink-muted">{c.sql_type || "—"}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{c.distinct_count ?? "—"}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{(c.null_pct * 100).toFixed(1)}%</td>
                    <td className="px-3 py-2 text-ink-muted">
                      {c.is_pk_candidate && "PK "}{c.is_fk_candidate && "FK"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <Panel title={`KPI catalog (${data?.kpis.length ?? 0})`}
               subtitle="Derived from the active dataset — formulas are the executor's canonical form.">
          {!data?.kpis.length ? <EmptyState title="No KPIs" /> : (
            <table className="w-full text-xs">
              <thead className="text-ink-muted"><tr>
                <th className="text-left px-3 py-2">ID</th>
                <th className="text-left px-3 py-2">Name</th>
                <th className="text-left px-3 py-2">Aggregation</th>
                <th className="text-left px-3 py-2">Formula</th>
                <th className="text-left px-3 py-2">Unit</th>
                <th className="text-left px-3 py-2">Requires</th>
              </tr></thead>
              <tbody>
                {data.kpis.map(k => (
                  <tr key={k.id} className="border-t border-panel-border">
                    <td className="px-3 py-2 font-mono text-brand-accent-soft">{k.id}</td>
                    <td className="px-3 py-2">{k.name}</td>
                    <td className="px-3 py-2">{k.aggregation}</td>
                    <td className="px-3 py-2 font-mono text-[11px]">{k.formula}</td>
                    <td className="px-3 py-2">{k.unit || "—"}</td>
                    <td className="px-3 py-2 text-ink-muted">{k.required_columns.join(", ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>
    </>
  );
}
