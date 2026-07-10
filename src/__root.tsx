import { createFileRoute, Outlet } from "@tanstack/react-router";
import { RoleShell } from "@/components/layout/RoleShell";
import { LayoutDashboard, FileStack, Upload, Bell, User, Settings, PlusCircle } from "lucide-react";
import { requireRole } from "@/lib/route-guard";

export const Route = createFileRoute("/applicant")({
  beforeLoad: ({ location }) => requireRole("applicant", location.pathname),
  component: ApplicantLayout,
});

function ApplicantLayout() {
  const nav = [
    { to: "/applicant/dashboard", label: "Dashboard", icon: <LayoutDashboard className="h-4 w-4" /> },
    { to: "/applicant/applications", label: "Applications", icon: <FileStack className="h-4 w-4" /> },
    { to: "/applicant/applications/new", label: "New Application", icon: <PlusCircle className="h-4 w-4" /> },
    { to: "/applicant/upload", label: "Evidence", icon: <Upload className="h-4 w-4" /> },
    { to: "/applicant/notifications", label: "Notifications", icon: <Bell className="h-4 w-4" /> },
    { to: "/applicant/profile", label: "Profile", icon: <User className="h-4 w-4" /> },
    { to: "/applicant/settings", label: "Settings", icon: <Settings className="h-4 w-4" /> },
  ];
  return <RoleShell role="Applicant" nav={nav}><Outlet /></RoleShell>;
}
