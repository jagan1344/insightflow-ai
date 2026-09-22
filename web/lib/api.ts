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
