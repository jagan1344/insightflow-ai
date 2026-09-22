export function Logo({ size = 22 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-2 font-semibold tracking-tight">
      <span
        aria-hidden
        style={{ width: size, height: size }}
        className="rounded-md bg-gradient-to-br from-brand-glow to-brand-deep shadow-glow"
      />
      <span className="text-ink">InsightFlow AI</span>
    </span>
  );
}
