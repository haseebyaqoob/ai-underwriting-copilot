import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { AuthShell, TextField, PrimaryBtn } from "@/components/auth/AuthShell";
import { useEffect, useState } from "react";
import { ROLE_HOME, useAuth } from "@/lib/auth";

export const Route = createFileRoute("/signup")({
  head: () => ({ meta: [{ title: "Create an account — Yaqeen" }] }),
  component: SignupPage,
});

function SignupPage() {
  const nav = useNavigate();
  const { user, signUp } = useAuth();
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [email, setEmail] = useState("");
  const [org, setOrg] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { if (user) nav({ to: ROLE_HOME[user.role], replace: true }); }, [user, nav]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (!email || !first || pw.length < 8) { setErr("Please complete every field (password ≥ 8 chars)."); return; }
    setBusy(true);
    try {
      const u = await signUp({ name: `${first} ${last}`.trim(), email, org, password: pw });
      nav({ to: ROLE_HOME[u.role], replace: true });
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <AuthShell
      eyebrow="Create account"
      title="Join Yaqeen"
      sub="Set up your workspace in under a minute."
      footer={<>Already have an account? <Link to="/login" className="underline underline-offset-4">Sign in</Link></>}
    >
      <form className="space-y-4" onSubmit={submit}>
        <div className="grid grid-cols-2 gap-3">
          <TextField label="First name" value={first} onChange={setFirst} placeholder="Adnan" />
          <TextField label="Last name" value={last} onChange={setLast} placeholder="Rehman" />
        </div>
        <TextField label="Work email" value={email} onChange={setEmail} placeholder="you@bank.pk" />
        <TextField label="Organization" value={org} onChange={setOrg} placeholder="Al-Madina Kiryana" />
        <TextField label="Password" type="password" value={pw} onChange={setPw} placeholder="At least 8 characters" />
        {err && <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">{err}</div>}
        <PrimaryBtn type="submit">{busy ? "Creating…" : "Create account"}</PrimaryBtn>
        <p className="text-[11px] text-muted-foreground">
          New accounts start with the <span className="text-foreground">Applicant</span> role. By continuing you agree to Yaqeen's Terms and Privacy Notice.
        </p>
      </form>
    </AuthShell>
  );
}
