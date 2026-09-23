"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine,
} from "recharts";

import { Logo } from "@/components/ui/Logo";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

type Metrics = {
  n_questions: number;
  text_to_sql: {
    n: number;
    execution_accuracy: number | null;
    exact_match: number | null;
    sql_validity_rate: number | null;
    schema_matching_accuracy: number | null;
  };
  business: {
    n: number;
    answer_correctness: number | null;
    kpi_matching_accuracy: number | null;
    evidence_support_rate: number | null;
    result_consistency: number | null;
  };
  reliability: {
    avg_confidence: number | null;
    avg_confidence_correct: number | null;
    avg_confidence_incorrect: number | null;
    high_confidence_error_rate: number | null;
    n_high_confidence: number;
  };
  decision: {
    distribution: Record<string, number>;
    distribution_rate: Record<string, number>;
    decision_correctness: number | null;
    answer_precision: number | null;
    unsafe_answer_count: number;
    unsafe_answer_rate: number | null;
  };
  calibration: {
    bins: {
      range: [number, number];
      n: number;
      correct: number;
      incorrect: number;
      accuracy: number | null;
      avg_confidence: number | null;
    }[];
    ece: number | null;
    brier: number | null;
    n_scored: number;
  };
  per_category: Record<string, Record<string, {
    n: number; correct_dec: number; ex_true: number; ex_total: number;
    unsafe: number; decision_correctness: number; execution_accuracy: number | null;
    avg_confidence: number; unsafe_answer_rate: number;
  }>>;
};

type Ablation = {
  configs: Record<string, Record<string, number>>;
  results: Record<string, {
    text_to_sql: { execution_accuracy: number | null };
    business: { answer_correctness: number | null; evidence_support_rate: number | null };
    reliability: { avg_confidence: number | null; high_confidence_error_rate: number | null };
    decision: { decision_correctness: number | null; unsafe_answer_rate: number | null };
    calibration: { ece: number | null; brier: number | null };
  }>;
};

type Payload =
  | { status: "ok"; metrics: Metrics; ablation: Ablation | null }
  | { status: "not_ready"; detail: string; results_dir: string };

const DECISION_TONE: Record<string, string> = {
  ANSWER:  "#22C55E",
  WARN:    "#F59E0B",
  CLARIFY: "#38BDF8",
  ABSTAIN: "#F43F5E",
};

function pct(v: number | null | undefined, digits = 1) {
  if (v === null || v === undefined) return "—";
  return (v * 100).toFixed(digits) + "%";
}
function num(v: number | null | undefined, digits = 3) {
  if (v === null || v === undefined) return "—";
  return v.toFixed(digits);
}

