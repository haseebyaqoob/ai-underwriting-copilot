import { createFileRoute, Link } from "@tanstack/react-router";
import { SectionHeader, StatCard, WorkflowStageChip, ConfidenceBadge } from "@/components/yaqeen/primitives";
import { CategoryStatusBadge } from "@/components/yaqeen/evidence";
import { fmtPKR } from "@/lib/utils";
import { useApplicantDashboard } from "@/lib/yaqeen-queries";
import { useAuth } from "@/lib/auth";
import {
  ArrowRight,
  Upload,
  Sparkles,
  AlertCircle,
  Wallet,
  FileText,
  FolderOpen,
  ShieldCheck,
  Plus,
} from "lucide-react";

export const Route = createFileRoute("/applicant/dashboard")({ component: ApplicantDashboard });

/**
 * Dashboard redesign (UI/UX only — palette, fonts, and the paper-card /
 * Chip vocabulary are untouched). Three structural changes from the
 * previous layout:
 *
 * 1. The old "Evidence Status" card and the separate orange "Still
 *    needed" alert box are merged into a single higher-priority
 *    "Evidence Readiness" card at the top of the page. They described
 *    the same thing (how ready is my evidence) from two disconnected
 *    widgets; splitting attention across them buried the one number
 *    that matters. The card now also surfaces the completion bar using
 *    `evidenceCompletionPct`, which the API already returned but the
 *    old layout never rendered.
 * 2. The applications list row is rebuilt to actually reflow on small
 *    screens (the old `grid-cols-12` row had no responsive fallback and
 *    would clip on mobile) and gets a stage-colored accent + icon so
 *    the eye has a single strong entry point per row instead of five
 *    same-weight columns.
 * 3. Every section gets its own loading skeleton and empty state
 *    (previously only the two stat cards did) so a slow network never
 *    shows a half-built page.
 */
