import clsx from "clsx";

export function LiveIndicator({ live, updatedAt }: { live: boolean; updatedAt: number | null }) {
  const secondsAgo = updatedAt ? Math.max(0, Math.round((Date.now() - updatedAt) / 1000)) : null;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs",
        live
          ? "border-state-answer/40 bg-state-answer/10 text-state-answer"
          : "border-panel-border bg-white/5 text-ink-muted",
      )}
    >
      <span
        className={clsx(
          "h-2 w-2 rounded-full",
          live ? "bg-state-answer animate-pulseDot" : "bg-ink-faint",
        )}
      />
      {live ? "Live" : "Offline"}
      {live && secondsAgo !== null && (
        <span className="text-ink-muted/80">· updated {secondsAgo}s ago</span>
      )}
    </span>
  );
}
