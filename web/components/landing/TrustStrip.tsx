import { CheckCircle2, ShieldCheck, HandHelping } from "lucide-react";

const ITEMS = [
  { icon: <CheckCircle2 size={16} />, text: "Validated SQL" },
  { icon: <ShieldCheck size={16} />,  text: "Evidence-grounded" },
  { icon: <HandHelping size={16} />,  text: "Knows when to abstain" },
];

export function TrustStrip() {
  return (
    <section className="border-y border-panel-border/50 bg-[#0E1E2A]/40">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-center gap-6 px-5 py-6 text-sm text-ink-muted">
        {ITEMS.map((it, i) => (
          <span key={i} className="inline-flex items-center gap-2">
            <span className="text-brand-glow">{it.icon}</span>
            {it.text}
          </span>
        ))}
      </div>
    </section>
  );
}
