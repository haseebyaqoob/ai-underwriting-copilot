import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/applicant/")({
  beforeLoad: () => { throw redirect({ to: "/applicant/dashboard", replace: true }); },
});
