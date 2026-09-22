"use client";

import { motion } from "framer-motion";
import { Card } from "@/components/ui/Card";
import {
  MessageSquare, Database, Gauge, ShieldQuestion, ScrollText, Activity,
} from "lucide-react";

const FEATURES = [
  {
    icon: MessageSquare,
    title: "Natural-language questions",
    body: "Ask in plain English; the system plans and answers.",
  },
  {
    icon: Database,
    title: "Business- & KPI-aware validation",
    body: "A semantic layer of KPIs, synonyms and business rules.",
  },
  {
    icon: Gauge,
    title: "Multi-signal confidence",
    body: "Seven weighted signals combine into one honest score.",
  },
  {
    icon: ShieldQuestion,
    title: "Answer / Warn / Clarify / Abstain",
    body: "A decision policy — never a fluent guess when unsure.",
  },
  {
    icon: ScrollText,
    title: "Evidence-chain explanations",
    body: "Question → SQL → KPI → filters → rows. Auditable end-to-end.",
  },
  {
    icon: Activity,
    title: "Real-time auto-updating dashboards",
    body: "WebSocket-driven charts that move as data changes — no refresh.",
  },
];

export function Features() {
  return (
    <section id="features" className="relative py-24">
      <div className="mx-auto max-w-6xl px-5">
        <div className="mb-14 text-center">
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Built to be <span className="text-brand-glow">correct</span>, not just fluent.
          </h2>
          <p className="mx-auto mt-3 max-w-2xl text-ink-muted">
            InsightFlow AI treats every answer as a claim that must be defended by evidence.
          </p>
        </div>

        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05, duration: 0.4 }}
              viewport={{ once: true, margin: "-50px" }}
            >
              <Card className="h-full p-5">
                <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-brand-teal/15 text-brand-glow">
                  <f.icon size={20} />
                </div>
                <div className="text-base font-semibold">{f.title}</div>
                <p className="mt-1 text-sm text-ink-muted">{f.body}</p>
              </Card>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
