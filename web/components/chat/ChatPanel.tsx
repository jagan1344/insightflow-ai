"use client";

import { useEffect, useRef, useState } from "react";
import { Send, Loader2 } from "lucide-react";
import { askQuestion } from "@/lib/api";
import type { AskResponse } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { AssistantMessage, UserMessage } from "./Message";

const SUGGESTIONS = [
  "What is the total revenue?",
  "Why did revenue decrease in July?",
  "Gross margin by category",
  "Top products by revenue",
  "Show revenue by month",
];

interface Turn {
  question: string;
  resp?: AskResponse;
  error?: string;
}

export function ChatPanel() {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [turns.length, busy]);

  async function ask(q: string) {
    const question = q.trim();
    if (!question || busy) return;
    setInput("");
    setBusy(true);
    setTurns((prev) => [...prev, { question }]);
    try {
      const resp = await askQuestion(question);
      setTurns((prev) => {
        const copy = prev.slice();
        copy[copy.length - 1] = { question, resp };
        return copy;
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Something went wrong";
      setTurns((prev) => {
        const copy = prev.slice();
        copy[copy.length - 1] = { question, error: msg };
        return copy;
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div ref={scroller} className="flex-1 overflow-y-auto px-1 py-4">
        {turns.length === 0 ? (
          <EmptyState onPick={ask} />
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col gap-5">
            {turns.map((t, i) => (
              <div key={i} className="grid gap-4">
                <UserMessage text={t.question} />
                {t.resp ? (
                  <AssistantMessage resp={t.resp} />
                ) : t.error ? (
                  <div className="rounded-2xl border border-state-abstain/30 bg-state-abstain/10 p-3 text-sm text-state-abstain">
                    {t.error}
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-sm text-ink-muted">
                    <Loader2 size={14} className="animate-spin" /> Thinking…
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="border-t border-panel-border/60 bg-[#0B1620]/60 p-3 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                ask(input);
              }
            }}
            rows={1}
            placeholder="Ask about revenue, orders, margin — try “Why did revenue decrease in July?”"
            className="min-h-[44px] max-h-[160px] flex-1 resize-y rounded-xl border border-panel-border bg-panel/80 px-3 py-2.5 text-sm outline-none focus:border-brand-teal/60"
          />
          <Button onClick={() => ask(input)} disabled={busy}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            Ask
          </Button>
        </div>
      </div>
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-4 pt-10 text-center">
      <div className="rounded-full border border-brand-teal/30 bg-brand-teal/10 px-3 py-1 text-xs text-brand-glow">
        Ready when you are
      </div>
      <h2 className="mt-4 text-2xl font-semibold tracking-tight">
        Ask a business question — get an evidence-backed answer.
      </h2>
      <p className="mt-2 text-sm text-ink-muted">
        Every answer shows its confidence, decision and evidence chain.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => onPick(s)}
            className="rounded-full border border-panel-border bg-panel/60 px-3 py-1.5 text-sm text-ink-muted hover:bg-panel hover:text-ink"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
