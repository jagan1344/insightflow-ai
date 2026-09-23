"use client";

import clsx from "clsx";
import { useState } from "react";

export interface Tab {
  key: string;
  label: string;
  icon?: React.ReactNode;
}

export function Tabs({
  tabs,
  value,
  onChange,
  className,
}: {
  tabs: Tab[];
  value: string;
  onChange: (v: string) => void;
  className?: string;
}) {
  return (
    <div
      className={clsx(
        "inline-flex items-center gap-1 rounded-xl border border-panel-border bg-panel/60 p-1",
        className,
      )}
    >
      {tabs.map((t) => {
        const active = t.key === value;
        return (
          <button
            key={t.key}
            onClick={() => onChange(t.key)}
            className={clsx(
              "inline-flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors",
              active
                ? "bg-brand-teal/15 text-brand-glow"
                : "text-ink-muted hover:text-ink",
            )}
          >
            {t.icon}
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

export function useTabs<T extends string>(initial: T) {
  const [value, setValue] = useState<T>(initial);
  return { value, setValue };
}
