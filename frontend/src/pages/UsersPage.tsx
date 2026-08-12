import { useQuery } from "@tanstack/react-query";
import { usersApi } from "@/api/endpoints";
import { DataTable, EmptyState, ErrorState, LoadingSkeleton, PageHeader } from "@/components/ui";
import { formatDate } from "@/utils/format";

export function UsersPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["users"],
    queryFn: usersApi.list,
  });

  if (isLoading) return <LoadingSkeleton rows={6} />;
  if (isError) return <ErrorState message="Failed to load users (admin/operator only)." onRetry={() => refetch()} />;
  if (!data?.length) return <EmptyState message="No users." />;

  return (
    <div>
      <PageHeader title="Users" description="Account management — RBAC enforced by backend." />
      <DataTable headers={["Username", "Email", "Role", "Active", "Locked", "Created"]}>
        {data.map((u) => (
          <tr key={u.id}>
            <td className="px-4 py-3">{u.username}</td>
            <td className="px-4 py-3 text-sm text-soc-muted">{u.email ?? "—"}</td>
            <td className="px-4 py-3 capitalize">{u.role}</td>
            <td className="px-4 py-3">{u.is_active ? "Yes" : "No"}</td>
            <td className="px-4 py-3">{u.is_locked ? "Yes" : "No"}</td>
            <td className="px-4 py-3 text-xs text-soc-muted">{formatDate(u.created_at)}</td>
          </tr>
        ))}
      </DataTable>
    </div>
  );
}
