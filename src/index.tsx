import { createFileRoute, Link } from "@tanstack/react-router";
import { SectionHeader, StatCard } from "@/components/yaqeen/primitives";
import { useOfficerDashboard } from "@/lib/yaqeen-queries";
import { useAuth } from "@/lib/auth";
import { statusLabel, type AppStatus } from "@/lib/utils";

export const Route = createFileRoute("/officer/dashboard")({ component: OfficerDashboard });

function OfficerDashboard() {
  const { user } = useAuth();
  const { data, isLoading, isError, error } = useOfficerDashboard();

  return (
    <div className="space-y-8">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-[0.22em] text-muted-foreground">Underwriting desk</div>
          <h1 className="mt-1 font-serif text-3xl">{user?.name}</h1>
        </div>
        <Link to="/officer/queue" className="rounded-lg bg-navy px-4 py-2 text-sm text-paper hover:opacity-95">Open queue →</Link>
      </div>

      {isError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          Couldn't load the dashboard: {(error as Error).message}
        </div>
      )}

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-4">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="paper-card h-24 animate-pulse" />)}</div>
      ) : data ? (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            <StatCard label="In queue" value={String(data.queueCount)} />
            <StatCard label="Approvals (30d)" value={String(data.approvalsLast30d)} />
            <StatCard label="Rejections (30d)" value={String(data.rejectionsLast30d)} />
            <StatCard label="Avg. time to decision" value={data.avgTimeToDecisionMinutes != null ? `${Math.round(data.avgTimeToDecisionMinutes)} min` : "—"} />
          </div>
          <div className="paper-card p-6">
            <SectionHeader eyebrow="Portfolio" title="Status breakdown" />
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
              {Object.entries(data.statusBreakdown).map(([k, v]) => (
                <div key={k} className="rounded-lg border border-border/70 p-3">
                  <div className="text-2xl font-serif">{v}</div>
                  <div className="text-xs text-muted-foreground">{statusLabel(k as AppStatus) ?? k}</div>
                </div>
              ))}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
