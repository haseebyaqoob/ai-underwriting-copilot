import { createFileRoute, Link } from "@tanstack/react-router";
import { SectionHeader, StatCard, WorkflowStageChip, ConfidenceBadge } from "@/components/yaqeen/primitives";
import { fmtPKR } from "@/lib/utils";
import { useApplicantDashboard } from "@/lib/yaqeen-queries";
import { useAuth } from "@/lib/auth";
import { ArrowRight, Upload, Sparkles, AlertCircle } from "lucide-react";

export const Route = createFileRoute("/applicant/dashboard")({ component: ApplicantDashboard });

function ApplicantDashboard() {
  const { user } = useAuth();
  const { data, isLoading, isError, error } = useApplicantDashboard();

  return (
    <div className="space-y-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-[0.22em] text-muted-foreground">Welcome back</div>
          <h1 className="mt-1 font-serif text-3xl md:text-4xl">{user?.name}{user?.org ? ` · ${user.org}` : ""}</h1>
        </div>
        <div className="flex gap-2">
          <Link to="/applicant/upload" className="rounded-lg border border-border bg-card/70 px-4 py-2 text-sm hover:bg-muted flex items-center gap-2"><Upload className="h-4 w-4" /> Evidence</Link>
          <Link to="/applicant/applications/new" className="rounded-lg bg-navy px-4 py-2 text-sm text-paper hover:opacity-95">Start new application</Link>
        </div>
      </div>

      {isError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          Couldn't load your dashboard: {(error as Error).message}
        </div>
      )}

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="paper-card h-24 animate-pulse p-5" />)}
        </div>
      ) : data ? (
        <div className="grid gap-4 md:grid-cols-3">
          <StatCard label="Active applications" value={String(data.activeApplicationCount)} />
          <StatCard label="Total applications" value={String(data.totalApplicationCount)} />
          {data.evidenceCompletionPct != null && (
            <StatCard label="Evidence Completion" value={`${data.evidenceCompletionPct}%`} />
          )}
        </div>
      ) : null}

      {data && data.evidenceCompletionPct != null && data.missingRequiredEvidence.length > 0 && (
        <div className="paper-card flex flex-wrap items-center gap-3 border-clay/30 bg-clay/5 p-4">
          <AlertCircle className="h-4 w-4 shrink-0 text-clay" />
          <div className="text-sm text-foreground">
            Missing required evidence: <span className="font-medium">{data.missingRequiredEvidence.join(", ")}</span>
          </div>
          {data.primaryApplicationId && (
            <Link to="/applicant/upload" className="ml-auto shrink-0 rounded-lg border border-clay/30 px-3 py-1.5 text-xs text-clay hover:bg-clay/10">
              Add evidence →
            </Link>
          )}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 paper-card p-6">
          <SectionHeader eyebrow="Your applications" title="In progress" />
          {data && data.recentApplications.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No applications yet. <Link to="/applicant/applications/new" className="underline underline-offset-4">Start your first application</Link>.
            </p>
          )}
          <div className="divide-y divide-border/60">
            {data?.recentApplications.map((a) => (
              <Link key={a.id} to="/applicant/applications/$id" params={{ id: a.id }} className="grid grid-cols-12 items-center gap-3 py-4 hover:bg-muted/40 -mx-2 px-2 rounded-lg">
                <div className="col-span-4">
                  <div className="text-xs text-muted-foreground">{a.displayId}</div>
                  <div className="font-medium">{a.businessName}</div>
                </div>
                <div className="col-span-2 text-sm">{fmtPKR(Number(a.amountPkr))}</div>
                <div className="col-span-3"><WorkflowStageChip stage={a.workflowStage} label={a.workflowStageLabel} /></div>
                <div className="col-span-2">{a.confidence != null ? <ConfidenceBadge value={a.confidence} /> : <span className="text-xs text-muted-foreground">—</span>}</div>
                <div className="col-span-1 flex justify-end text-muted-foreground"><ArrowRight className="h-4 w-4" /></div>
              </Link>
            ))}
          </div>
        </div>

        <div className="space-y-6">
          {data && data.aiActivity.length > 0 && (
            <div className="paper-card p-6">
              <div className="mb-1 flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-navy" />
                <h3 className="font-serif text-lg text-foreground">Latest AI Activity</h3>
              </div>
              <ol className="mt-3 space-y-3">
                {data.aiActivity.slice(0, 6).map((t, i) => (
                  <li key={i} className="text-sm">
                    <div className="text-xs text-muted-foreground">{new Date(t.at).toLocaleString()}</div>
                    <div className="text-foreground/90">{t.label}</div>
                  </li>
                ))}
              </ol>
            </div>
          )}

          <div className="paper-card p-6">
            <SectionHeader eyebrow="Timeline" title="What Yaqeen did" />
            {data && data.activityTimeline.length === 0 && (
              <p className="text-sm text-muted-foreground">Nothing yet — activity shows up here once you submit an application.</p>
            )}
            <ol className="relative border-l border-border/60 pl-4 space-y-4">
              {data?.activityTimeline.map((t, i) => (
                <li key={i} className="relative">
                  <span className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full bg-gold ring-4 ring-background" />
                  <div className="text-xs text-muted-foreground">{new Date(t.at).toLocaleString()} · {t.actorName}</div>
                  <div className="text-sm">{t.label}</div>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>
    </div>
  );
}
