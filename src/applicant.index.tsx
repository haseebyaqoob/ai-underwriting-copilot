import { createFileRoute, Link } from "@tanstack/react-router";
import { AuthShell, PrimaryBtn } from "@/components/auth/AuthShell";

export const Route = createFileRoute("/session-expired")({ component: SessionExpired });

function SessionExpired() {
  return (
    <AuthShell eyebrow="Security" title="Your session expired" sub="For your protection, Yaqeen signed you out after inactivity.">
      <div className="space-y-3">
        <Link to="/login"><PrimaryBtn>Sign in again</PrimaryBtn></Link>
        <Link to="/" className="block text-center text-sm text-muted-foreground hover:text-foreground">Back to home</Link>
      </div>
    </AuthShell>
  );
}
