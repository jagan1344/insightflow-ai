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
  dataset_id: string;
  dataset_name: string;
  table_name: string;
  rows_inserted: number;
  rows_skipped: number;
  skipped_row_indices: number[];
  columns: { name: string; sql_type: string; role: string }[];
  is_active: boolean;
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

// --------- dataset registry ---------

export interface DatasetSummary {
  id: string;
  name: string;
  table: string;
  kind: "demo" | "uploaded";
  uploaded_at: string | null;
  is_active: boolean;
}

export interface ActiveDataset {
  id: string;
  name: string;
  table: string;
  kind: "demo" | "uploaded";
  columns: {
    name: string;
    sql_type: string;
    role: string;
    sample_values: string[];
  }[];
  measures: string[];
  dimensions: string[];
  dates: string[];
}

export async function fetchActiveDataset(): Promise<ActiveDataset> {
  const res = await fetch("/api/datasets/active", { cache: "no-store" });
  if (!res.ok) throw new Error(`fetch active dataset failed: ${res.status}`);
  return res.json();
}

export async function fetchDatasets(): Promise<DatasetSummary[]> {
  const res = await fetch("/api/datasets", { cache: "no-store" });
  if (!res.ok) throw new Error(`fetch datasets failed: ${res.status}`);
  return res.json();
}

export async function activateDataset(id: string): Promise<void> {
  const res = await fetch(`/api/datasets/activate/${encodeURIComponent(id)}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`activate dataset failed: ${res.status}`);
}

