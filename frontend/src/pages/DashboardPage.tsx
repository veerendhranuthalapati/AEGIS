import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
} from "recharts";
import { analyticsApi } from "@/api/endpoints";
import { ErrorState, LoadingSkeleton, PageHeader, StatCard } from "@/components/ui";
import { formatNumber } from "@/utils/format";

const COLORS = ["#3b82f6", "#ef4444", "#f97316", "#22c55e", "#a855f7"];

export function DashboardPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["overview"],
    queryFn: analyticsApi.overview,
    refetchInterval: 30_000,
  });

  const { data: requests } = useQuery({
    queryKey: ["requests-ts"],
    queryFn: () => analyticsApi.requests(24),
  });

  if (isLoading) return <LoadingSkeleton rows={6} />;
  if (isError || !data)
    return <ErrorState message="Failed to load dashboard data from backend." onRetry={() => refetch()} />;

  const reviewCount =
    data.decisions_today.find((d) => d.decision === "REQUIRE_REVIEW")?.count ?? 0;
  const allowCount = data.decisions_today.find((d) => d.decision === "ALLOW")?.count ?? 0;

  const hasChartData = data.requests_24h.length > 0 || data.event_counts_by_type.length > 0;

  return (
    <div>
      <PageHeader
        title="Security Dashboard"
        description="Live metrics from AEGIS backend — no fabricated statistics."
      />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Current risk (15m avg)" value={data.current_risk} accent="high" />
        <StatCard label="Active incidents" value={data.active_incidents} accent="critical" />
        <StatCard label="Blocked requests" value={formatNumber(data.blocked_requests)} />
        <StatCard label="Open approvals" value={data.open_approvals} />
        <StatCard label="Total requests" value={formatNumber(data.total_requests)} />
        <StatCard label="Under review" value={reviewCount} />
        <StatCard label="Allowed (24h)" value={allowCount} />
        <StatCard label="Event types (24h)" value={data.event_counts_by_type.length} />
      </div>

      {!hasChartData ? (
        <div className="panel mt-6 text-soc-muted">No telemetry yet. Run the attack lab or send traffic through the gateway.</div>
      ) : (
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <div className="panel h-72">
            <h3 className="mb-2 text-sm font-medium text-slate-300">Requests (24h)</h3>
            <ResponsiveContainer width="100%" height="90%">
              <LineChart data={data.requests_24h}>
                <XAxis dataKey="hour" tick={{ fontSize: 10 }} hide />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ background: "#111820", border: "1px solid #1e2936" }} />
                <Line type="monotone" dataKey="count" stroke="#3b82f6" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="panel h-72">
            <h3 className="mb-2 text-sm font-medium text-slate-300">Decisions (24h)</h3>
            <ResponsiveContainer width="100%" height="90%">
              <BarChart data={data.decisions_today}>
                <XAxis dataKey="decision" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ background: "#111820", border: "1px solid #1e2936" }} />
                <Bar dataKey="count" fill="#3b82f6" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="panel h-72">
            <h3 className="mb-2 text-sm font-medium text-slate-300">Event types</h3>
            <ResponsiveContainer width="100%" height="90%">
              <PieChart>
                <Pie
                  data={data.event_counts_by_type.slice(0, 8)}
                  dataKey="count"
                  nameKey="event_type"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label={({ event_type }) => event_type?.slice(0, 12)}
                >
                  {data.event_counts_by_type.slice(0, 8).map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: "#111820", border: "1px solid #1e2936" }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="panel h-72">
            <h3 className="mb-2 text-sm font-medium text-slate-300">Blocked vs total (hourly)</h3>
            <ResponsiveContainer width="100%" height="90%">
              <BarChart data={requests ?? []}>
                <XAxis dataKey="hour" hide />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ background: "#111820", border: "1px solid #1e2936" }} />
                <Bar dataKey="count" fill="#64748b" name="Total" />
                <Bar dataKey="blocked" fill="#ef4444" name="Blocked" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
