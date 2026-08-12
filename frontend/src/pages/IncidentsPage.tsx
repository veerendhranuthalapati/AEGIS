import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { incidentsApi } from "@/api/endpoints";
import { DataTable, EmptyState, ErrorState, LoadingSkeleton, PageHeader, SeverityBadge } from "@/components/ui";
import { formatDate } from "@/utils/format";

export function IncidentsPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["incidents"],
    queryFn: incidentsApi.list,
  });

  if (isLoading) return <LoadingSkeleton rows={8} />;
  if (isError) return <ErrorState message="Failed to load incidents." onRetry={() => refetch()} />;
  if (!data?.length) return <EmptyState message="No incidents correlated yet." />;

  return (
    <div>
      <PageHeader title="Incidents" description="Correlated attack campaigns from the backend worker." />
      <DataTable headers={["#", "Title", "Severity", "Type", "Confidence", "Status", "First seen"]}>
        {data.map((inc) => (
          <tr key={inc.id} className="hover:bg-soc-border/30">
            <td className="px-4 py-3 font-mono text-xs">{inc.incident_number}</td>
            <td className="px-4 py-3">
              <Link to={`/incidents/${inc.id}`} className="text-blue-400 hover:underline">
                {inc.title}
              </Link>
            </td>
            <td className="px-4 py-3">
              <SeverityBadge severity={inc.severity} />
            </td>
            <td className="px-4 py-3 text-xs text-soc-muted">{inc.attack_type ?? "—"}</td>
            <td className="px-4 py-3 tabular-nums">{inc.confidence.toFixed(1)}</td>
            <td className="px-4 py-3">{inc.status}</td>
            <td className="px-4 py-3 text-xs text-soc-muted">{formatDate(inc.first_seen)}</td>
          </tr>
        ))}
      </DataTable>
    </div>
  );
}
