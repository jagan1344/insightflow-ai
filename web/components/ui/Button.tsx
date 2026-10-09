import { ButtonHTMLAttributes, forwardRef } from "react";
import clsx from "clsx";

type Variant = "primary" | "ghost" | "outline" | "secondary" | "danger";
type Size = "sm" | "md" | "lg";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export const Button = forwardRef<HTMLButtonElement, Props>(
  ({ variant = "primary", size = "sm", className, children, ...rest }, ref) => {
    const base =
      "inline-flex items-center justify-center gap-2 font-medium rounded-lg transition-all focus:outline-none focus:ring-2 focus:ring-brand-accent/60 disabled:opacity-50 disabled:cursor-not-allowed";
    const variants: Record<Variant, string> = {
      primary:
        "bg-gradient-to-b from-brand-glow to-brand-teal text-[#062024] hover:brightness-110 shadow-[0_10px_30px_-10px_rgba(20,184,166,0.55)]",
      ghost:
        "text-ink hover:bg-white/5",
      outline:
        "border border-panel-border text-ink hover:bg-white/5",
      secondary:
        "border border-panel-border bg-bg-soft/80 text-ink hover:bg-panel/60",
      danger:
        "bg-state-abstain/15 text-state-abstain border border-state-abstain/40 hover:bg-state-abstain/25",
    };
    const sizes: Record<Size, string> = {
      sm: "text-xs px-2.5 py-1.5",
      md: "text-sm px-4 py-2.5",
      lg: "text-base px-5 py-3",
    };
    return (
      <button
        ref={ref}
        className={clsx(base, variants[variant], sizes[size], className)}
        {...rest}
      >
        {children}
      </button>
    );
  },
);
Button.displayName = "Button";
