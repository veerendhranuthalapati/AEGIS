import { clsx } from "./clsx";

export function cn(...inputs: Parameters<typeof clsx>) {
  return clsx(...inputs);
}

export function severityBadge(severity: string) {
  const s = severity.toUpperCase();
  if (s === "CRITICAL") return "badge-critical";
  if (s === "HIGH") return "badge-high";
  if (s === "MEDIUM") return "badge-medium";
  return "badge-low";
}

export function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function formatNumber(n: number | null | undefined) {
  if (n == null) return "—";
  return n.toLocaleString();
}
