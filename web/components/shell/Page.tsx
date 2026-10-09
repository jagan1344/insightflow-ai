"use client";

import { ReactNode } from "react";

export function Panel({ title, subtitle, children, right }: {
  title?: string; subtitle?: string;
  children: ReactNode; right?: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-panel-border bg-panel/60 shadow-panel">
      {(title || subtitle || right) && (
        <header className="flex items-start justify-between gap-3 px-5 py-4 border-b border-panel-border">
          <div className="min-w-0">
            {title && <h3 className="text-sm font-semibold text-ink truncate">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-muted truncate">{subtitle}</p>}
          </div>
          {right}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function EmptyState({ title, body }: { title: string; body?: string }) {
  return (
    <div className="text-center py-14 px-6">
      <div className="mx-auto h-10 w-10 rounded-full bg-panel-border/50 flex items-center justify-center text-ink-muted">—</div>
      <div className="mt-3 text-sm font-medium text-ink">{title}</div>
      {body && <div className="mt-1 text-xs text-ink-muted max-w-sm mx-auto">{body}</div>}
    </div>
  );
}

export function Pill({ children, tone = "default" }: {
  children: ReactNode;
  tone?: "default" | "answer" | "warn" | "clarify" | "abstain" | "accent";
}) {
  const toneMap: Record<string, string> = {
    default: "bg-panel-border/40 text-ink-muted",
    answer:  "bg-state-answer/15 text-state-answer",
    warn:    "bg-state-warn/15 text-state-warn",
    clarify: "bg-state-clarify/15 text-state-clarify",
    abstain: "bg-state-abstain/15 text-state-abstain",
    accent:  "bg-brand-accent/15 text-brand-accent-soft",
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium ${toneMap[tone]}`}>
      {children}
    </span>
  );
}
