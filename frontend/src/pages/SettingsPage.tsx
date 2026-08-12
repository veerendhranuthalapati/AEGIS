import { useAuthStore } from "@/stores/authStore";
import { PageHeader } from "@/components/ui";

export function SettingsPage() {
  const user = useAuthStore((s) => s.user);

  return (
    <div className="max-w-lg">
      <PageHeader title="Settings" description="Session and environment information." />
      <div className="panel space-y-3 text-sm">
        <p>
          <span className="text-soc-muted">User:</span> {user?.username}
        </p>
        <p>
          <span className="text-soc-muted">Role:</span> {user?.role}
        </p>
        <p>
          <span className="text-soc-muted">API base:</span> /api (proxied to gateway :8000 in dev)
        </p>
        <p className="text-xs text-soc-muted">
          Authorization is enforced by the backend. UI role checks are for navigation convenience only.
        </p>
      </div>
    </div>
  );
}
