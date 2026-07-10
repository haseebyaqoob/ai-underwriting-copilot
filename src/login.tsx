import { createFileRoute, Link } from "@tanstack/react-router";
import { ShieldAlert } from "lucide-react";
import { useAuth, ROLE_HOME } from "@/lib/auth";

export const Route = createFileRoute("/unauthorized")({
  head: () => ({ meta: [{ title: "Access denied — Yaqeen" }, { name: "robots", content: "noindex" }] }),
  component: UnauthorizedPage,
});

function UnauthorizedPage() {
  const { user, signOut } = useAuth();
  const home = user ? ROLE_HOME[user.role] : "/login";
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-gold-soft/60 text-navy">
          <ShieldAlert className="h-6 w-6" />
        </div>
        <div className="mt-6 font-serif text-6xl text-navy">403</div>
        <h1 className="mt-2 font-serif text-2xl">You don't have access to this workspace.</h1>
        <p className="mt-3 text-sm text-muted-foreground">
          {user
            ? <>Signed in as <span className="text-foreground">{user.email}</span>. This area is reserved for a different role.</>
            : "Please sign in to continue."}
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-2">
          <Link to={home} className="rounded-md bg-navy px-4 py-2 text-sm text-paper hover:opacity-90">
            {user ? "Go to my dashboard" : "Sign in"}
          </Link>
          {user && (
            <button onClick={signOut} className="rounded-md border border-input px-4 py-2 text-sm hover:bg-accent">
              Sign out
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
