import { createFileRoute } from "@tanstack/react-router";
import { ComingSoon } from "@/components/yaqeen/coming-soon";

export const Route = createFileRoute("/admin/analytics")({ component: A });
function A() {
  return <ComingSoon eyebrow="Analytics" title="Platform analytics" note="No pipeline-stage or time-series analytics endpoint exists on the backend yet. The real portfolio numbers that do exist are on the Admin Dashboard page." />;
}
