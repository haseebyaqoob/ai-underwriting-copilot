import { createFileRoute } from "@tanstack/react-router";
import { NotificationsPage } from "@/components/yaqeen/notifications-page";

export const Route = createFileRoute("/applicant/notifications")({ component: N });
function N() {
  return <NotificationsPage role="applicant" />;
}
