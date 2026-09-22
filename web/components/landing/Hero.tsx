"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, ShieldCheck, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";

export function Hero() {
  return (
    <section className="relative overflow-hidden pt-40 pb-24">
      <div className="pointer-events-none absolute inset-0 grid-bg opacity-40" aria-hidden />
      <div className="pointer-events-none absolute -top-40 left-1/2 -translate-x-1/2 h-[520px] w-[820px] rounded-full bg-brand-teal/20 blur-3xl" aria-hidden />

      <div className="relative mx-auto max-w-6xl px-5 text-center">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <Badge tone="brand" className="mx-auto">
            <Sparkles size={12} />
            confidence-aware conversational BI
          </Badge>
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05, duration: 0.6 }}
          className="mx-auto mt-6 max-w-4xl text-4xl font-semibold leading-tight tracking-tight text-ink sm:text-6xl"
        >
          Ask your data.{" "}
          <span className="bg-gradient-to-r from-brand-glow via-brand-teal to-sky-400 bg-clip-text text-transparent">
            Get answers you can trust.
          </span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15, duration: 0.6 }}
          className="mx-auto mt-6 max-w-2xl text-lg text-ink-muted"
        >
          A confidence-aware, explainable AI analyst for your business data — it
          validates every query, shows its evidence, and knows when to abstain.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25, duration: 0.6 }}
          className="mt-8 flex flex-wrap items-center justify-center gap-3"
        >
          <Link href="/app">
            <Button size="lg">
              Try InsightFlow AI <ArrowRight size={16} />
            </Button>
          </Link>
          <a href="#how">
            <Button size="lg" variant="outline">
              See how it works
            </Button>
          </a>
        </motion.div>

        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4, duration: 0.6 }}
          className="mt-6 inline-flex items-center gap-2 text-xs text-ink-faint"
        >
          <ShieldCheck size={14} className="text-brand-glow" />
          Runs fully offline — no API key needed for the demo.
        </motion.p>

        <FloatingMock />
      </div>
    </section>
  );
}

function FloatingMock() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.4, duration: 0.7 }}
      className="relative mx-auto mt-16 max-w-4xl"
    >
      <div className="rounded-3xl border border-panel-border bg-panel/70 p-4 shadow-glow backdrop-blur">
        <div className="grid gap-3 sm:grid-cols-3">
          <MockKpi label="Total Revenue" value="$3.4M" delta="-2.1%" />
          <MockKpi label="Orders" value="2,131" delta="+1.4%" tone="up" />
          <MockKpi label="Gross Margin" value="42.0%" delta="+0.3%" tone="up" />
        </div>
        <div className="mt-3 rounded-2xl border border-panel-border/70 bg-[#0E1E2A]/60 p-4">
          <MockChat />
        </div>
      </div>
    </motion.div>
  );
}

function MockKpi({ label, value, delta, tone = "down" }: { label: string; value: string; delta: string; tone?: "up" | "down" }) {
  return (
    <div className="rounded-2xl border border-panel-border bg-[#0E1E2A]/60 p-4 text-left">
      <div className="text-xs text-ink-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
      <div className={`mt-1 inline-block rounded-full px-2 py-0.5 text-xs ${tone === "up" ? "bg-state-answer/10 text-state-answer" : "bg-state-abstain/10 text-state-abstain"}`}>
        {delta} vs last month
      </div>
    </div>
  );
}

function MockChat() {
  return (
    <div className="grid gap-3 sm:grid-cols-[1fr,1fr] items-start">
      <div>
        <div className="text-xs text-ink-muted">You</div>
        <div className="mt-1 rounded-xl border border-panel-border bg-panel px-3 py-2 text-sm">
          Why did revenue decrease in July?
        </div>
      </div>
      <div>
        <div className="flex items-center gap-2 text-xs text-ink-muted">
          <span className="inline-block h-2 w-2 rounded-full bg-state-answer animate-pulseDot" /> InsightFlow
          <span className="ml-auto rounded-full border border-state-answer/40 bg-state-answer/10 px-2 py-0.5 text-state-answer">ANSWER · 0.97</span>
        </div>
        <div className="mt-1 rounded-xl border border-panel-border bg-panel px-3 py-2 text-sm text-ink">
          Revenue fell 55.5% vs June. Largest negative contributors:
          <span className="text-brand-glow"> East −80.6%</span> and
          <span className="text-brand-glow"> Furniture −87.4%</span>.
        </div>
      </div>
    </div>
  );
}
