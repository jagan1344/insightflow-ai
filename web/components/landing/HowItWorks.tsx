"use client";

import { motion } from "framer-motion";
import { ChevronRight } from "lucide-react";

const STEPS = [
  { k: "Understand",   d: "Parse the question." },
  { k: "Retrieve",     d: "Schema + KPI semantic layer." },
  { k: "Generate SQL", d: "Rule-based or LLM." },
  { k: "Validate",     d: "Read-only, business rules." },
  { k: "Execute",      d: "Row-capped SQL." },
  { k: "Analyse",      d: "Summary + root-cause." },
  { k: "Confidence",   d: "7 weighted signals." },
  { k: "Decide",       d: "Answer / Warn / Clarify / Abstain." },
  { k: "Explain",      d: "Evidence-grounded." },
];

export function HowItWorks() {
  return (
    <section id="how" className="relative py-24 border-t border-panel-border/50">
      <div className="mx-auto max-w-6xl px-5">
        <div className="mb-14 text-center">
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            The pipeline — every step is <span className="text-brand-glow">auditable</span>.
          </h2>
          <p className="mx-auto mt-3 max-w-2xl text-ink-muted">
            No hidden magic. Each stage is inspectable and can refuse.
          </p>
        </div>

        <div className="flex flex-wrap items-stretch justify-center gap-3">
          {STEPS.map((s, i) => (
            <motion.div
              key={s.k}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04, duration: 0.35 }}
              viewport={{ once: true }}
              className="flex items-center gap-2"
            >
              <div className="rounded-xl border border-panel-border bg-panel/60 px-3 py-2">
                <div className="text-xs font-semibold text-brand-glow">
                  {String(i + 1).padStart(2, "0")}
                </div>
                <div className="text-sm font-semibold">{s.k}</div>
                <div className="text-xs text-ink-muted">{s.d}</div>
              </div>
              {i < STEPS.length - 1 && (
                <ChevronRight size={14} className="text-ink-faint" />
              )}
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
