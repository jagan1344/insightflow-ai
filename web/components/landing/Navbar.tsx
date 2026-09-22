"use client";

import Link from "next/link";
import { Github } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { Button } from "@/components/ui/Button";

export function Navbar() {
  return (
    <header className="fixed inset-x-0 top-0 z-40 border-b border-panel-border/60 bg-[#0B1620]/60 backdrop-blur-md">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3">
        <Link href="/" aria-label="Home"><Logo /></Link>
        <div className="hidden md:flex items-center gap-6 text-sm text-ink-muted">
          <a href="#features" className="hover:text-ink">Features</a>
          <a href="#how" className="hover:text-ink">How it works</a>
          <a
            href="https://github.com/jagan1344/insightflow-ai"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 hover:text-ink"
          >
            <Github size={16} /> GitHub
          </a>
        </div>
        <Link href="/app">
          <Button size="sm">Try InsightFlow AI</Button>
        </Link>
      </nav>
    </header>
  );
}
