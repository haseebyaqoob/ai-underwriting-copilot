import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { AuthShell, TextField, PrimaryBtn } from "@/components/auth/AuthShell";
import { useEffect, useState } from "react";
import { DEMO_ACCOUNTS, ROLE_HOME, ROLE_LABEL, useAuth } from "@/lib/auth";
import { User, Briefcase, ShieldCheck } from "lucide-react";

export const Route = createFileRoute("/login")({
  head: () => ({ meta: [{ title: "Sign in — Yaqeen" }] }),
  component: LoginPage,
});

const ROLE_ICON = {
  applicant: <User className="h-4 w-4" />,
  loan_officer: <Briefcase className="h-4 w-4" />,
  admin: <ShieldCheck className="h-4 w-4" />,
} as const;

function LoginPage() {
  const nav = useNavigate();
  const { user, signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (user) nav({ to: ROLE_HOME[user.role], replace: true });
  }, [user, nav]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null); setBusy(true);
    try {
      const u = await signIn(email, pw);
      nav({ to: ROLE_HOME[u.role], replace: true });
    } catch (e) {
      setErr((e as Error).message);
    } finally { setBusy(false); }
  };

  const fillDemo = (email: string, password: string) => { setEmail(email); setPw(password); setErr(null); };

  return (
    <AuthShell
      eyebrow="Welcome back"
      title="Sign in to Yaqeen"
      sub="Continue where you left off."
      footer={<>New to Yaqeen? <Link to="/signup" className="underline underline-offset-4">Create an account</Link></>}
    >
      <form className="space-y-4" onSubmit={submit}>
        <TextField label="Work email" value={email} onChange={setEmail} placeholder="you@bank.pk" />
        <TextField label="Password" type="password" value={pw} onChange={setPw} />
        {err && <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">{err}</div>}
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <label className="flex items-center gap-2"><input type="checkbox" defaultChecked className="rounded border-input" /> Keep me signed in</label>
          <Link to="/forgot-password" className="hover:text-foreground">Forgot?</Link>
        </div>
        <PrimaryBtn type="submit">{busy ? "Signing in…" : "Continue"}</PrimaryBtn>
      </form>

      <div className="mt-8">
        <div className="flex items-center gap-3 text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          <span className="h-px flex-1 bg-border" />
          Demo accounts (dev only)
          <span className="h-px flex-1 bg-border" />
        </div>
        <div className="mt-3 space-y-2">
          {DEMO_ACCOUNTS.map((a) => (
            <button
              key={a.email}
              type="button"
              onClick={() => fillDemo(a.email, a.password)}
              className="group flex w-full items-center gap-3 rounded-lg border border-border bg-card/60 px-3 py-2.5 text-left transition hover:border-navy/40 hover:bg-muted"
            >
              <span className="grid h-8 w-8 place-items-center rounded-md bg-navy text-paper">{ROLE_ICON[a.role]}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium text-foreground">{ROLE_LABEL[a.role]}</span>
                <span className="block truncate text-[11px] text-muted-foreground">{a.email} · {a.blurb}</span>
              </span>
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground opacity-0 transition group-hover:opacity-100">Autofill</span>
            </button>
          ))}
        </div>
      </div>
    </AuthShell>
  );
}