export default function ResearchPage() {
  const [data, setData] = useState<Payload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/research")
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch((e) => setErr(String(e)));
  }, []);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-panel-border/60 bg-[#0B1620]/70 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-3">
          <Link href="/" aria-label="Home"><Logo /></Link>
          <div className="flex items-center gap-3">
            <Badge tone="brand">Research evaluation</Badge>
            <Link href="/app" className="text-sm text-ink-muted hover:text-ink">
              → Open app
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl px-5 py-8">
        <h1 className="text-2xl font-semibold">Research evaluation</h1>
        <p className="mt-2 max-w-3xl text-sm text-ink-muted">
          Live view of the metrics computed in <code>evaluation/results/*.json</code>.
          Every number is measured against the real InsightFlow orchestrator on
          the InsightFlow Reliability Benchmark. Base paper: BIRD (Li et al.,
          NeurIPS 2023) — this dashboard evaluates InsightFlow's{" "}
          <span className="text-brand-glow">reliability-to-decision layer</span>,
          not a BIRD reproduction. See{" "}
          <code>evaluation/reports/alignment.md</code>.
        </p>

        {err && (
          <Card className="mt-6 border-state-abstain/40 bg-state-abstain/10">
            <CardBody>Failed to load: {err}</CardBody>
          </Card>
        )}
        {data && data.status === "not_ready" && (
          <Card className="mt-6 border-state-warn/40 bg-state-warn/10">
            <CardBody>
              <div className="font-medium">Results not built yet.</div>
              <p className="mt-1 text-sm text-ink-muted">{data.detail}</p>
              <pre className="mt-3 whitespace-pre-wrap break-words rounded-md bg-panel/60 p-3 text-xs">
{`python evaluation/scripts/prepare_dataset.py
python evaluation/scripts/run_evaluation.py
python evaluation/scripts/calculate_metrics.py
python evaluation/scripts/run_ablation.py`}
              </pre>
            </CardBody>
          </Card>
        )}

        {data && data.status === "ok" && (
          <ResultsView metrics={data.metrics} ablation={data.ablation} />
        )}
      </main>
    </div>
  );
}

function ResultsView({ metrics, ablation }: { metrics: Metrics; ablation: Ablation | null }) {
  const decDist = Object.entries(metrics.decision.distribution).map(([k, v]) => ({
    action: k, count: v,
  }));
  const calibRows = metrics.calibration.bins.map((b) => ({
    range: `${b.range[0].toFixed(2)}–${b.range[1].toFixed(2)}`,
    accuracy: b.accuracy ?? 0,
    avg_confidence: b.avg_confidence ?? 0,
    n: b.n,
  }));

  return (
    <div className="mt-8 grid gap-6">
      {/* Dataset */}
      <Card>
        <CardHeader><div className="text-sm font-medium">Dataset</div></CardHeader>
        <CardBody className="grid gap-3 md:grid-cols-4">
          <Kpi label="Total questions" value={String(metrics.n_questions)} />
          <Kpi label="Answerable" value={String(metrics.business.n + 2)} sub="incl. 2 diagnostic" />
          <Kpi label="Ambiguous" value="4" />
          <Kpi label="Out-of-scope" value="6" />
        </CardBody>
      </Card>

      {/* Text-to-SQL & business */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><div className="text-sm font-medium">Text-to-SQL (n={metrics.text_to_sql.n})</div></CardHeader>
          <CardBody className="grid gap-3 sm:grid-cols-2">
            <Kpi label="Execution accuracy (EX)" value={pct(metrics.text_to_sql.execution_accuracy)}
                 sub="BIRD-style set equality" tone="answer" />
            <Kpi label="SQL validity rate" value={pct(metrics.text_to_sql.sql_validity_rate)} />
            <Kpi label="Schema match" value={pct(metrics.text_to_sql.schema_matching_accuracy)} />
            <Kpi label="Exact match" value={pct(metrics.text_to_sql.exact_match)} sub="canonicalised text match" />
          </CardBody>
        </Card>
        <Card>
          <CardHeader><div className="text-sm font-medium">Business correctness</div></CardHeader>
          <CardBody className="grid gap-3 sm:grid-cols-2">
            <Kpi label="Answer correctness" value={pct(metrics.business.answer_correctness)} tone="answer" />
            <Kpi label="KPI match" value={pct(metrics.business.kpi_matching_accuracy)} />
            <Kpi label="Evidence support" value={pct(metrics.business.evidence_support_rate)} />
            <Kpi label="Result consistency" value={pct(metrics.business.result_consistency)} />
          </CardBody>
        </Card>
      </div>

      {/* Reliability + decision */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><div className="text-sm font-medium">Reliability</div></CardHeader>
          <CardBody className="grid gap-3 sm:grid-cols-2">
            <Kpi label="Avg confidence" value={num(metrics.reliability.avg_confidence)} />
            <Kpi label="Avg conf | correct" value={num(metrics.reliability.avg_confidence_correct)} tone="answer" />
            <Kpi label="Avg conf | incorrect" value={num(metrics.reliability.avg_confidence_incorrect)} tone="abstain" />
            <Kpi label="High-conf error rate"
                 value={pct(metrics.reliability.high_confidence_error_rate)}
                 sub={`n_high_conf = ${metrics.reliability.n_high_confidence}`}
                 tone="warn" />
            <Kpi label="ECE (lower better)" value={num(metrics.calibration.ece, 4)} />
            <Kpi label="Brier (lower better)" value={num(metrics.calibration.brier, 4)} />
          </CardBody>
        </Card>
        <Card>
          <CardHeader><div className="text-sm font-medium">Decision policy</div></CardHeader>
          <CardBody>
            <div className="grid gap-3 sm:grid-cols-2">
              <Kpi label="Decision correctness" value={pct(metrics.decision.decision_correctness)} tone="answer" />
              <Kpi label="Answer precision" value={pct(metrics.decision.answer_precision)} />
              <Kpi label="Unsafe answer rate" value={pct(metrics.decision.unsafe_answer_rate)}
                   sub={`${metrics.decision.unsafe_answer_count} unsafe`} tone="abstain" />
              <Kpi label="ANSWER share" value={pct(metrics.decision.distribution_rate.ANSWER)} />
            </div>
            <div className="mt-5">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={decDist} margin={{ top: 10, right: 8, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1E3A44" />
                  <XAxis dataKey="action" tick={{ fill: "#8FA6AE", fontSize: 12 }} stroke="#1E3A44" />
                  <YAxis tick={{ fill: "#8FA6AE", fontSize: 12 }} stroke="#1E3A44" width={30} />
                  <Tooltip contentStyle={{ background: "#0E1E2A", border: "1px solid #1E3A44", borderRadius: 12 }} />
                  <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                    {decDist.map((d) => (
                      <Cell key={d.action} fill={DECISION_TONE[d.action] || "#14B8A6"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardBody>
        </Card>
      </div>

      {/* Calibration */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium">
              Confidence calibration (n_scored = {metrics.calibration.n_scored})
            </div>
            <div className="text-xs text-ink-muted">
              perfect = 45° line
            </div>
          </div>
        </CardHeader>
        <CardBody className="grid gap-6 lg:grid-cols-[2fr,3fr] items-start">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-ink-muted">
                  <th className="py-2">Bin</th>
                  <th>n</th>
                  <th>correct</th>
                  <th>accuracy</th>
                  <th>avg_conf</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-panel-border/50">
                {metrics.calibration.bins.map((b, i) => (
                  <tr key={i}>
                    <td className="py-2">
                      {b.range[0].toFixed(2)}–{b.range[1].toFixed(2)}
                    </td>
                    <td>{b.n}</td>
                    <td>{b.correct}</td>
                    <td>{pct(b.accuracy)}</td>
                    <td>{num(b.avg_confidence)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={calibRows} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1E3A44" />
                <XAxis dataKey="avg_confidence" type="number" domain={[0, 1]}
                       tick={{ fill: "#8FA6AE", fontSize: 12 }} stroke="#1E3A44" />
                <YAxis type="number" domain={[0, 1]} tick={{ fill: "#8FA6AE", fontSize: 12 }} stroke="#1E3A44" width={44}/>
                <Tooltip contentStyle={{ background: "#0E1E2A", border: "1px solid #1E3A44", borderRadius: 12 }} />
                <ReferenceLine
                  segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]}
                  stroke="#5F7A83"
                  strokeDasharray="3 3"
                />
                <Line type="monotone" dataKey="accuracy" stroke="#22D3B7" strokeWidth={2} dot={{ r: 6, fill: "#14B8A6" }} isAnimationActive />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardBody>
      </Card>

      {/* Ablation */}
      {ablation && (
        <Card>
          <CardHeader>
            <div className="text-sm font-medium">
              Ablation — SQL-only vs SQL+KPI vs Full InsightFlow
            </div>
          </CardHeader>
          <CardBody>
            <AblationTable ablation={ablation} />
          </CardBody>
        </Card>
      )}
    </div>
  );
}

function Kpi({
  label, value, sub, tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "answer" | "warn" | "clarify" | "abstain";
}) {
  const t: Record<string, string> = {
    answer:  "text-state-answer",
    warn:    "text-state-warn",
    clarify: "text-state-clarify",
    abstain: "text-state-abstain",
  };
  return (
    <div className="rounded-xl border border-panel-border bg-panel/60 p-3">
      <div className="text-[11px] uppercase tracking-wider text-ink-muted">{label}</div>
      <div className={`mt-1 text-xl font-semibold tabular-nums ${tone ? t[tone] : "text-ink"}`}>
        {value}
      </div>
      {sub && <div className="mt-1 text-[11px] text-ink-faint">{sub}</div>}
    </div>
  );
}

function AblationTable({ ablation }: { ablation: Ablation }) {
  const cfgs = Object.keys(ablation.results);
  const rows: [string, (a: Ablation["results"][string]) => number | null][] = [
    ["EX",                         (a) => a.text_to_sql.execution_accuracy],
    ["Business correctness",       (a) => a.business.answer_correctness],
    ["Evidence support",           (a) => a.business.evidence_support_rate],
    ["Decision correctness",       (a) => a.decision.decision_correctness],
    ["Unsafe answer rate",         (a) => a.decision.unsafe_answer_rate],
    ["High-conf error rate",       (a) => a.reliability.high_confidence_error_rate],
    ["Avg confidence",             (a) => a.reliability.avg_confidence],
    ["ECE (↓)",                    (a) => a.calibration.ece],
    ["Brier (↓)",                  (a) => a.calibration.brier],
  ];
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wider text-ink-muted">
            <th className="py-2">Metric</th>
            {cfgs.map((c) => <th key={c}>{c}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-panel-border/50">
          {rows.map(([label, get]) => {
            const values = cfgs.map((c) => get(ablation.results[c]));
            // Find the best per row for row-level highlight
            const numeric = values.filter((v): v is number => typeof v === "number");
            const lowerBetter = label.includes("↓") || label.includes("Unsafe") || label.includes("error");
            const best = numeric.length ? (lowerBetter ? Math.min(...numeric) : Math.max(...numeric)) : null;
            return (
              <tr key={label}>
                <td className="py-2 text-ink-muted">{label}</td>
                {values.map((v, i) => (
                  <td key={i} className={`tabular-nums ${v === best ? "text-brand-glow font-semibold" : ""}`}>
                    {typeof v === "number" ? v.toFixed(4) : "—"}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-3 text-xs text-ink-faint">
        Best value per row highlighted in teal. All three configs share the same
        NL→SQL, execution and decision-thresholding stages — the only thing
        varied is the seven weights that combine reliability signals.
      </p>
    </div>
  );
}
