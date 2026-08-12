import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { eventsApi, toolsApi } from "@/api/endpoints";
import { DataTable, EmptyState, ErrorState, LoadingSkeleton, PageHeader, StatCard } from "@/components/ui";
import { formatDate } from "@/utils/format";
import { useAuthStore } from "@/stores/authStore";

export function AgentsPage() {
  const qc = useQueryClient();
  const role = useAuthStore((s) => s.user?.role);
  const canApprove = role === "admin" || role === "operator";

  const { data: tools, isLoading: tLoad } = useQuery({ queryKey: ["tools"], queryFn: toolsApi.list });
  const { data: approvals, isLoading: aLoad, isError, refetch } = useQuery({
    queryKey: ["approvals"],
    queryFn: toolsApi.approvals,
    refetchInterval: 10_000,
  });
  const { data: events } = useQuery({
    queryKey: ["events-tools"],
    queryFn: () => eventsApi.list({ limit: 100 }),
  });

  const decide = useMutation({
    mutationFn: ({ id, approved }: { id: string; approved: boolean }) =>
      toolsApi.decideApproval(id, approved),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["approvals"] }),
  });

  if (tLoad || aLoad) return <LoadingSkeleton rows={8} />;
  if (isError) return <ErrorState message="Failed to load agent/tool data." onRetry={() => refetch()} />;

  const toolEvents = (events ?? []).filter(
    (e) => e.event_type.startsWith("tool_") || e.event_type === "agent_tool_invocation",
  );
  const pending = (approvals ?? []).filter((a) => a.status === "pending");

  return (
    <div>
      <PageHeader title="AI Agent Security" description="Tool registry, invocations, and approval workflow." />
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <StatCard label="Registered tools" value={tools?.length ?? 0} />
        <StatCard label="Pending approvals" value={pending.length} accent="high" />
        <StatCard label="Tool events" value={toolEvents.length} />
      </div>
      <h3 className="mb-2 text-sm font-medium text-slate-300">Approval queue</h3>
      {!approvals?.length ? (
        <EmptyState message="No approval requests." />
      ) : (
        <DataTable headers={["Tool", "Actor", "Risk", "Status", "Created", "Action"]}>
          {approvals.map((a) => (
            <tr key={a.id}>
              <td className="px-4 py-2 font-mono text-xs">{a.tool_name}</td>
              <td className="px-4 py-2">{a.actor_id}</td>
              <td className="px-4 py-2 tabular-nums">{a.risk_score?.toFixed(1) ?? "—"}</td>
              <td className="px-4 py-2">{a.status}</td>
              <td className="px-4 py-2 text-xs text-soc-muted">{formatDate(a.created_at)}</td>
              <td className="px-4 py-2">
                {a.status === "pending" && canApprove ? (
                  <span className="flex gap-2">
                    <button
                      type="button"
                      className="btn-primary text-xs py-1"
                      onClick={() => decide.mutate({ id: a.id, approved: true })}
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      className="btn-ghost text-xs py-1"
                      onClick={() => decide.mutate({ id: a.id, approved: false })}
                    >
                      Deny
                    </button>
                  </span>
                ) : (
                  "—"
                )}
              </td>
            </tr>
          ))}
        </DataTable>
      )}
      {toolEvents.length > 0 && (
        <>
          <h3 className="mb-2 mt-8 text-sm font-medium text-slate-300">Recent tool events</h3>
          <DataTable headers={["Time", "Type", "Decision", "Endpoint"]}>
            {toolEvents.slice(0, 20).map((e) => (
              <tr key={e.event_id}>
                <td className="px-4 py-2 text-xs">{formatDate(e.timestamp)}</td>
                <td className="px-4 py-2">{e.event_type}</td>
                <td className="px-4 py-2">{e.decision ?? "—"}</td>
                <td className="px-4 py-2 font-mono text-xs">{e.endpoint ?? "—"}</td>
              </tr>
            ))}
          </DataTable>
        </>
      )}
    </div>
  );
}
