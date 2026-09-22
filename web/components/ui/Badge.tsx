import clsx from "clsx";
import { HTMLAttributes } from "react";

type Tone = "neutral" | "answer" | "warn" | "clarify" | "abstain" | "brand";

const TONE: Record<Tone, string> = {
  neutral: "bg-white/5 text-ink border-panel-border",
  brand:   "bg-brand-teal/10 text-brand-glow border-brand-teal/30",
  answer:  "bg-state-answer/10 text-state-answer border-state-answer/30",
  warn:    "bg-state-warn/10 text-state-warn border-state-warn/30",
  clarify: "bg-state-clarify/10 text-state-clarify border-state-clarify/30",
  abstain: "bg-state-abstain/10 text-state-abstain border-state-abstain/30",
};

export function Badge({
  tone = "neutral",
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
        TONE[tone],
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  );
}
