import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { fmtPKR } from "@/lib/utils";
import { useApplicantApplication, useSubmitApplication, useWithdrawApplication } from "@/lib/yaqeen-queries";
import { SectionHeader, WorkflowStageChip, ConfidenceBadge, ScoreRing, Chip } from "@/components/yaqeen/primitives";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertTriangle, CheckCircle2, Circle, Sparkles } from "lucide-react";

export const Route = createFileRoute("/applicant/applications/$id")({ component: AppDetail });

function DetailField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm text-foreground">{value}</div>
    </div>
  );
}

function AppDetail() {
  const { id } = Route.useParams();
  const { data: app, isLoading, isError, error } = useApplicantApplication(id);
  const submit = useSubmitApplication();
  const withdraw = useWithdrawApplication();
  const [actionError, setActionError] = useState<string | null>(null);

  if (isLoading) return <div className="paper-card h-64 animate-pulse" />;
  if (isError || !app) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
        Couldn't load this application: {(error as Error)?.message ?? "not found"}
      </div>
    );
  }

  const canSubmit = app.status === "draft";
  const canWithdraw = app.status === "draft" || app.status === "submitted" || app.status === "needs_docs";

  async function runAction(fn: () => Promise<unknown>) {
    setActionError(null);
    try {
      await fn();
    } catch (e) {
      setActionError((e as Error).message);
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs text-muted-foreground">{app.displayId} · {app.city}</div>
          <h1 className="mt-1 font-serif text-3xl">{app.businessName}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <WorkflowStageChip stage={app.workflowStage} label={app.workflowStageLabel} />
            {app.confidence != null && <ConfidenceBadge value={app.confidence} />}
            {app.officerName && <Chip tone="muted">Officer · {app.officerName}</Chip>}
            <Chip tone="muted">{fmtPKR(Number(app.amountPkr))} · {app.purpose}</Chip>
          </div>
          {(app.workflowStage === "documents_processing" || app.workflowStage === "evidence_verified" || app.workflowStage === "ai_underwriting") && (
            <Link
              to="/applicant/applications/$id/processing"
              params={{ id: app.id }}
              className="mt-2 inline-flex items-center gap-1.5 text-xs text-navy underline underline-offset-4"
            >
              <Sparkles className="h-3 w-3" /> View live AI processing status
            </Link>
          )}
        </div>
        <div className="flex items-center gap-3">
          {app.score != null && <div className="paper-card p-4"><ScoreRing value={app.score} size={140} /></div>}
        </div>
      </div>

      <div className="paper-card p-6">
        <SectionHeader eyebrow="Business & Loan" title="Application details" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <DetailField label="Business type" value={app.businessType ?? "—"} />
          <DetailField label="Owner" value={app.ownerName ?? "—"} />
          <DetailField label="Years operating / employees" value={`${app.yearsOperating ?? "—"} yrs · ${app.employeeCount ?? "—"}`} />
          <DetailField label="Registration" value={app.registrationStatus === "registered" ? "Registered" : "Unregistered"} />
          {(app.ntn || app.strn) && <DetailField label="NTN / STRN" value={`${app.ntn ?? "—"} / ${app.strn ?? "—"}`} />}
          <DetailField label="Tenure" value={`${app.tenorMonths ?? "—"} months`} />
          <DetailField label="Repayment preference" value={app.preferredRepayment ?? "—"} />
          {(app.monthlyEstimatedRevenuePkr || app.monthlyEstimatedExpensesPkr) && (
            <DetailField
              label="Applicant's own estimate"
              value={`${app.monthlyEstimatedRevenuePkr ? fmtPKR(Number(app.monthlyEstimatedRevenuePkr)) : "—"} rev / ${app.monthlyEstimatedExpensesPkr ? fmtPKR(Number(app.monthlyEstimatedExpensesPkr)) : "—"} exp`}
            />
          )}
        </div>
      </div>

      {(canSubmit || canWithdraw) && (
        <div className="paper-card p-4 flex flex-wrap items-center gap-3">
          {canSubmit && (
            <Button
              disabled={submit.isPending}
              onClick={() => runAction(() => submit.mutateAsync(app.id))}
            >
              {submit.isPending ? "Submitting…" : "Submit application"}
            </Button>
          )}
          {canWithdraw && (
            <Button
              variant="outline"
              disabled={withdraw.isPending}
              onClick={() => runAction(() => withdraw.mutateAsync(app.id))}
            >
              {withdraw.isPending ? "Withdrawing…" : "Withdraw application"}
            </Button>
          )}
          {canSubmit && (
            <span className="text-xs text-muted-foreground">
              Still a draft — upload your documents, then submit when ready. Officers can't see it until then.
            </span>
          )}
        </div>
      )}
      {actionError && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Couldn't complete that action</AlertTitle>
          <AlertDescription>{actionError}</AlertDescription>
        </Alert>
      )}

      {app.assessment?.status === "insufficient_evidence" && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Your application is almost ready</AlertTitle>
          <AlertDescription>
            <p className="mt-1">To generate an AI underwriting assessment, we recommend:</p>
            <ul className="mt-2 space-y-1.5">
              {app.assessment.readinessChecklist.map((item) => (
                <li key={item.key} className="flex items-start gap-2">
                  {item.met ? (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-sage" />
                  ) : (
                    <Circle className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                  )}
                  <span className={item.met ? "text-foreground/70 line-through decoration-muted-foreground/40" : "text-foreground"}>
                    {item.label} <span className="text-xs text-muted-foreground">— {item.detail}</span>
                  </span>
                </li>
              ))}
            </ul>
            <Link
              to="/applicant/upload"
              className="mt-3 inline-flex items-center gap-1 text-sm text-navy underline underline-offset-4"
            >
              Go to Evidence
            </Link>
          </AlertDescription>
        </Alert>
      )}

      {app.revenue && (app.revenue.verifiedFloorMonthlyPkr != null || app.revenue.blendedEstimateHighMonthlyPkr != null) && (
        <div className="paper-card p-6">
          <SectionHeader
            eyebrow="Revenue estimate"
            title={`Based on ${app.revenue.monthsOfData.toFixed(1)} month(s) / ${app.revenue.weeksOfData.toFixed(1)} week(s) of data`}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-border/60 p-4">
              <div className="text-xs uppercase tracking-wide text-muted-foreground">Verified floor (wallet only)</div>
              <div className="mt-1 text-2xl font-serif">
                {app.revenue.verifiedFloorMonthlyPkr != null ? fmtPKR(Number(app.revenue.verifiedFloorMonthlyPkr)) + "/mo" : "Not enough data yet"}
              </div>
            </div>
            <div className="rounded-lg border border-border/60 p-4">
              <div className="text-xs uppercase tracking-wide text-muted-foreground">Blended estimate range</div>
              <div className="mt-1 text-2xl font-serif">
                {app.revenue.blendedEstimateLowMonthlyPkr != null && app.revenue.blendedEstimateHighMonthlyPkr != null
                  ? `${fmtPKR(Number(app.revenue.blendedEstimateLowMonthlyPkr))} – ${fmtPKR(Number(app.revenue.blendedEstimateHighMonthlyPkr))}/mo`
                  : "Not enough data yet"}
              </div>
            </div>
          </div>
          {app.revenue.plausibilityFlag && (
            <p className="mt-3 text-sm text-amber-700">{app.revenue.plausibilityNote}</p>
          )}
        </div>
      )}

      {app.assessment?.status === "scored" && (
        <div className="paper-card p-6">
          <SectionHeader eyebrow="How this score was built" title="Scoring factors" />
          <div className="space-y-3">
            {app.assessment.factors.map((f) => (
              <div key={f.key} className="flex items-center justify-between gap-4 border-b border-border/40 pb-3 last:border-0">
                <div>
                  <div className="text-sm font-medium">{f.label} <span className="text-xs text-muted-foreground">({f.weightPct}% weight)</span></div>
                  <div className="text-xs text-muted-foreground">{f.explanation}</div>
                </div>
                <div className="text-sm font-serif shrink-0">{f.factorScore.toFixed(0)}/100</div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted-foreground">{app.assessment.debtExposure.note}</p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 paper-card p-6">
          <SectionHeader eyebrow="Evidence" title="Documents contributing to this assessment" />
          {app.evidence.length === 0 ? (
            <p className="text-sm text-muted-foreground">No documents processed yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wider text-muted-foreground">
                <tr><th className="py-2">Type</th><th className="py-2">Entries</th><th className="py-2">Date range</th><th className="py-2">Confidence</th></tr>
              </thead>
              <tbody className="[&_tr]:border-t [&_tr]:border-border/60">
                {app.evidence.map((e) => (
                  <tr key={e.sourceType}>
                    <td className="py-2">{e.sourceType}</td>
                    <td className="py-2">{e.transactionCount}</td>
                    <td className="py-2 text-muted-foreground">{e.dateRangeStart ?? "—"} to {e.dateRangeEnd ?? "—"}</td>
                    <td className="py-2"><ConfidenceBadge value={e.avgConfidence} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="paper-card p-6">
          <SectionHeader eyebrow="Timeline" title="Underwriting events" />
          {app.timeline.length === 0 && <p className="text-sm text-muted-foreground">No activity yet.</p>}
          <ol className="relative border-l border-border/60 pl-4 space-y-4">
            {app.timeline.map((t, i) => (
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
  );
}
