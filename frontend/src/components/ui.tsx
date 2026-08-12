import { ReactNode } from "react";

export function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string | number;
  sub?: string;
  accent?: "critical" | "high" | "default";
}) {
  const color =
    accent === "critical"
      ? "text-red-400"
      : accent === "high"
        ? "text-orange-400"
        : "text-white";
  return (
    <div className="panel">
      <p className="text-xs uppercase tracking-wide text-soc-muted">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${color}`}>{value}</p>
      {sub && <p className="mt-1 text-xs text-soc-muted">{sub}</p>}
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="panel flex flex-col items-center justify-center py-12 text-soc-muted">
      <p>{message}</p>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="panel border-red-900/50 bg-red-950/20 py-8 text-center">
      <p className="text-red-300">{message}</p>
      {onRetry && (
        <button type="button" className="btn-primary mt-4" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function LoadingSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-10 animate-pulse rounded bg-soc-border/40" />
      ))}
    </div>
  );
}

export function PageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-xl font-semibold text-white">{title}</h1>
      {description && <p className="mt-1 text-sm text-soc-muted">{description}</p>}
    </div>
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  const cls =
    severity.toUpperCase() === "CRITICAL"
      ? "badge-critical"
      : severity.toUpperCase() === "HIGH"
        ? "badge-high"
        : severity.toUpperCase() === "MEDIUM"
          ? "badge-medium"
          : "badge-low";
  return <span className={cls}>{severity}</span>;
}

export function DataTable({
  headers,
  children,
}: {
  headers: string[];
  children: ReactNode;
}) {
  return (
    <div className="panel overflow-x-auto p-0">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-soc-border text-xs uppercase text-soc-muted">
            {headers.map((h) => (
              <th key={h} className="px-4 py-3 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-soc-border">{children}</tbody>
      </table>
    </div>
  );
}
