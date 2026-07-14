import { createFileRoute } from "@tanstack/react-router";
import { ComingSoon } from "@/components/yaqeen/coming-soon";

export const Route = createFileRoute("/officer/analytics")({ component: A });
function A() {
  return <ComingSoon eyebrow="Analytics" title="Portfolio analytics" note="No analytics endpoint exists on the backend yet for officer-level trend data. officer/dashboard's real status_breakdown is available from the Dashboard page; deeper trend charts need a new backend module." />;
}
