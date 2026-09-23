export function fmtCurrency(n: number): string {
  if (Math.abs(n) >= 1_000_000) return "$" + (n / 1_000_000).toFixed(2) + "M";
  if (Math.abs(n) >= 1_000)     return "$" + (n / 1_000).toFixed(1) + "K";
  return "$" + n.toFixed(0);
}

export function fmtNumber(n: number): string {
  return n.toLocaleString();
}

export function fmtPct(n: number): string {
  return (n >= 0 ? "+" : "") + n.toFixed(1) + "%";
}

export function fmtRatio(n: number): string {
  return (n * 100).toFixed(1) + "%";
}

export const CATEGORY_COLORS = ["#14B8A6", "#38BDF8", "#8B5CF6", "#F59E0B"];
export const REGION_COLORS   = ["#14B8A6", "#22D3B7", "#0E7C6B", "#0891B2"];
