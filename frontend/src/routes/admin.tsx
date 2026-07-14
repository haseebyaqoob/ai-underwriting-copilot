import { createFileRoute, Outlet } from "@tanstack/react-router";
import { RoleShell } from "@/components/layout/RoleShell";
import { LayoutDashboard, Users, UserCog, Shield, BarChart3, ScrollText, Cpu, Sliders, Settings } from "lucide-react";
import { requireRole } from "@/lib/route-guard";

export const Route = createFileRoute("/admin")({
  beforeLoad: ({ location }) => requireRole("admin", location.pathname),
  component: AdminLayout,
});

function AdminLayout() {
  const nav = [
    { to: "/admin/dashboard", label: "Dashboard", icon: <LayoutDashboard className="h-4 w-4" /> },
    { to: "/admin/officers", label: "Officer Management", icon: <UserCog className="h-4 w-4" /> },
    { to: "/admin/users", label: "User Management", icon: <Users className="h-4 w-4" /> },
    { to: "/admin/permissions", label: "Permissions", icon: <Shield className="h-4 w-4" /> },
    { to: "/admin/analytics", label: "System Analytics", icon: <BarChart3 className="h-4 w-4" /> },
    { to: "/admin/audit", label: "Audit Logs", icon: <ScrollText className="h-4 w-4" /> },
    { to: "/admin/models", label: "Model Usage", icon: <Cpu className="h-4 w-4" /> },
    { to: "/admin/config", label: "Configuration", icon: <Sliders className="h-4 w-4" /> },
    { to: "/admin/settings", label: "Settings", icon: <Settings className="h-4 w-4" /> },
  ];
  return <RoleShell role="Administrator" nav={nav}><Outlet /></RoleShell>;
}
