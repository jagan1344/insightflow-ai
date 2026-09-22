import { ButtonHTMLAttributes, forwardRef } from "react";
import clsx from "clsx";

type Variant = "primary" | "ghost" | "outline";
type Size = "sm" | "md" | "lg";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export const Button = forwardRef<HTMLButtonElement, Props>(
  ({ variant = "primary", size = "md", className, children, ...rest }, ref) => {
    const base =
      "inline-flex items-center justify-center gap-2 font-medium rounded-xl transition-all focus:outline-none focus:ring-2 focus:ring-brand-teal/60 disabled:opacity-50 disabled:cursor-not-allowed";
    const variants: Record<Variant, string> = {
      primary:
        "bg-gradient-to-b from-brand-glow to-brand-teal text-[#062024] hover:brightness-110 shadow-[0_10px_30px_-10px_rgba(20,184,166,0.55)]",
      ghost:
        "text-ink hover:bg-white/5",
      outline:
        "border border-panel-border text-ink hover:bg-white/5",
    };
    const sizes: Record<Size, string> = {
      sm: "text-sm px-3 py-1.5",
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
