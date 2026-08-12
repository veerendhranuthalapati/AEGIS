import { useQuery } from "@tanstack/react-query";
import { threatsApi } from "@/api/endpoints";
import { DataTable, EmptyState, ErrorState, LoadingSkeleton, PageHeader, SeverityBadge } from "@/components/ui";
import { formatDate } from "@/utils/format";
import { Link } from "react-router-dom";

export function ThreatsPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["threats-live"],
    queryFn: () => threatsApi.live(120, 100),
    refetchInterval: 15_000,
  });

  if (isLoading) return <LoadingSkeleton rows={8} />;
  if (isError) return <ErrorState message="Failed to load live threats." onRetry={() => refetch()} />;
  if (!data?.length) return <EmptyState message="No medium+ severity events in the last 2 hours." />;

  return (
    <div>
      <PageHeader title="Live Threats" description="Recent HIGH/MEDIUM/CRITICAL events from backend." />
      <DataTable headers={["Time", "Type", "Severity", "Decision", "Endpoint", "Risk", "Incident"]}>
        {data.map((t) => (
          <tr key={t.event_id} className="hover:bg-soc-border/30">
            <td className="px-4 py-2 text-xs text-soc-muted">{formatDate(t.timestamp)}</td>
            <td className="px-4 py-2 text-sm">{t.event_type}</td>
            <td className="px-4 py-2">
              <SeverityBadge severity={t.severity} />
            </td>
            <td className="px-4 py-2">{t.decision ?? "—"}</td>
            <td className="px-4 py-2 font-mono text-xs">{t.endpoint ?? "—"}</td>
            <td className="px-4 py-2 tabular-nums">{t.risk_score?.toFixed(1) ?? "—"}</td>
            <td className="px-4 py-2">
              {t.incident_id ? (
                <Link to={`/incidents/${t.incident_id}`} className="text-blue-400 text-xs hover:underline">
                  View
                </Link>
              ) : (
                "—"
              )}
            </td>
          </tr>
        ))}
      </DataTable>
    </div>
  );
}
