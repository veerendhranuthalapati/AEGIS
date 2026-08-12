import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { auditApi } from "@/api/endpoints";
import { DataTable, EmptyState, ErrorState, LoadingSkeleton, PageHeader } from "@/components/ui";
import { formatDate } from "@/utils/format";

export function AuditPage() {
  const [actionFilter, setActionFilter] = useState("");
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["audit", actionFilter],
    queryFn: () => auditApi.list({ limit: 100, action: actionFilter || undefined }),
  });

  if (isLoading) return <LoadingSkeleton rows={8} />;
  if (isError) return <ErrorState message="Failed to load audit logs." onRetry={() => refetch()} />;

  return (
    <div>
      <PageHeader title="Audit Logs" description="Administrative and security audit trail from backend." />
      <input
        className="input mb-4 max-w-sm"
        placeholder="Filter by action (exact match)…"
        value={actionFilter}
        onChange={(e) => setActionFilter(e.target.value)}
      />
      {!data?.length ? (
        <EmptyState message="No audit entries match." />
      ) : (
        <DataTable headers={["Time", "Actor", "Action", "Target", "Status", "IP"]}>
          {data.map((a) => (
            <tr key={a.id}>
              <td className="px-4 py-2 text-xs text-soc-muted">{formatDate(a.timestamp)}</td>
              <td className="px-4 py-2 font-mono text-xs">{a.actor_id ?? "—"}</td>
              <td className="px-4 py-2">{a.action}</td>
              <td className="px-4 py-2 font-mono text-xs">
                {a.target_type ? `${a.target_type}:${a.target_id ?? ""}` : "—"}
              </td>
              <td className="px-4 py-2">{a.status}</td>
              <td className="px-4 py-2 text-xs">{a.ip_address ?? "—"}</td>
            </tr>
          ))}
        </DataTable>
      )}
    </div>
  );
}
