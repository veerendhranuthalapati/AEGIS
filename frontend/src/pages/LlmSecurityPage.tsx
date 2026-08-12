import { useQuery } from "@tanstack/react-query";
import { eventsApi } from "@/api/endpoints";
import { DataTable, EmptyState, ErrorState, LoadingSkeleton, PageHeader, SeverityBadge, StatCard } from "@/components/ui";
import { formatDate } from "@/utils/format";

export function LlmSecurityPage() {
  const { data: events, isLoading, isError, refetch } = useQuery({
    queryKey: ["events-llm"],
    queryFn: () => eventsApi.list({ limit: 100 }),
  });

  if (isLoading) return <LoadingSkeleton rows={8} />;
  if (isError) return <ErrorState message="Failed to load LLM security events." onRetry={() => refetch()} />;

  const llmEvents = (events ?? []).filter((e) => e.event_type.startsWith("llm_"));

  const blocked = llmEvents.filter((e) => e.decision === "BLOCK").length;
  const review = llmEvents.filter((e) => e.decision === "REQUIRE_REVIEW").length;
  const redactions = llmEvents.filter((e) => e.event_type.includes("redact")).length;

  return (
    <div>
      <PageHeader
        title="LLM Security"
        description="Prompt/output scanning events. Sensitive content is redacted by backend policy."
      />
      <div className="mb-6 grid gap-4 sm:grid-cols-4">
        <StatCard label="LLM events" value={llmEvents.length} />
        <StatCard label="Blocked" value={blocked} accent="critical" />
        <StatCard label="Under review" value={review} />
        <StatCard label="Redaction events" value={redactions} />
      </div>
      {!llmEvents.length ? (
        <EmptyState message="No LLM security events yet." />
      ) : (
        <DataTable headers={["Time", "Type", "Severity", "Decision", "Risk", "Source"]}>
          {llmEvents.map((e) => (
            <tr key={e.event_id}>
              <td className="px-4 py-2 text-xs text-soc-muted">{formatDate(e.timestamp)}</td>
              <td className="px-4 py-2">{e.event_type}</td>
              <td className="px-4 py-2">
                <SeverityBadge severity={e.severity} />
              </td>
              <td className="px-4 py-2">{e.decision ?? "—"}</td>
              <td className="px-4 py-2 tabular-nums">{e.risk_score?.toFixed(1) ?? "—"}</td>
              <td className="px-4 py-2 text-xs text-soc-muted">{e.detection_source ?? "—"}</td>
            </tr>
          ))}
        </DataTable>
      )}
    </div>
  );
}
