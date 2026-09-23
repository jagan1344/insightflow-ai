"use client";

import { motion } from "framer-motion";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";

const REV = [
  { month: "Jan", value: 385 },
  { month: "Feb", value: 345 },
  { month: "Mar", value: 413 },
  { month: "Apr", value: 402 },
  { month: "May", value: 454 },
  { month: "Jun", value: 455 },
  { month: "Jul", value: 202 },
  { month: "Aug", value: 359 },
  { month: "Sep", value: 372 },
];

const REG = [
  { region: "East", value: 969 },
  { region: "North", value: 856 },
  { region: "South", value: 810 },
  { region: "West", value: 754 },
];

export function DashboardPreview() {
  return (
    <section className="relative border-t border-panel-border/50 py-24">
      <div className="mx-auto max-w-6xl px-5">
        <div className="mb-8 text-center">
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            A dashboard that <span className="text-brand-glow">moves with your data</span>.
          </h2>
          <p className="mx-auto mt-3 max-w-2xl text-ink-muted">
            Charts subscribe to a live WebSocket and animate in place as new orders arrive.
          </p>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          viewport={{ once: true }}
          className="rounded-3xl border border-panel-border bg-panel/70 p-5 shadow-glow backdrop-blur"
        >
          <div className="grid gap-5 lg:grid-cols-2">
            <PreviewCard title="Revenue by month">
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={REV} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                  <defs>
                    <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%"   stopColor="#22D3B7" stopOpacity={0.65} />
                      <stop offset="100%" stopColor="#22D3B7" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1E3A44" />
                  <XAxis dataKey="month" tick={{ fill: "#8FA6AE", fontSize: 12 }} stroke="#1E3A44" />
                  <YAxis tick={{ fill: "#8FA6AE", fontSize: 12 }} stroke="#1E3A44" width={44}/>
                  <Tooltip
                    contentStyle={{ background: "#0E1E2A", border: "1px solid #1E3A44", borderRadius: 12 }}
                    labelStyle={{ color: "#E6EEF0" }}
                  />
                  <Area type="monotone" dataKey="value" stroke="#22D3B7" fill="url(#revGrad)" strokeWidth={2} isAnimationActive />
                </AreaChart>
              </ResponsiveContainer>
            </PreviewCard>

            <PreviewCard title="Revenue by region">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={REG} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1E3A44" />
                  <XAxis dataKey="region" tick={{ fill: "#8FA6AE", fontSize: 12 }} stroke="#1E3A44" />
                  <YAxis tick={{ fill: "#8FA6AE", fontSize: 12 }} stroke="#1E3A44" width={44}/>
                  <Tooltip
                    contentStyle={{ background: "#0E1E2A", border: "1px solid #1E3A44", borderRadius: 12 }}
                    labelStyle={{ color: "#E6EEF0" }}
                  />
                  <Bar dataKey="value" fill="#14B8A6" radius={[6, 6, 0, 0]} isAnimationActive />
                </BarChart>
              </ResponsiveContainer>
            </PreviewCard>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function PreviewCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-panel-border bg-[#0E1E2A]/50 p-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-sm font-medium text-ink">{title}</div>
        <span className="inline-flex items-center gap-1.5 text-xs text-ink-muted">
          <span className="h-2 w-2 rounded-full bg-state-answer animate-pulseDot" /> Live preview
        </span>
      </div>
      {children}
    </div>
  );
}
