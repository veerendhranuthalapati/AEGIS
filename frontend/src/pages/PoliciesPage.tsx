import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { policiesApi } from "@/api/endpoints";
import { DataTable, EmptyState, ErrorState, LoadingSkeleton, PageHeader } from "@/components/ui";
import { formatDate } from "@/utils/format";
import { useAuthStore } from "@/stores/authStore";

export function PoliciesPage() {
  const qc = useQueryClient();
  const role = useAuthStore((s) => s.user?.role);
  const canEdit = role === "admin" || role === "operator";

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["policies"],
    queryFn: policiesApi.list,
  });

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      policiesApi.update(id, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["policies"] }),
  });

  if (isLoading) return <LoadingSkeleton rows={6} />;
  if (isError) return <ErrorState message="Failed to load policies." onRetry={() => refetch()} />;
  if (!data?.length) return <EmptyState message="No policies configured." />;

  return (
    <div>
      <PageHeader title="Policies" description="Backend policy engine rules — enforcement is server-side." />
      <DataTable headers={["Name", "Action", "Priority", "Enabled", "Updated", ""]}>
        {data.map((p) => (
          <tr key={p.id}>
            <td className="px-4 py-3">
              <p className="font-medium">{p.name}</p>
              <p className="text-xs text-soc-muted">{p.description ?? ""}</p>
            </td>
            <td className="px-4 py-3">{p.action}</td>
            <td className="px-4 py-3 tabular-nums">{p.priority}</td>
            <td className="px-4 py-3">{p.enabled ? "Yes" : "No"}</td>
            <td className="px-4 py-3 text-xs text-soc-muted">{formatDate(p.updated_at)}</td>
            <td className="px-4 py-3">
              {canEdit && (
                <button
                  type="button"
                  className="btn-ghost text-xs"
                  onClick={() => toggle.mutate({ id: p.id, enabled: !p.enabled })}
                >
                  {p.enabled ? "Disable" : "Enable"}
                </button>
              )}
            </td>
          </tr>
        ))}
      </DataTable>
    </div>
  );
}
