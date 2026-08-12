import { NavLink, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  AlertTriangle,
  Shield,
  Globe,
  Bot,
  FileKey,
  Users,
  Brain,
  ScrollText,
  Settings,
  LogOut,
  Activity,
} from "lucide-react";
import { useAuthStore } from "@/stores/authStore";
import { authApi } from "@/api/endpoints";

const nav = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/threats", label: "Threats", icon: Activity },
  { to: "/incidents", label: "Incidents", icon: AlertTriangle },
  { to: "/api-security", label: "API Security", icon: Globe },
  { to: "/llm-security", label: "LLM Security", icon: Shield },
  { to: "/agents", label: "AI Agents", icon: Bot },
  { to: "/policies", label: "Policies", icon: FileKey },
  { to: "/users", label: "Users", icon: Users },
  { to: "/ml", label: "ML Models", icon: Brain },
  { to: "/audit", label: "Audit Logs", icon: ScrollText },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } catch {
      /* session may already be invalid */
    }
    logout();
    navigate("/login");
  };

  return (
    <aside className="flex w-56 flex-col border-r border-soc-border bg-soc-panel">
      <div className="border-b border-soc-border px-4 py-5">
        <p className="text-lg font-bold tracking-tight text-white">AEGIS</p>
        <p className="text-xs text-soc-muted">Security Gateway SOC</p>
      </div>
      <nav className="flex-1 space-y-0.5 p-2">
        {nav.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-2 rounded-md px-3 py-2 text-sm ${
                isActive
                  ? "bg-soc-accent/20 text-blue-300"
                  : "text-slate-400 hover:bg-soc-border/50 hover:text-slate-200"
              }`
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-soc-border p-4">
        <p className="truncate text-sm font-medium text-slate-200">{user?.username}</p>
        <p className="text-xs capitalize text-soc-muted">{user?.role ?? "user"}</p>
        <button type="button" onClick={handleLogout} className="btn-ghost mt-2 flex items-center gap-1">
          <LogOut size={14} /> Log out
        </button>
      </div>
    </aside>
  );
}
