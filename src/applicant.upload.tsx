import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { fmtPKR } from "@/lib/utils";
import {
  useOfficerApplication,
  useStartReview,
  useApproveApplication,
  useRejectApplication,
  useRequestDocs,
  useReopenApplication,
} from "@/lib/yaqeen-queries";
import type { DecisionReasonCode } from "@/lib/yaqeen-types";
import { SectionHeader, StatusChip, ConfidenceBadge, ScoreRing, Chip, StatCard } from "@/components/yaqeen/primitives";
import { ShieldCheck, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

export const Route = createFileRoute("/officer/applications/$id")({ component: OfficerAppDetail });

const REASON_CODES: { value: DecisionReasonCode; label: string }[] = [
  { value: "strong_cashflow_evidence", label: "Strong cashflow evidence" },
  { value: "adequate_evidence_coverage", label: "Adequate evidence coverage" },
  { value: "acceptable_debt_service_ratio", label: "Acceptable debt-service ratio" },
  { value: "insufficient_evidence", label: "Insufficient evidence" },
  { value: "high_risk_inconsistency", label: "High-risk inconsistency" },
  { value: "debt_service_coverage_low", label: "Debt-service coverage too low" },
  { value: "income_instability", label: "Income instability" },
  { value: "missing_wallet_statement", label: "Missing wallet statement" },
  { value: "missing_khata", label: "Missing khata" },
  { value: "missing_utility_bill", label: "Missing utility bill" },
  { value: "missing_cnic", label: "Missing/invalid CNIC" },
  { value: "unclear_document_quality", label: "Unclear document quality" },
  { value: "other", label: "Other (see note)" },
];

function DecisionPanel({ applicationId }: { applicationId: string }) {
  const [reasonCode, setReasonCode] = useState<DecisionReasonCode | "">("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const approve = useApproveApplication();
  const reject = useRejectApplication();
  const requestDocs = useRequestDocs();

  const pending = approve.isPending || reject.isPending || requestDocs.isPending;

  async function run(mutate: (v: { applicationId: string; body: unknown }) => Promise<unknown>) {
    if (!reasonCode) {
      setError("Pick a reason code first — every decision needs one.");
      return;
    }
    setError(null);
    try {
      await mutate({ applicationId, body: { reasonCode, note: note || undefined } });
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="paper-card p-6 space-y-4">
      <SectionHeader eyebrow="Decision" title="Approve, reject, or request more documents" />
      <div>
        <label className="text-xs uppercase tracking-wide text-muted-foreground">Reason code (required)</label>
        <Select value={reasonCode} onValueChange={(v) => setReasonCode(v as DecisionReasonCode)}>
          <SelectTrigger className="mt-1"><SelectValue placeholder="Select a reason…" /></SelectTrigger>
          <SelectContent>
            {REASON_CODES.map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div>
        <label className="text-xs uppercase tracking-wide text-muted-foreground">Note (optional)</label>
        <Textarea className="mt-1" value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
      </div>
      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <div className="flex flex-wrap gap-3">
        <Button disabled={pending} onClick={() => run(approve.mutateAsync)}>Approve</Button>
        <Button disabled={pending} variant="destructive" onClick={() => run(reject.mutateAsync)}>Reject</Button>
        <Button disabled={pending} variant="outline" onClick={() => run(requestDocs.mutateAsync)}>Request more docs</Button>
      </div>
    </div>
  );
}

function OfficerAppDetail() {
  const { id } = Route.useParams();
  const { data: app, isLoading, isError, error } = useOfficerApplication(id);
  const startReview = useStartReview();
  const reopen = useReopenApplication();
  const [actionError, setActionError] = useState<string | null>(null);

  if (isLoading) return <div className="paper-card h-64 animate-pulse" />;
  if (isError || !app) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
        Couldn't load this application: {(error as Error)?.message ?? "not found"}
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs text-muted-foreground">{app.displayId} · {app.city}</div>
          <h1 className="mt-1 font-serif text-3xl">{app.businessName}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <StatusChip status={app.status} />
            {app.confidence != null && <ConfidenceBadge value={app.confidence} />}
            <Chip tone="muted">Applicant · {app.applicantName}</Chip>
            <Chip tone="muted">{fmtPKR(Number(app.amountPkr))} · {app.purpose}</Chip>
            {app.cnicNumber && (
              <Chip tone="muted"><ShieldCheck className="mr-1 inline h-3 w-3" />CNIC {app.cnicNumber}</Chip>
            )}
          </div>
        </div>
        {app.score != null && <div className="paper-card p-4"><ScoreRing value={app.score} size={140} /></div>}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {app.status === "submitted" && (
          <Button
            disabled={startReview.isPending}
            onClick={async () => {
              setActionError(null);
              try { await startReview.mutateAsync({ applicationId: app.id }); }
              catch (e) { setActionError((e as Error).message); }
            }}
          >
            {startReview.isPending ? "Starting…" : "Start review"}
          </Button>
        )}
        {(app.status === "approved" || app.status === "rejected") && (
          <ReopenButton applicationId={app.id} onError={setActionError} pending={reopen.isPending} mutate={reopen.mutateAsync} />
        )}
      </div>
      {actionError && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{actionError}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <StatCard label="Owner" value={app.ownerName ?? "—"} />
        <StatCard label="Years operating" value={app.yearsOperating != null ? String(app.yearsOperating) : "—"} />
        <StatCard label="Employees" value={app.employeeCount != null ? String(app.employeeCount) : "—"} />
      </div>

      {app.assessment?.status === "insufficient_evidence" && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Insufficient evidence to generate an assessment</AlertTitle>
          <AlertDescription>
            <ul className="mt-1 list-disc pl-5 space-y-1">
              {app.assessment.reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
            {app.assessment.missingDocumentTypes.length > 0 && (
              <p className="mt-2">Request: <span className="font-medium">{app.assessment.missingDocumentTypes.join(", ")}</span></p>
            )}
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 paper-card p-6">
          <SectionHeader eyebrow="Revenue" title="Estimated from evidence_transactions" />
          {app.revenue ? (
            <div className="grid gap-4 sm:grid-cols-2 text-sm">
              <div>
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Verified floor (wallet)</div>
                <div className="mt-1 text-xl font-serif">
                  {app.revenue.verifiedFloorMonthlyPkr != null ? fmtPKR(Number(app.revenue.verifiedFloorMonthlyPkr)) + "/mo" : "n/a"}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Blended range</div>
                <div className="mt-1 text-xl font-serif">
                  {app.revenue.blendedEstimateLowMonthlyPkr != null && app.revenue.blendedEstimateHighMonthlyPkr != null
                    ? `${fmtPKR(Number(app.revenue.blendedEstimateLowMonthlyPkr))} – ${fmtPKR(Number(app.revenue.blendedEstimateHighMonthlyPkr))}/mo`
                    : "n/a"}
                </div>
              </div>
              <div className="sm:col-span-2 text-muted-foreground">
                Based on {app.revenue.monthsOfData.toFixed(1)} months across: {app.revenue.sourceTypesUsed.join(", ") || "—"}
              </div>
              {app.revenue.plausibilityFlag && <div className="sm:col-span-2 text-amber-700">{app.revenue.plausibilityNote}</div>}
            </div>
          ) : <p className="text-sm text-muted-foreground">No evidence yet.</p>}
        </div>
        <div className="paper-card p-6">
          <SectionHeader eyebrow="Consistency checks" title="Officer view (full detail)" />
          {app.consistencyChecks.length === 0 ? (
            <p className="text-sm text-muted-foreground">No checks run yet.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {app.consistencyChecks.map((c) => (
                <li key={c.checkId} className="flex items-start gap-2">
                  <span className={c.passed ? "text-emerald-600" : "text-amber-700"}>{c.passed ? "✓" : "!"}</span>
                  <span className="text-muted-foreground">{c.message}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {app.assessment?.status === "scored" && (
        <div className="paper-card p-6">
          <SectionHeader eyebrow="Explainability" title="Score factor breakdown" />
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

      {app.evidence.length > 0 && (
        <div className="paper-card overflow-hidden">
          <div className="border-b border-border px-6 py-4"><h3 className="font-serif text-xl">Evidence coverage</h3></div>
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-muted-foreground">
              <tr><th className="px-6 py-3">Type</th><th className="px-6 py-3">Entries</th><th className="px-6 py-3">Date range</th><th className="px-6 py-3">Confidence</th></tr>
            </thead>
            <tbody className="[&_tr]:border-t [&_tr]:border-border/60">
              {app.evidence.map((e) => (
                <tr key={e.sourceType}>
                  <td className="px-6 py-3">{e.sourceType}</td>
                  <td className="px-6 py-3">{e.transactionCount}</td>
                  <td className="px-6 py-3 text-muted-foreground">{e.dateRangeStart ?? "—"} to {e.dateRangeEnd ?? "—"}</td>
                  <td className="px-6 py-3"><ConfidenceBadge value={e.avgConfidence} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {app.status === "in_review" && <DecisionPanel applicationId={app.id} />}

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
  );
}

function ReopenButton({
  applicationId, onError, pending, mutate,
}: { applicationId: string; onError: (e: string | null) => void; pending: boolean; mutate: (v: { applicationId: string; body: unknown }) => Promise<unknown> }) {
  const [reasonCode, setReasonCode] = useState<DecisionReasonCode | "">("");
  return (
    <div className="flex items-center gap-2">
      <Select value={reasonCode} onValueChange={(v) => setReasonCode(v as DecisionReasonCode)}>
        <SelectTrigger className="w-56"><SelectValue placeholder="Reason to reopen…" /></SelectTrigger>
        <SelectContent>
          {REASON_CODES.map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}
        </SelectContent>
      </Select>
      <Button
        variant="outline"
        disabled={pending}
        onClick={async () => {
          if (!reasonCode) { onError("Pick a reason code to reopen this decision."); return; }
          onError(null);
          try { await mutate({ applicationId, body: { reasonCode } }); }
          catch (e) { onError((e as Error).message); }
        }}
      >
        Reopen for review
      </Button>
    </div>
  );
}
