import { useQuery } from "@tanstack/react-query";
import { eventsApi } from "@/api/endpoints";
import { DataTable, EmptyState, ErrorState, LoadingSkeleton, PageHeader, SeverityBadge, StatCard } from "@/components/ui";
import { formatDate } from "@/utils/format";

export function ApiSecurityPage() {
  const { data: events, isLoading, isError, refetch } = useQuery({
    queryKey: ["events-api"],
    queryFn: () => eventsApi.list({ limit: 200 }),
  });

  if (isLoading) return <LoadingSkeleton rows={8} />;
  if (isError) return <ErrorState message="Failed to load API security data." onRetry={() => refetch()} />;

  const apiEvents = (events ?? []).filter(
    (e) =>
      !e.event_type.startsWith("llm_") &&
      !e.event_type.startsWith("tool_") &&
      e.event_type !== "agent_tool_invocation",
  );

  const blocked = apiEvents.filter((e) => e.decision === "BLOCK").length;
  const endpoints = new Set(apiEvents.map((e) => e.endpoint ?? "unknown"));

  const endpointStats = new Map<string, { total: number; blocked: number }>();
  for (const e of apiEvents) {
    const ep = e.endpoint ?? "unknown";
    const cur = endpointStats.get(ep) ?? { total: 0, blocked: 0 };
    cur.total += 1;
    if (e.decision === "BLOCK") cur.blocked += 1;
    endpointStats.set(ep, cur);
  }

  const topEndpoints = [...endpointStats.entries()]
    .sort((a, b) => b[1].total - a[1].total)
    .slice(0, 10);

  return (
    <div>
      <PageHeader title="API Security" description="Gateway API attack telemetry from security events." />
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <StatCard label="API events" value={apiEvents.length} />
        <StatCard label="Blocked" value={blocked} accent="critical" />
        <StatCard label="Unique endpoints" value={endpoints.size} />
      </div>
      {topEndpoints.length > 0 && (
        <div className="panel mb-6">
          <h3 className="mb-3 text-sm font-medium text-slate-300">Top endpoints</h3>
          <div className="space-y-2">
            {topEndpoints.map(([ep, stats]) => (
              <div key={ep} className="flex items-center justify-between border-b border-soc-border/50 py-2 text-sm">
                <span className="font-mono text-xs">{ep}</span>
                <span className="text-soc-muted">
                  {stats.total} requests · {stats.blocked} blocked
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
      {!apiEvents.length ? (
        <EmptyState message="No API security events recorded." />
      ) : (
        <DataTable headers={["Time", "Type", "Severity", "Decision", "Endpoint", "Risk"]}>
          {apiEvents.map((e) => (
            <tr key={e.event_id}>
              <td className="px-4 py-2 text-xs text-soc-muted">{formatDate(e.timestamp)}</td>
              <td className="px-4 py-2">{e.event_type}</td>
              <td className="px-4 py-2">
                <SeverityBadge severity={e.severity} />
              </td>
              <td className="px-4 py-2">{e.decision ?? "—"}</td>
              <td className="px-4 py-2 font-mono text-xs">{e.endpoint ?? "—"}</td>
              <td className="px-4 py-2 tabular-nums">{e.risk_score?.toFixed(1) ?? "—"}</td>
            </tr>
          ))}
        </DataTable>
      )}
    </div>
  );
}
