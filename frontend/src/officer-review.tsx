import { cn } from "@/lib/utils";
import type { ReactNode } from "react";
import type { AppStatus } from "@/lib/utils";
import type { WorkflowStageKey } from "@/lib/yaqeen-types";

export function Chip({ children, tone = "muted", className }: { children: ReactNode; tone?: "muted" | "gold" | "navy" | "sage" | "clay" | "danger"; className?: string }) {
  const map = {
    muted: "bg-muted text-muted-foreground border-border",
    gold: "bg-gold-soft/60 text-navy border-gold/30",
    navy: "bg-navy text-paper border-navy",
    sage: "bg-sage/15 text-sage border-sage/30",
    clay: "bg-clay/15 text-clay border-clay/30",
    danger: "bg-destructive/10 text-destructive border-destructive/30",
  } as const;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium tracking-tight", map[tone], className)}>
      {children}
    </span>
  );
}

export function StatusChip({ status }: { status: AppStatus }) {
  const map: Record<AppStatus, { label: string; tone: Parameters<typeof Chip>[0]["tone"] }> = {
    draft: { label: "Draft", tone: "muted" },
    submitted: { label: "Submitted", tone: "navy" },
    in_review: { label: "In Review", tone: "gold" },
    needs_docs: { label: "Needs Docs", tone: "clay" },
    approved: { label: "Approved", tone: "sage" },
    rejected: { label: "Rejected", tone: "danger" },
    withdrawn: { label: "Withdrawn", tone: "muted" },
  };
  const s = map[status];
  return <Chip tone={s.tone}>{s.label}</Chip>;
}

/** Dashboard workflow redesign: the finer-grained stage
 * (workflow_stage_service.py) rather than the raw 7-value ApplicationStatus
 * -- distinct from StatusChip above (still used where the raw status is
 * what matters, e.g. officer-side views this session didn't touch). */
export function WorkflowStageChip({ stage, label }: { stage: WorkflowStageKey; label: string }) {
  const toneMap: Record<WorkflowStageKey, Parameters<typeof Chip>[0]["tone"]> = {
    draft: "muted",
    documents_processing: "gold",
    evidence_verified: "sage",
    ai_underwriting: "navy",
    officer_review: "navy",
    additional_evidence_requested: "clay",
    approved: "sage",
    rejected: "danger",
    withdrawn: "muted",
  };
  return <Chip tone={toneMap[stage]}>{label}</Chip>;
}

export function ConfidenceBadge({ value }: { value: number }) {
  const tone = value >= 90 ? "sage" : value >= 75 ? "gold" : "clay";
  return <Chip tone={tone}>{value}% confidence</Chip>;
}

export function RiskIndicator({ level }: { level: "low" | "moderate" | "elevated" | "high" }) {
  const map = { low: { t: "sage", l: "Low risk" }, moderate: { t: "gold", l: "Moderate" }, elevated: { t: "clay", l: "Elevated" }, high: { t: "danger", l: "High risk" } } as const;
  const m = map[level];
  return <Chip tone={m.t as any}>{m.l}</Chip>;
}

export function SectionHeader({ eyebrow, title, sub }: { eyebrow?: string; title: string; sub?: string }) {
  return (
    <div className="mb-8">
      {eyebrow && <div className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">{eyebrow}</div>}
      <h2 className="font-serif text-3xl leading-tight text-foreground md:text-4xl">{title}</h2>
      {sub && <p className="mt-2 max-w-2xl text-sm text-muted-foreground md:text-base">{sub}</p>}
    </div>
  );
}

export function StatCard({ label, value, delta, hint }: { label: string; value: string; delta?: string; hint?: string }) {
  return (
    <div className="paper-card p-5">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-2 flex items-baseline gap-2">
        <div className="font-serif text-2xl">{value}</div>
        {delta && <div className="text-xs text-sage">{delta}</div>}
      </div>
      {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}

export function ScoreRing({ value, size = 160 }: { value: number; size?: number }) {
  const r = size / 2 - 10;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(1, (value - 300) / (850 - 300)));
  const off = c * (1 - pct);
  const tone = value >= 720 ? "var(--sage)" : value >= 640 ? "var(--gold)" : "var(--clay)";
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="var(--border)" strokeWidth={8} fill="none" />
        <circle cx={size / 2} cy={size / 2} r={r} stroke={tone} strokeWidth={8} fill="none"
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off} style={{ transition: "stroke-dashoffset 1.2s ease" }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-xs uppercase tracking-wider text-muted-foreground">Yaqeen Score</div>
        <div className="font-serif text-4xl">{value}</div>
        <div className="text-xs text-muted-foreground">of 850</div>
      </div>
    </div>
  );
}
