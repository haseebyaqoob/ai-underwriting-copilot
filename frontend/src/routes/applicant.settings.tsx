import { createFileRoute, redirect } from "@tanstack/react-router";

/**
 * Section 8 (nav cleanup): the standalone Settings page is gone from the
 * nav and its content now lives on /applicant/profile. This route is
 * kept (rather than deleted) purely so an old bookmark/link doesn't
 * 404 -- it just forwards to the new location.
 */
export const Route = createFileRoute("/applicant/settings")({
  beforeLoad: () => {
    throw redirect({ to: "/applicant/profile" });
  },
});