function ApplicantDashboard() {
  const { user } = useAuth();
  const { data, isLoading, isError, error } = useApplicantDashboard();

  const completionPct = data?.evidenceCompletionPct ?? 0;
  const readinessLabel = completionPct >= 90 ? "Strong" : completionPct >= 50 ? "Building Up" : completionPct > 0 ? "Just Started" : "Not Started";

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-[0.22em] text-muted-foreground">Welcome back</div>
          <h1 className="mt-1 font-serif text-3xl md:text-4xl">
            {user?.name}
            {user?.org ? ` · ${user.org}` : ""}
          </h1>
        </div>
        <div className="flex gap-2">
          <Link
            to="/applicant/upload"
            className="flex items-center gap-2 rounded-lg border border-border bg-card/70 px-4 py-2 text-sm hover:bg-muted"
          >
            <Upload className="h-4 w-4" aria-hidden="true" /> Evidence
          </Link>
          <Link
            to="/applicant/applications/new"
            className="flex items-center gap-2 rounded-lg bg-navy px-4 py-2 text-sm text-paper hover:opacity-95"
          >
            <Plus className="h-4 w-4" aria-hidden="true" /> Start new application
          </Link>
        </div>
      </div>

      {isError && (
        <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          Couldn't load your dashboard: {(error as Error).message}
        </div>
      )}

      {isLoading ? (
        <DashboardSkeleton />
      ) : (
        <>
          {/* Stat row */}
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Active applications" value={String(data?.activeApplicationCount ?? 0)} />
            <StatCard label="Total applications" value={String(data?.totalApplicationCount ?? 0)} />
            <StatCard
              label="Reusable in wallet"
              value={String(data?.walletReusableCount ?? 0)}
              hint={data && data.walletReusableCount > 0 ? "Ready to attach to any application" : undefined}
            />
          </div>

          {/* Unified Evidence Readiness card */}
          {data && data.evidenceSummary.length > 0 && (
            <div className="paper-card p-6">
              <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                    <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" /> Evidence Readiness
                  </div>
                  <h3 className="mt-1 font-serif text-xl text-foreground">{readinessLabel}</h3>
                </div>
                {data.primaryApplicationId && (
                  <Link
                    to="/applicant/upload"
                    className="rounded-lg border border-navy/30 px-3 py-1.5 text-xs font-medium text-navy hover:bg-navy/5"
                  >
                    Review evidence →
                  </Link>
                )}
              </div>

              <div className="mb-5 h-1.5 w-full overflow-hidden rounded-full bg-muted" aria-hidden="true">
                <div
                  className="h-full rounded-full bg-navy transition-[width] duration-700 ease-out"
                  style={{ width: `${completionPct}%` }}
                />
              </div>

              <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
                {data.evidenceSummary.map((line) => (
                  <div key={line.key} className="flex items-center gap-2 text-sm">
                    <span className="text-foreground/80">{line.label}</span>
                    <CategoryStatusBadge label={line.status} />
                  </div>
                ))}
                {data.walletReusableCount > 0 && (
                  <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                    <Wallet className="h-3.5 w-3.5" aria-hidden="true" />
                    {data.walletReusableCount} reusable document{data.walletReusableCount === 1 ? "" : "s"} in wallet
                  </div>
                )}
              </div>

              {data.missingRequiredEvidence.length > 0 && (
                <div className="mt-5 flex flex-wrap items-start gap-3 rounded-lg border border-clay/30 bg-clay/5 p-4">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-clay" aria-hidden="true" />
                  <div className="min-w-0 flex-1 text-sm text-foreground">
                    <span className="font-medium">Still needed:</span>{" "}
                    <span className="text-foreground/80">{data.missingRequiredEvidence.join(", ")}</span>
                  </div>
                  {data.primaryApplicationId && (
                    <Link
                      to="/applicant/upload"
                      className="shrink-0 rounded-lg border border-clay/30 px-3 py-1.5 text-xs text-clay hover:bg-clay/10"
                    >
                      Add evidence →
                    </Link>
                  )}
                </div>
              )}
            </div>
          )}

          <div className="grid gap-6 lg:grid-cols-3">
            <div className="paper-card p-6 lg:col-span-2">
              <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">Your applications</div>
                  <h2 className="font-serif text-3xl leading-tight text-foreground md:text-4xl">In progress</h2>
                </div>
                {data && data.recentApplications.length > 0 && (
                  <Link to="/applicant/applications/" className="mt-2 text-xs text-navy underline underline-offset-4">
                    View all →
                  </Link>
                )}
              </div>

              {data && data.recentApplications.length === 0 && (
                <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border py-12 text-center">
                  <FolderOpen className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
                  <p className="max-w-xs text-sm text-muted-foreground">
                    You haven't started an application yet. It only takes a few minutes to get going.
                  </p>
                  <Link
                    to="/applicant/applications/new"
                    className="mt-1 flex items-center gap-1.5 rounded-lg bg-navy px-4 py-2 text-sm text-paper hover:opacity-95"
                  >
                    <Plus className="h-4 w-4" aria-hidden="true" /> Start your first application
                  </Link>
                </div>
              )}

              <ul className="divide-y divide-border/60">
                {data?.recentApplications.map((a) => (
                  <li key={a.id}>
                    <Link
                      to="/applicant/applications/$id"
                      params={{ id: a.id }}
                      className="-mx-2 flex flex-col gap-3 rounded-lg px-2 py-4 hover:bg-muted/40 sm:flex-row sm:items-center sm:gap-4"
                    >
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-navy/8 text-navy">
                        <FileText className="h-4 w-4" aria-hidden="true" />
                      </span>

                      <span className="min-w-0 flex-1">
                        <span className="block text-xs text-muted-foreground">{a.displayId}</span>
                        <span className="block truncate font-medium text-foreground">{a.businessName}</span>
                      </span>

                      <span className="flex flex-wrap items-center gap-2 sm:justify-end sm:gap-4">
                        <span className="text-sm text-foreground/85 sm:w-24 sm:text-right">{fmtPKR(Number(a.amountPkr))}</span>
                        <WorkflowStageChip stage={a.workflowStage} label={a.workflowStageLabel} />
                        {a.confidence != null ? (
                          <ConfidenceBadge value={a.confidence} />
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                        <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>

            <div className="space-y-6">
              <div className="paper-card p-6">
                <div className="mb-1 flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-navy" aria-hidden="true" />
                  <h3 className="font-serif text-lg text-foreground">Latest AI Activity</h3>
                </div>
                {data && data.aiActivity.length === 0 ? (
                  <p className="mt-3 text-sm text-muted-foreground">
                    Nothing to show yet — this fills in once documents start processing.
                  </p>
                ) : (
                  <ol className="mt-3 space-y-3">
                    {data?.aiActivity.slice(0, 6).map((t, i) => (
                      <li key={i} className="text-sm">
                        <div className="text-xs text-muted-foreground">{new Date(t.at).toLocaleString()}</div>
                        <div className="text-foreground/90">{t.label}</div>
                      </li>
                    ))}
                  </ol>
                )}
              </div>

              <div className="paper-card p-6">
                <SectionHeader eyebrow="Timeline" title="What Yaqeen did" />
                {data && data.activityTimeline.length === 0 && (
                  <p className="text-sm text-muted-foreground">Nothing yet — activity shows up here once you submit an application.</p>
                )}
                <ol className="relative space-y-4 border-l border-border/60 pl-4">
                  {data?.activityTimeline.map((t, i) => (
                    <li key={i} className="relative">
                      <span className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full bg-gold ring-4 ring-background" aria-hidden="true" />
                      <div className="text-xs text-muted-foreground">
                        {new Date(t.at).toLocaleString()} · {t.actorName}
                      </div>
                      <div className="text-sm">{t.label}</div>
                    </li>
                  ))}
                </ol>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading dashboard">
      <div className="grid gap-4 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="paper-card h-20 animate-pulse p-5" />
        ))}
      </div>
      <div className="paper-card h-40 animate-pulse p-6" />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="paper-card h-80 animate-pulse p-6 lg:col-span-2" />
        <div className="space-y-6">
          <div className="paper-card h-40 animate-pulse p-6" />
          <div className="paper-card h-40 animate-pulse p-6" />
        </div>
      </div>
    </div>
  );
}
