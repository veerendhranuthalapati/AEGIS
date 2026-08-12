import { useQuery } from "@tanstack/react-query";
import { mlApi } from "@/api/endpoints";
import { DataTable, EmptyState, ErrorState, LoadingSkeleton, PageHeader } from "@/components/ui";
import { formatDate } from "@/utils/format";

export function MlPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["ml-models"],
    queryFn: mlApi.models,
  });

  if (isLoading) return <LoadingSkeleton rows={4} />;
  if (isError) return <ErrorState message="Failed to load ML models." onRetry={() => refetch()} />;
  if (!data?.length) return <EmptyState message="No ML models trained yet." />;

  return (
    <div>
      <PageHeader
        title="ML Models"
        description="Anomaly detection models. Metrics are from synthetic training data unless otherwise noted."
      />
      <div className="panel mb-4 border-amber-900/40 bg-amber-950/20 text-sm text-amber-200">
        Dataset: <strong>Synthetic</strong> — do not interpret accuracy as real-world performance.
      </div>
      <DataTable headers={["Name", "Algorithm", "Version", "Status", "Trained", "Accuracy", "Samples"]}>
        {data.map((m) => {
          const acc = m.metrics?.accuracy;
          const accuracy =
            typeof acc === "number" ? acc.toFixed(3) : acc != null ? String(acc) : "—";
          return (
            <tr key={m.id}>
              <td className="px-4 py-3">{m.name}</td>
              <td className="px-4 py-3">{m.algorithm}</td>
              <td className="px-4 py-3 font-mono text-xs">{m.version}</td>
              <td className="px-4 py-3">{m.status}</td>
              <td className="px-4 py-3 text-xs">{m.trained_at ? formatDate(m.trained_at) : "—"}</td>
              <td className="px-4 py-3 tabular-nums">{accuracy}</td>
              <td className="px-4 py-3 tabular-nums">{m.training_size}</td>
            </tr>
          );
        })}
      </DataTable>
    </div>
  );
}
