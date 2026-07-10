import { createFileRoute, Outlet } from "@tanstack/react-router";
import { RoleShell } from "@/components/layout/RoleShell";
import { LayoutDashboard, Inbox, BarChart3, Bell, Settings, FileSearch } from "lucide-react";
import { requireRole } from "@/lib/route-guard";

export const Route = createFileRoute("/officer")({
  beforeLoad: ({ location }) => requireRole("loan_officer", location.pathname),
  component: OfficerLayout,
});

function OfficerLayout() {
  const nav = [
    { to: "/officer/dashboard", label: "Dashboard", icon: <LayoutDashboard className="h-4 w-4" /> },
    { to: "/officer/queue", label: "Application Queue", icon: <Inbox className="h-4 w-4" /> },
    { to: "/officer/applications/YQN-01042", label: "Review Workspace", icon: <FileSearch className="h-4 w-4" /> },
    { to: "/officer/analytics", label: "Analytics", icon: <BarChart3 className="h-4 w-4" /> },
    { to: "/officer/notifications", label: "Notifications", icon: <Bell className="h-4 w-4" /> },
    { to: "/officer/settings", label: "Settings", icon: <Settings className="h-4 w-4" /> },
  ];
  return <RoleShell role="Loan Officer" nav={nav}><Outlet /></RoleShell>;
}
