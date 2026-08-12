import { FormEvent, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { authApi } from "@/api/endpoints";
import { useAuthStore } from "@/stores/authStore";
import { getErrorMessage } from "@/api/client";
import type { User } from "@/types/api";

export function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const setSession = useAuthStore((s) => s.setSession);
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? "/";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await authApi.login(username, password);
      setSession(res.access_token, res.refresh_token, res.user as User);
      navigate(from, { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-soc-bg px-4">
      <div className="panel w-full max-w-md">
        <h1 className="text-xl font-semibold text-white">AEGIS Security Gateway</h1>
        <p className="mt-1 text-sm text-soc-muted">Sign in to the control plane</p>
        <form onSubmit={submit} className="mt-6 space-y-4">
          <div>
            <label className="text-xs text-soc-muted">Username</label>
            <input
              className="input mt-1"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </div>
          <div>
            <label className="text-xs text-soc-muted">Password</label>
            <input
              type="password"
              className="input mt-1"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          {error && <p className="text-sm text-red-400">{error}</p>}
          <button type="submit" className="btn-primary w-full" disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="mt-4 text-xs text-soc-muted">
          Dev credentials: admin / Admin@1234 or operator / Operator@1234
        </p>
      </div>
    </div>
  );
}
