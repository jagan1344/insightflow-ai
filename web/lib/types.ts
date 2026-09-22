export type DecisionAction = "ANSWER" | "WARN" | "CLARIFY" | "ABSTAIN";

export interface Decision {
  action: DecisionAction;
  reason: string;
}

export interface Confidence {
  score: number;
  signals: Record<string, number>;
}

export interface EvidenceStep {
  step: string;
  value: unknown;
}

export interface Evidence {
  chain: EvidenceStep[];
  sample_rows: Record<string, unknown>[];
  row_count: number;
}

export interface AskResponse {
  question: string;
  sql: string;
  intent: string;
  kpi: string | null;
  decision: Decision;
  confidence: Confidence;
  answer: string;
  explanation: string;
  recommendation: string | null;
  chart: { kind: string; x?: string; y?: string };
  result_columns: string[];
  result_rows: (string | number | null)[][];
  evidence: Evidence;
  notes: string[];
}

export interface KpiValue {
  value: number;
  unit: string;
  delta_pct: number;
}

export interface DashboardPayload {
  version: number;
  kpis: Record<string, KpiValue>;
  revenue_by_month:    { month: string; value: number }[];
  revenue_by_region:   { region: string; value: number }[];
  revenue_by_category: { category: string; value: number }[];
  margin_by_category:  { category: string; value: number }[];
}

export interface WsMessage {
  type: "dashboard_update" | "heartbeat" | "pong";
  version?: number;
  ts?: number;
  data?: DashboardPayload;
}
