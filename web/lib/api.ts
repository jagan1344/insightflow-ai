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

/**
 * Best backend origin for browser-issued requests.
 *
 * By default the Next.js dev server proxies `/api/*` to the backend via
 * `next.config.js` rewrites. That proxy tends to time out on multipart
 * uploads (~3 MB Excel files → ECONNRESET) before the backend finishes
 * decoding + inserting rows. So for LARGE requests (uploads) we skip
 * the proxy and go directly to the backend — CORS is already allowed
 * for the dev origin.
 *
 * You can override via `NEXT_PUBLIC_BACKEND_URL` (e.g. in production).
 */
function backendOrigin(): string {
  const fromEnv = process.env.NEXT_PUBLIC_BACKEND_URL;
  if (fromEnv) return fromEnv.replace(/\/$/, "");
  if (typeof window === "undefined") return "";
  // Dev: same host, port 8000.
  const { protocol, hostname } = window.location;
  return `${protocol}//${hostname}:8000`;
}

export async function uploadOrdersCsv(
  file: File,
  mode: "replace" | "append" = "replace",
  datasetName?: string,
): Promise<UploadResult> {
  const fd = new FormData();
  fd.append("file", file);
  const qs = new URLSearchParams({ mode });
  if (datasetName) qs.set("dataset_name", datasetName);
  const url = `${backendOrigin()}/api/upload/orders?${qs.toString()}`;
  const res = await fetch(url, { method: "POST", body: fd });
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


// ============================================================================
// Enterprise dashboard pages — real backend endpoints
// ============================================================================

export interface ExplorerMeta {
  dataset: { id: string; name: string; table: string; kind: string };
  columns: { name: string; role: string; sql_type: string }[];
  measures: string[];
  dimensions: string[];
  dates: string[];
  kpis: {
    id: string; name: string; aggregation: string; formula: string;
    unit: string; aliases: string[];
  }[];
  grain: string;
  suggested_questions: string[];
}

export async function fetchExplorerMeta(): Promise<ExplorerMeta> {
  const res = await fetch("/api/pages/explorer", { cache: "no-store" });
  if (!res.ok) throw new Error(`explorer meta failed: ${res.status}`);
  return res.json();
}

export interface AnomalyResponse {
  kpi?: string;
  name?: string;
  method?: string;
  threshold?: number;
  mean?: number | null;
  stdev?: number | null;
  series?: { period: string; value: number }[];
  anomalies?: {
    period: string; value: number; z_score: number;
    expected: number; deviation: number; severity: "high" | "medium";
  }[];
  sql?: string;
  unavailable?: boolean;
  reason?: string;
  note?: string;
}

export async function fetchAnomalies(kpi: string, threshold = 2.0): Promise<AnomalyResponse> {
  const q = new URLSearchParams({ kpi_id: kpi, threshold: String(threshold) });
  const res = await fetch(`/api/pages/anomaly?${q}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`anomaly failed: ${res.status}`);
  return res.json();
}

export interface ForecastResponse {
  kpi?: string;
  name?: string;
  baseline?: string;
  horizon?: number;
  history?: { period: string; value: number }[];
  mae?: number | null;
  test_len?: number;
  forecast?: { period: string; value: number }[];
  unavailable?: boolean;
  reason?: string;
  note?: string;
}

export async function fetchForecast(kpi: string, horizon = 3, baseline = "last_value"): Promise<ForecastResponse> {
  const q = new URLSearchParams({ kpi_id: kpi, horizon: String(horizon), baseline });
  const res = await fetch(`/api/pages/forecast?${q}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`forecast failed: ${res.status}`);
  return res.json();
}

export interface Recommendation {
  observation: string;
  metric: string;
  value: unknown;
  evidence_sql: string;
  suggested_action: string;
  limitations: string;
}

export async function fetchRecommendations(): Promise<{ recommendations: Recommendation[]; note?: string }> {
  const res = await fetch("/api/pages/recommendations", { cache: "no-store" });
  if (!res.ok) throw new Error(`recommendations failed: ${res.status}`);
  return res.json();
}

export interface SummaryReport {
  source: string;
  content: {
    title: string; generated_at: string; dataset: string;
    kpis: { kpi_id: string; name?: string; value?: number | null; unit?: string; error?: string }[];
    markdown?: string;
  };
  duration_ms?: number;
}

export async function fetchSummaryReport(format: "markdown" | "json" = "markdown"): Promise<SummaryReport> {
  const q = new URLSearchParams({ format });
  const res = await fetch(`/api/pages/reports/summary?${q}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`report failed: ${res.status}`);
  return res.json();
}

export interface SourcesInfo {
  database: { dialect: string; table_count: number; tables: string[] };
  datasets: DatasetSummary[];
  active_dataset: {
    id: string; name: string; table: string; kind: string;
    measures: string[]; dimensions: string[]; dates: string[];
  };
}

export async function fetchSources(): Promise<SourcesInfo> {
  const res = await fetch("/api/pages/sources", { cache: "no-store" });
  if (!res.ok) throw new Error(`sources failed: ${res.status}`);
  return res.json();
}

export interface SemanticModelResp {
  dataset: { id: string; name: string; table: string; kind: string };
  model: {
    grain: string; grain_confidence: number;
    primary_key_candidate: string | null;
    columns: {
      name: string; role: string; role_confidence: number;
      sql_type: string; distinct_count: number | null;
      null_pct: number; is_pk_candidate: boolean;
      is_fk_candidate: boolean; aliases: string[];
    }[];
    n_rows: number;
  };
  kpis: {
    id: string; name: string; aggregation: string; formula: string;
    unit: string; aliases: string[]; required_columns: string[];
    ratio_0_1: boolean; non_negative: boolean;
  }[];
}

export async function fetchSemanticModel(): Promise<SemanticModelResp> {
  const res = await fetch("/api/pages/semantic", { cache: "no-store" });
  if (!res.ok) throw new Error(`semantic failed: ${res.status}`);
  return res.json();
}

export interface SettingsInfo {
  python_version: string;
  database_url_configured: boolean;
  llm_provider: string;
  cors_origins: string;
  mcp_servers: { name: string; enabled: boolean; transport: string; connected: boolean }[];
  confidence_thresholds: { threshold_high?: number; threshold_low?: number };
  confidence_weights: Record<string, number>;
}

export async function fetchSettings(): Promise<SettingsInfo> {
  const res = await fetch("/api/pages/settings", { cache: "no-store" });
  if (!res.ok) throw new Error(`settings failed: ${res.status}`);
  return res.json();
}

// ============================================================================
// MCP introspection
// ============================================================================

export interface MCPServerStatus {
  name: string; enabled: boolean; connected: boolean;
  transport: string; tool_count: number; tools: string[];
  allowed_tools: string[] | null; error: string | null;
}

export async function fetchMCPServers(): Promise<MCPServerStatus[]> {
  const res = await fetch("/api/mcp/servers", { cache: "no-store" });
  if (!res.ok) throw new Error(`mcp servers failed: ${res.status}`);
  return res.json();
}

export async function connectMCPServers(): Promise<Record<string, string>> {
  const res = await fetch("/api/mcp/connect_all", { method: "POST" });
  if (!res.ok) throw new Error(`mcp connect failed: ${res.status}`);
  return res.json();
}

export interface MCPToolDescriptor {
  name: string; description: string; input_schema: Record<string, unknown>;
}

export async function fetchMCPTools(server?: string): Promise<Record<string, MCPToolDescriptor[]>> {
  const q = server ? `?server=${encodeURIComponent(server)}` : "";
  const res = await fetch(`/api/mcp/tools${q}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`mcp tools failed: ${res.status}`);
  return res.json();
}

export async function callMCPTool(server: string, tool: string, args: Record<string, unknown> = {}): Promise<{
  ok: boolean; server: string; tool: string; content: unknown;
  raw_text: string; error: string; duration_ms: number;
}> {
  const res = await fetch("/api/mcp/call", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ server, tool, arguments: args }),
  });
  if (!res.ok) throw new Error(`mcp call failed: ${res.status}`);
  return res.json();
}
