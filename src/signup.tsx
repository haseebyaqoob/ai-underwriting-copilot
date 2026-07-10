import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/officer/")({
  beforeLoad: () => { throw redirect({ to: "/officer/dashboard", replace: true }); },
});
