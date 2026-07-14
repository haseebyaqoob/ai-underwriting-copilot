import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { AuthShell, PrimaryBtn } from "@/components/auth/AuthShell";
import { useState } from "react";

export const Route = createFileRoute("/otp")({ component: OtpPage });

function OtpPage() {
  const nav = useNavigate();
  const [vals, setVals] = useState(["", "", "", "", "", ""]);
  return (
    <AuthShell eyebrow="Verify" title="Enter the 6-digit code" sub="We sent it to your work email. It expires in 10 minutes.">
      <form className="space-y-6" onSubmit={(e)=>{e.preventDefault(); nav({ to: "/login" });}}>
        <div className="flex justify-between gap-2">
          {vals.map((v, i) => (
            <input key={i} inputMode="numeric" maxLength={1} value={v}
              onChange={(e)=>{ const n=[...vals]; n[i]=e.target.value.slice(-1); setVals(n); }}
              className="h-14 w-12 rounded-lg border border-input bg-card/70 text-center font-serif text-2xl outline-none focus:border-navy focus:ring-2 focus:ring-gold/40" />
          ))}
        </div>
        <PrimaryBtn type="submit">Verify & continue</PrimaryBtn>
        <div className="text-center text-xs text-muted-foreground">Didn't get it? <button type="button" className="underline underline-offset-4">Resend</button></div>
      </form>
    </AuthShell>
  );
}
