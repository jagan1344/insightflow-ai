"use client";

import { motion } from "framer-motion";
import { Lightbulb, User, Sparkles } from "lucide-react";
import type { AskResponse } from "@/lib/types";
import { DecisionBadge } from "./DecisionBadge";
import { ConfidenceBars } from "./ConfidenceBars";
import { EvidenceChain } from "./EvidenceChain";
import { ChartInline } from "./ChartInline";

export function UserMessage({ text }: { text: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex justify-end"
    >
      <div className="flex max-w-[75%] items-start gap-2">
        <div className="rounded-2xl rounded-tr-sm bg-brand-teal/15 border border-brand-teal/25 px-4 py-2.5 text-sm">
          {text}
        </div>
        <div className="mt-1 rounded-full bg-white/5 p-1.5 text-ink-muted">
          <User size={14} />
        </div>
      </div>
    </motion.div>
  );
}

export function AssistantMessage({ resp }: { resp: AskResponse }) {
  const answered = resp.decision.action === "ANSWER" || resp.decision.action === "WARN";
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-start gap-2"
    >
      <div className="mt-1 rounded-full bg-brand-teal/15 p-1.5 text-brand-glow">
        <Sparkles size={14} />
      </div>
      <div className="w-full max-w-[92%] rounded-2xl rounded-tl-sm border border-panel-border bg-panel/80 p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <DecisionBadge action={resp.decision.action} score={resp.confidence.score} />
          {resp.kpi && (
            <span className="text-xs text-ink-muted">KPI: <span className="text-ink">{resp.kpi}</span></span>
          )}
        </div>

        <div className="mb-3 text-xs text-ink-muted">{resp.decision.reason}</div>

        <details className="mb-3 rounded-xl border border-panel-border/70 bg-[#0E1E2A]/50">
          <summary className="cursor-pointer select-none px-3 py-2 text-xs text-ink-muted hover:text-ink">
            Confidence signals
          </summary>
          <div className="px-3 pb-3">
            <ConfidenceBars signals={resp.confidence.signals} />
          </div>
        </details>

        {answered ? (
          <div className="text-sm leading-relaxed text-ink whitespace-pre-wrap">
            {resp.explanation || resp.answer}
          </div>
        ) : (
          <div className="rounded-xl border border-state-clarify/30 bg-state-clarify/5 px-3 py-2 text-sm text-ink">
            {resp.explanation}
          </div>
        )}

        {answered && <ChartInline resp={resp} />}

        {resp.recommendation && (
          <div className="mt-3 flex items-start gap-2 rounded-xl border border-brand-teal/30 bg-brand-teal/10 px-3 py-2 text-sm">
            <Lightbulb size={16} className="mt-0.5 text-brand-glow" />
            <span>{resp.recommendation}</span>
          </div>
        )}

        {resp.sql && (
          <details className="mt-3 rounded-xl border border-panel-border/70 bg-[#0E1E2A]/50">
            <summary className="cursor-pointer select-none px-3 py-2 text-xs text-ink-muted hover:text-ink">
              SQL
            </summary>
            <pre className="overflow-x-auto whitespace-pre-wrap break-words px-3 pb-3 font-mono text-xs text-ink">
              {resp.sql}
            </pre>
          </details>
        )}

        <div className="mt-3">
          <EvidenceChain evidence={resp.evidence} />
        </div>
      </div>
    </motion.div>
  );
}
