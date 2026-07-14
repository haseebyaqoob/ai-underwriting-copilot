import { createFileRoute } from "@tanstack/react-router";
import { ComingSoon } from "@/components/yaqeen/coming-soon";

export const Route = createFileRoute("/admin/models")({ component: Models });
function Models() {
  return <ComingSoon eyebrow="AI" title="Model usage" note="No usage/cost-tracking endpoint exists on the backend yet for the Gemini provider. Module 5 built the GeminiProvider itself, but not usage telemetry -- that's a real gap, not a UI oversight." />;
}
