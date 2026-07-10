import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMemo } from "react";
import { SectionHeader } from "@/components/yaqeen/primitives";
import { useApplicantApplication } from "@/lib/yaqeen-queries";
import type { ProcessingStep } from "@/lib/yaqeen-types";
import { CheckCircle2, Circle, Loader2 } from "lucide-react";

export const Route = createFileRoute("/applicant/applications/$id/processing")({ component: ProcessingPage });

function ProcessingPage() {
  const { id } = Route.useParams();
  const nav = useNavigate();
  // Polls every 2.5s while anything is still pending/in_progress -- real
  // progress, not a fixed-duration fake sequence (see
  // backend/app/services/workflow_stage_service.py's module docstring).
  // Polling stops itself once every step is complete, or once the
  // application has moved past SUBMITTED (an officer or the state
  // machine took over).
  const { data: app, isLoading } = useApplicantApplication(id, {
    refetchInterval: (query) => {
      const steps = query.state.data?.processingSteps;
      const allDone = steps && steps.every((s) => s.status === "complete");
      return allDone ? false : 2500;
    },
  });

  const steps = app?.processingSteps ?? [];
  const completeCount = steps.filter((s) => s.status === "complete").length;
  const allComplete = steps.length > 0 && completeCount === steps.length;

  const progressPct = useMemo(() => (steps.length ? Math.round((completeCount / steps.length) * 100) : 0), [steps, completeCount]);

  return (
    <div className="space-y-8">
      <SectionHeader
        eyebrow="Processing"
        title="Yaqeen is reading your application"
        sub="This runs automatically — no need to keep this tab open. We'll notify you the moment it's ready for officer review."
      />

      {isLoading || !app ? (
        <div className="paper-card h-64 animate-pulse" />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
          <div className="paper-card flex flex-col items-center justify-center gap-3 p-6 text-center">
            <div className="relative grid h-28 w-28 place-items-center">
              <svg viewBox="0 0 100 100" className="absolute inset-0 -rotate-90">
                <circle cx="50" cy="50" r="44" fill="none" stroke="var(--color-muted)" strokeWidth="8" />
                <circle
                  cx="50" cy="50" r="44" fill="none" stroke="var(--color-navy)" strokeWidth="8" strokeLinecap="round"
                  strokeDasharray={`${2 * Math.PI * 44}`}
                  strokeDashoffset={`${2 * Math.PI * 44 * (1 - progressPct / 100)}`}
                  className="transition-[stroke-dashoffset] duration-700 ease-out"
                />
              </svg>
              <span className="font-serif text-2xl text-foreground">{progressPct}%</span>
            </div>
            <div className="text-xs text-muted-foreground">
              {allComplete ? "All steps complete" : `${completeCount} of ${steps.length} steps complete`}
            </div>
            <div className="mt-2 text-xs text-muted-foreground">
              Application <span className="font-mono text-foreground">{app.displayId}</span>
            </div>
          </div>

          <div className="paper-card divide-y divide-border/60 overflow-hidden">
            {steps.map((s) => (
              <StepRow key={s.key} step={s} />
            ))}
          </div>
        </div>
      )}

      <div className="flex justify-end gap-3">
        <button
          onClick={() => nav({ to: "/applicant/applications/$id", params: { id } })}
          className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-muted/40"
        >
          View application details
        </button>
        <button
          onClick={() => nav({ to: "/applicant/dashboard" })}
          disabled={!allComplete}
          className="rounded-lg bg-navy px-4 py-2 text-sm text-paper disabled:opacity-50"
        >
          {allComplete ? "Go to Dashboard →" : "Waiting for processing…"}
        </button>
      </div>
    </div>
  );
}

function StepRow({ step }: { step: ProcessingStep }) {
  return (
    <div className="flex items-center gap-4 px-6 py-4">
      <div className="shrink-0">
        {step.status === "complete" && <CheckCircle2 className="h-5 w-5 text-sage" />}
        {step.status === "in_progress" && <Loader2 className="h-5 w-5 animate-spin text-gold" />}
        {step.status === "pending" && <Circle className="h-5 w-5 text-muted-foreground/40" />}
      </div>
      <div className="min-w-0 flex-1">
        <div className={`text-sm font-medium ${step.status === "pending" ? "text-muted-foreground" : "text-foreground"}`}>{step.label}</div>
        <div className="text-xs text-muted-foreground">{step.detail}</div>
      </div>
      <div className="shrink-0 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {step.status === "complete" ? "Complete" : step.status === "in_progress" ? "In progress" : "Waiting"}
      </div>
    </div>
  );
}
