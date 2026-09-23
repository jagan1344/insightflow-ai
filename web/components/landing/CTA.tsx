import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/Button";

export function CTA() {
  return (
    <section className="relative py-24">
      <div className="mx-auto max-w-4xl px-5">
        <div className="relative overflow-hidden rounded-3xl border border-panel-border bg-gradient-to-br from-brand-teal/15 via-panel/60 to-sky-500/10 p-10 text-center shadow-glow">
          <div className="pointer-events-none absolute inset-0 grid-bg opacity-30" aria-hidden />
          <h2 className="relative text-3xl font-semibold tracking-tight sm:text-4xl">
            See what your data has been trying to tell you.
          </h2>
          <p className="relative mx-auto mt-3 max-w-xl text-ink-muted">
            Try the chat and watch the live dashboard update as new orders arrive.
          </p>
          <div className="relative mt-8 flex justify-center">
            <Link href="/app">
              <Button size="lg">
                Try InsightFlow AI <ArrowRight size={16} />
              </Button>
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
