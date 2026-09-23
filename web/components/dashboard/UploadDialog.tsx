"use client";

import { useRef, useState } from "react";
import { Upload, X, Loader2, CheckCircle2, AlertTriangle, Download } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { uploadOrdersCsv, SAMPLE_CSV_URL, type UploadResult } from "@/lib/api";

interface Props {
  open: boolean;
  onClose: () => void;
  onSuccess?: (r: UploadResult) => void;
}

export function UploadDialog({ open, onClose, onSuccess }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<"replace" | "append">("replace");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  if (!open) return null;

  async function submit() {
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await uploadOrdersCsv(file, mode);
      setResult(r);
      onSuccess?.(r);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setFile(null);
    setResult(null);
    setError(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[#03080B]/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative mx-4 w-full max-w-lg rounded-2xl border border-panel-border bg-panel/95 p-5 shadow-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute right-3 top-3 rounded-full p-1 text-ink-muted hover:bg-white/5 hover:text-ink"
          aria-label="Close"
        >
          <X size={16} />
        </button>

        <div className="mb-4 flex items-start gap-3">
          <div className="rounded-xl bg-brand-teal/15 p-2 text-brand-glow">
            <Upload size={18} />
          </div>
          <div>
            <h2 className="text-lg font-semibold">Upload your dataset</h2>
            <p className="mt-1 text-sm text-ink-muted">
              CSV with columns like <code>order_date, region, category, product,
              customer, segment, quantity, revenue, cost, discount</code>. Only
              <code className="mx-1">revenue</code>is required.
            </p>
          </div>
        </div>

        {!result && (
          <>
            <label
              className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-6 text-center ${
                file ? "border-brand-teal/60 bg-brand-teal/5" : "border-panel-border bg-[#0E1E2A]/40 hover:bg-white/5"
              }`}
            >
              <input
                ref={inputRef}
                type="file"
                accept=".csv,text/csv"
                className="sr-only"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
              {file ? (
                <>
                  <span className="text-sm font-medium">{file.name}</span>
                  <span className="text-xs text-ink-muted">
                    {(file.size / 1024).toFixed(1)} KB — click to change
                  </span>
                </>
              ) : (
                <>
                  <Upload size={22} className="text-ink-muted" />
                  <span className="text-sm">Click to choose a .csv file</span>
                  <span className="text-xs text-ink-faint">Up to 5 MB · 50k rows</span>
                </>
              )}
            </label>

            <fieldset className="mt-4">
              <legend className="mb-2 text-xs uppercase tracking-wider text-ink-muted">
                Load mode
              </legend>
              <div className="flex gap-2">
                <ModeChip
                  active={mode === "replace"}
                  label="Replace existing orders"
                  sub="Clears the current table first."
                  onClick={() => setMode("replace")}
                />
                <ModeChip
                  active={mode === "append"}
                  label="Append"
                  sub="Adds rows on top of what's there."
                  onClick={() => setMode("append")}
                />
              </div>
            </fieldset>

            {error && (
              <div className="mt-4 flex items-start gap-2 rounded-xl border border-state-abstain/40 bg-state-abstain/10 px-3 py-2 text-sm text-state-abstain">
                <AlertTriangle size={16} className="mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            <div className="mt-5 flex items-center justify-between gap-3">
              <a
                href={SAMPLE_CSV_URL}
                className="inline-flex items-center gap-1.5 text-xs text-ink-muted hover:text-ink"
              >
                <Download size={12} /> Download a sample CSV
              </a>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
                <Button size="sm" onClick={submit} disabled={!file || busy}>
                  {busy ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                  {busy ? "Uploading…" : "Upload"}
                </Button>
              </div>
            </div>
          </>
        )}

        {result && (
          <div className="grid gap-3">
            <div className="flex items-center gap-2 rounded-xl border border-state-answer/40 bg-state-answer/10 px-3 py-2 text-sm text-state-answer">
              <CheckCircle2 size={16} />
              <span>{result.detail}</span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm">
              <Kv label="Rows inserted" value={String(result.rows_inserted)} />
              <Kv label="Rows skipped" value={String(result.rows_skipped)} />
              <Kv label="Mode" value={result.mode} />
              <Kv
                label="Dims upserted"
                value={
                  Object.entries(result.dims_upserted)
                    .filter(([, v]) => v > 0)
                    .map(([k, v]) => `${k}:${v}`)
                    .join(", ") || "—"
                }
              />
            </div>

            {result.rows_skipped > 0 && (
              <div className="rounded-xl border border-state-warn/40 bg-state-warn/10 px-3 py-2 text-xs">
                Skipped rows: {result.skipped_row_indices.join(", ")}
                {result.skipped_row_indices.length >= 50 && "…"}
              </div>
            )}

            <div className="mt-1 text-xs text-ink-muted">
              Recognised columns:{" "}
              {result.columns_recognized.join(", ") || "(none)"}
            </div>

            <div className="mt-3 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={reset}>Upload another</Button>
              <Button size="sm" onClick={onClose}>Done</Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Kv({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-panel-border bg-[#0E1E2A]/50 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wider text-ink-muted">{label}</div>
      <div className="mt-0.5 tabular-nums">{value}</div>
    </div>
  );
}

function ModeChip({
  active, label, sub, onClick,
}: {
  active: boolean;
  label: string;
  sub: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 rounded-xl border px-3 py-2 text-left transition-colors ${
        active
          ? "border-brand-teal/60 bg-brand-teal/10"
          : "border-panel-border bg-[#0E1E2A]/40 hover:bg-white/5"
      }`}
    >
      <div className="text-sm font-medium">{label}</div>
      <div className="text-[11px] text-ink-muted">{sub}</div>
    </button>
  );
}
