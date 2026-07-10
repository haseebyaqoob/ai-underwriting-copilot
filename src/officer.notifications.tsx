import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { AuthShell, TextField, PrimaryBtn } from "@/components/auth/AuthShell";

export const Route = createFileRoute("/forgot-password")({ component: ForgotPage });

function ForgotPage() {
  const nav = useNavigate();
  return (
    <AuthShell eyebrow="Recover access" title="Reset your password" sub="We'll send a secure recovery link to your work email." footer={<>Remembered it? <Link to="/login" className="underline underline-offset-4">Sign in</Link></>}>
      <form className="space-y-4" onSubmit={(e)=>{e.preventDefault(); nav({ to: "/otp" });}}>
        <TextField label="Work email" placeholder="you@bank.pk" />
        <PrimaryBtn type="submit">Send recovery link</PrimaryBtn>
      </form>
    </AuthShell>
  );
}
