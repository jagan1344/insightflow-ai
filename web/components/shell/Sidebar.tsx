"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, MessageSquare, LineChart, AlertTriangle, TrendingUp,
  Lightbulb, FileText, Database, Shapes, Settings as SettingsIcon,
  Compass,
} from "lucide-react";

import { Logo } from "@/components/ui/Logo";

const NAV = [
  { href: "/app",                 label: "Executive Overview", icon: LayoutDashboard },
  { href: "/app/explorer",        label: "Analytics Explorer",  icon: Compass },
  { href: "/app/ask",              label: "Ask AI",              icon: MessageSquare },
  { href: "/app/anomaly",          label: "Anomaly Detection",   icon: AlertTriangle },
  { href: "/app/forecast",         label: "Forecasting",         icon: TrendingUp },
  { href: "/app/recommendations",  label: "Recommendations",     icon: Lightbulb },
  { href: "/app/reports",          label: "Reports",             icon: FileText },
  { href: "/app/sources",          label: "Data Sources",        icon: Database },
  { href: "/app/semantic",         label: "Semantic Models",     icon: Shapes },
  { href: "/app/settings",         label: "Settings",            icon: SettingsIcon },
];

export function Sidebar() {
  const path = usePathname();
  return (
    <aside className="hidden md:flex md:w-56 md:shrink-0 flex-col border-r border-panel-border bg-bg-soft">
      <div className="h-14 flex items-center gap-2 px-4 border-b border-panel-border">
        <Logo size={22} />
        <span className="font-semibold tracking-tight">InsightFlow</span>
      </div>
      <nav className="flex-1 overflow-y-auto py-3">
        {NAV.map((item) => {
          const active = path === item.href
            || (item.href !== "/app" && path?.startsWith(item.href));
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={[
                "flex items-center gap-3 mx-2 my-0.5 rounded-lg px-3 py-2 text-sm transition",
                active
                  ? "bg-brand-accent/10 text-brand-accent-soft border border-brand-accent/30"
                  : "text-ink-muted hover:text-ink hover:bg-panel/60",
              ].join(" ")}
            >
              <Icon size={16} />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="px-4 py-3 border-t border-panel-border text-xs text-ink-faint">
        v0.3 · confidence-aware
      </div>
    </aside>
  );
}
