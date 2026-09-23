import type { AskResponse, DashboardPayload } from "./types";

export async function askQuestion(question: string): Promise<AskResponse> {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) throw new Error(`ask failed: ${res.status}`);
  return res.json();
}

export async function fetchDashboard(): Promise<DashboardPayload> {
  const res = await fetch("/api/dashboard", { cache: "no-store" });
  if (!res.ok) throw new Error(`dashboard failed: ${res.status}`);
  return res.json();
}

export async function startSimulate(): Promise<void> {
  await fetch("/api/simulate/start", { method: "POST" });
}

export async function stopSimulate(): Promise<void> {
  await fetch("/api/simulate/stop", { method: "POST" });
}

export async function reseed(): Promise<void> {
  await fetch("/api/seed", { method: "POST" });
}

export interface UploadResult {
  ok: boolean;
  rows_inserted: number;
  rows_skipped: number;
  skipped_row_indices: number[];
  columns_recognized: string[];
  dims_upserted: Record<string, number>;
  mode: "replace" | "append";
  detail: string;
}

export async function uploadOrdersCsv(
  file: File,
  mode: "replace" | "append" = "replace",
): Promise<UploadResult> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`/api/upload/orders?mode=${mode}`, {
    method: "POST",
    body: fd,
  });
  if (!res.ok) {
    let msg = `upload failed: ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) msg = body.detail;
    } catch { /* ignore */ }
    throw new Error(msg);
  }
  return res.json();
}

export const SAMPLE_CSV_URL = "/api/upload/sample.csv";

