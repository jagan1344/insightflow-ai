import { Logo } from "@/components/ui/Logo";

export function Footer() {
  return (
    <footer className="border-t border-panel-border/60 py-12">
      <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-6 px-5 sm:flex-row sm:items-center">
        <div>
          <Logo />
          <p className="mt-2 max-w-md text-sm text-ink-muted">
            A confidence-aware AI analyst that shows its work.
          </p>
        </div>
        <div className="flex flex-wrap gap-6 text-sm text-ink-muted">
          <a href="#features" className="hover:text-ink">Features</a>
          <a href="#how" className="hover:text-ink">How it works</a>
          <a
            href="https://github.com/jagan1344/insightflow-ai"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-ink"
          >
            GitHub
          </a>
        </div>
      </div>
      <div className="mx-auto mt-8 max-w-6xl px-5 text-xs text-ink-faint">
        Built for BCSE497J Project-I · © {new Date().getFullYear()} InsightFlow AI
      </div>
    </footer>
  );
}
