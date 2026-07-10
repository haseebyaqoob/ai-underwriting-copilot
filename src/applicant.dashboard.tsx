import { createFileRoute } from "@tanstack/react-router";
import { ComingSoon } from "@/components/yaqeen/coming-soon";

export const Route = createFileRoute("/applicant/notifications")({ component: N });
function N() {
  return <ComingSoon eyebrow="Inbox" title="Notifications" note="No notifications endpoint exists on the backend yet — this page showed static mock data before and now shows an honest empty state instead." />;
}
