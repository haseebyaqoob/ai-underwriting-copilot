import { createFileRoute } from "@tanstack/react-router";
import { ComingSoon } from "@/components/yaqeen/coming-soon";

export const Route = createFileRoute("/admin/audit")({ component: Audit });
function Audit() {
  return <ComingSoon eyebrow="Compliance" title="Audit logs" note="No audit-log table or endpoint exists on the backend yet. Application state changes are visible per-application on the Timeline section of an application's detail page, but there's no cross-application audit trail." />;
}
