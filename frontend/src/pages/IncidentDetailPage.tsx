import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { incidentsApi } from "@/api/endpoints";
import { ErrorState, LoadingSkeleton, PageHeader, SeverityBadge } from "@/components/ui";
import { formatDate } from "@/utils/format";

export function IncidentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["incident", id],
    queryFn: () => incidentsApi.get(id!),
    enabled: !!id,
  });

  if (isLoading) return <LoadingSkeleton rows={6} />;
  if (isError || !data) return <ErrorState message="Incident not found." onRetry={() => refetch()} />;

  return (
    <div className="max-w-4xl space-y-6">
      <PageHeader title={data.title} description={`Incident #${data.incident_number}`} />
      <div className="panel space-y-3">
        <h2 className="text-sm font-semibold text-slate-300">Summary</h2>
        <p className="text-sm text-slate-400">{data.description ?? "No description."}</p>
        <div className="flex flex-wrap gap-4 text-sm">
          <span>
            Severity: <SeverityBadge severity={data.severity} />
          </span>
          <span>Risk confidence: {data.confidence.toFixed(1)}</span>
          <span>Status: {data.status}</span>
          <span>Attacker: {data.attacker_key ?? "unknown"}</span>
        </div>
      </div>
      {data.mitre_techniques && data.mitre_techniques.length > 0 && (
        <div className="panel">
          <h2 className="text-sm font-semibold text-slate-300">MITRE mapping</h2>
          <div className="mt-2 flex flex-wrap gap-2">
            {data.mitre_techniques.map((t) => (
              <span key={t} className="rounded bg-soc-border px-2 py-1 font-mono text-xs">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}
      <div className="panel">
        <h2 className="text-sm font-semibold text-slate-300">Timeline</h2>
        {!data.timeline?.length ? (
          <p className="mt-2 text-sm text-soc-muted">No timeline entries.</p>
        ) : (
          <ol className="mt-4 space-y-3 border-l border-soc-border pl-4">
            {data.timeline.map((entry, i) => (
              <li key={i} className="relative">
                <span className="absolute -left-[1.35rem] top-1 h-2 w-2 rounded-full bg-soc-accent" />
                <p className="text-xs text-soc-muted">{formatDate(entry.time)}</p>
                <p className="text-sm font-medium">{entry.event_type}</p>
                <p className="text-xs text-soc-muted">{entry.endpoint ?? entry.event_id}</p>
              </li>
            ))}
          </ol>
        )}
      </div>
      <div className="panel">
        <h2 className="text-sm font-semibold text-slate-300">Evidence</h2>
        <p className="mt-1 text-xs text-soc-muted">{data.related_event_ids?.length ?? 0} related events</p>
        <ul className="mt-2 space-y-1 font-mono text-xs text-slate-400">
          {(data.related_event_ids ?? []).map((eid) => (
            <li key={eid}>{eid}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
