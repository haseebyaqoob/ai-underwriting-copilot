import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { Logo } from "@/components/yaqeen/Logo";

export function AuthShell({ eyebrow, title, sub, children, footer }: { eyebrow?: string; title: string; sub?: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="min-h-screen grid md:grid-cols-2">
      <div className="hidden md:flex ink-gradient relative overflow-hidden p-12 flex-col">
        <Logo className="text-paper [&_span]:text-paper" />
        <div className="absolute inset-0 opacity-40 bg-[radial-gradient(circle_at_20%_10%,var(--gold)_0%,transparent_40%)]" />
        <div className="mt-auto relative">
          <div className="text-xs uppercase tracking-[0.22em] text-paper/60">Yaqeen · Underwriting Copilot</div>
          <h2 className="mt-3 font-serif text-4xl leading-tight text-paper">Evidence-based credit for Pakistan's SMEs.</h2>
          <p className="mt-3 max-w-md text-paper/75 text-sm">Trusted by loan officers to turn khata, wallet statements and utility bills into explainable underwriting decisions.</p>
        </div>
      </div>
      <div className="flex flex-col items-center justify-center p-6 md:p-12">
        <div className="w-full max-w-sm">
          <div className="md:hidden mb-8"><Logo /></div>
          {eyebrow && <div className="text-xs uppercase tracking-[0.22em] text-muted-foreground">{eyebrow}</div>}
          <h1 className="mt-2 font-serif text-3xl">{title}</h1>
          {sub && <p className="mt-2 text-sm text-muted-foreground">{sub}</p>}
          <div className="mt-8">{children}</div>
          {footer && <div className="mt-8 text-sm text-muted-foreground">{footer}</div>}
          <div className="mt-10 text-xs text-muted-foreground">
            <Link to="/" className="hover:text-foreground">← Back to yaqeen.pk</Link>
          </div>
        </div>
      </div>
    </div>
  );
}

export function TextField({ label, type = "text", placeholder, value, onChange }: { label: string; type?: string; placeholder?: string; value?: string; onChange?: (v: string)=>void }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-foreground/80">{label}</span>
      <input
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={(e)=>onChange?.(e.target.value)}
        className="w-full rounded-lg border border-input bg-card/70 px-3 py-2.5 text-sm outline-none transition focus:border-navy focus:ring-2 focus:ring-gold/40"
      />
    </label>
  );
}

export function PrimaryBtn({ children, onClick, type = "button" }: { children: ReactNode; onClick?: ()=>void; type?: "button" | "submit" }) {
  return <button type={type} onClick={onClick} className="w-full rounded-lg bg-navy px-4 py-2.5 text-sm text-paper transition hover:opacity-95 shadow-elegant">{children}</button>;
}
