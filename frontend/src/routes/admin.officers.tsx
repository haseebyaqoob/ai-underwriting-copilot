import { createFileRoute } from "@tanstack/react-router";
import { ComingSoon } from "@/components/yaqeen/coming-soon";

export const Route = createFileRoute("/admin/officers")({ component: OfficersPage });
function OfficersPage() {
  return <ComingSoon eyebrow="Team" title="Loan officers" note="No officer-roster or workload-management endpoint exists on the backend yet. Officers are created directly in the database today (see backend/scripts/seed_dev_data.py) -- there's no admin-facing CRUD for it." />;
}
