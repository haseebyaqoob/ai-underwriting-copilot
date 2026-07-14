import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { SectionHeader } from "@/components/yaqeen/primitives";
import { useAuth } from "@/lib/auth";
import {
  useChangePassword,
  useEvidenceWallet,
  useMarkAllNotificationsRead,
  useNotificationPreferences,
  useUpdateNotificationPreferences,
} from "@/lib/yaqeen-queries";
import { ApiError } from "@/lib/api-client";

export const Route = createFileRoute("/applicant/profile")({ component: ProfilePage });

/**
 * Section 8 (nav cleanup): everything that used to live on the standalone
 * /applicant/settings page (now just a redirect here) is a section on
 * this page instead -- Personal Information, Account Information, Change
 * Password, Security, Notification Preferences, Connected Evidence
 * Wallet, Sign Out -- per the brief's exact list.
 */
function ProfilePage() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const { data: wallet } = useEvidenceWallet();
  const reusableCount = wallet?.filter((w) => w.status === "verified" || w.status === "uploaded").length ?? 0;

  const handleSignOut = () => {
    signOut();
    navigate({ to: "/login", replace: true });
  };

  return (
    <div className="space-y-8">
      <SectionHeader eyebrow="Profile" title={user?.name ?? "Your profile"} sub={user?.org ?? undefined} />

      <Section title="Personal Information">
        <Info label="Full name" value={user?.name ?? "—"} />
        <Info label="Email" value={user?.email ?? "—"} />
      </Section>

      <Section title="Account Information">
        <Info label="Account type" value="Applicant" />
        <Info label="Organization" value={user?.org ?? "Not linked to a lender org"} />
        <Info label="Account ID" value={user?.id ? `${user.id.slice(0, 8)}…` : "—"} />
      </Section>

      <ChangePasswordSection />

      <Section title="Security">
        <Info label="Sign-in method" value="Email & password" />
        <p className="text-sm text-muted-foreground md:col-span-2">
          Changing your password automatically signs out any other active sessions on your account.
        </p>
      </Section>

      <NotificationPreferencesSection />

      <Section title="Connected Evidence Wallet">
        <Info label="Reusable documents stored" value={String(reusableCount)} />
        <p className="text-sm text-muted-foreground md:col-span-2">
          Documents you upload are saved to your Evidence Wallet so you can reuse them on future applications
          without uploading again. Manage them from the Evidence page.
        </p>
      </Section>

      <div className="paper-card p-6">
        <button
          onClick={handleSignOut}
          className="rounded-md border border-border px-4 py-2 text-sm hover:bg-muted"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">{title}</h2>
      <div className="paper-card p-6 grid gap-4 md:grid-cols-2">{children}</div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1">{value}</div>
    </div>
  );
}

function ChangePasswordSection() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const changePassword = useChangePassword();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(false);
    if (next.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    if (next !== confirm) {
      setError("New password and confirmation don't match.");
      return;
    }
    changePassword.mutate(
      { currentPassword: current, newPassword: next },
      {
        onSuccess: () => {
          setSuccess(true);
          setCurrent("");
          setNext("");
          setConfirm("");
        },
        onError: (err) => {
          setError(err instanceof ApiError ? err.message : "Couldn't change your password. Try again.");
        },
      },
    );
  };

  return (
    <div>
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">Change Password</h2>
      <form onSubmit={handleSubmit} className="paper-card p-6 grid gap-4 md:grid-cols-2">
        <label className="text-sm md:col-span-2">
          <span className="mb-1 block text-xs uppercase tracking-wider text-muted-foreground">Current password</span>
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
            className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm"
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs uppercase tracking-wider text-muted-foreground">New password</span>
          <input
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            required
            minLength={8}
            className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm"
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs uppercase tracking-wider text-muted-foreground">Confirm new password</span>
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            minLength={8}
            className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm"
          />
        </label>
        {error && <p className="text-sm text-destructive md:col-span-2">{error}</p>}
        {success && <p className="text-sm text-sage md:col-span-2">Password updated.</p>}
        <div className="md:col-span-2">
          <button
            type="submit"
            disabled={changePassword.isPending}
            className="rounded-md bg-navy px-4 py-2 text-sm text-paper hover:bg-navy-soft disabled:opacity-60"
          >
            {changePassword.isPending ? "Updating…" : "Update password"}
          </button>
        </div>
      </form>
    </div>
  );
}

function NotificationPreferencesSection() {
  const { data } = useNotificationPreferences();
  const update = useUpdateNotificationPreferences();
  const markAllRead = useMarkAllNotificationsRead();
  const enabled = data?.notificationsEnabled ?? true;

  return (
    <div>
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">Notification Preferences</h2>
      <div className="paper-card p-6 flex items-center justify-between gap-4">
        <div>
          <div className="font-medium">In-app notifications</div>
          <div className="text-sm text-muted-foreground">
            Get notified about status changes, document verification, and requests from your loan officer.
          </div>
        </div>
        <button
          onClick={() => update.mutate(!enabled)}
          disabled={update.isPending}
          aria-pressed={enabled}
          className={`relative h-7 w-12 shrink-0 rounded-full transition ${enabled ? "bg-navy" : "bg-muted"}`}
        >
          <span className={`absolute top-1 h-5 w-5 rounded-full bg-paper transition ${enabled ? "left-6" : "left-1"}`} />
        </button>
      </div>
      <button
        onClick={() => markAllRead.mutate()}
        className="mt-3 text-sm text-navy-soft underline underline-offset-4 hover:text-navy"
      >
        Mark all notifications as read
      </button>
    </div>
  );
}
