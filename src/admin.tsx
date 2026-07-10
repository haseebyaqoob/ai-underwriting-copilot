import { createFileRoute } from "@tanstack/react-router";
import { SectionHeader, StatCard } from "@/components/yaqeen/primitives";
import { useAdminDashboard } from "@/lib/yaqeen-queries";
import { fmtPKR, statusLabel, type AppStatus } from "@/lib/utils";

export const Route = createFileRoute("/admin/dashboard")({ component: AdminDashboard });

function AdminDashboard() {
  const { data, isLoading, isError, error } = useAdminDashboard();

  return (
    <div className="space-y-8">
      <SectionHeader eyebrow="Portfolio" title="Platform overview" sub="Scoped to your organization." />

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
            <StatCard label="Total applications" value={String(data.totalApplications)} />
            <StatCard label="Submitted (30d)" value={String(data.submittedLast30d)} />
            <StatCard label="Approval rate" value={data.approvalRate != null ? `${(data.approvalRate * 100).toFixed(1)}%` : "—"} />
            <StatCard label="Total volume" value={fmtPKR(Number(data.totalVolumePkr))} />
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

          {/* Officer performance and model-usage panels intentionally removed:
              admin_dashboard's backend response (AdminDashboardOut) doesn't
              expose per-officer or per-model data yet -- that was Module 7/8
              scope and hasn't been built. Showing it here would mean silently
              falling back to the fixture data this session was asked to
              remove. See docs/ARCHITECTURE_AND_PROGRESS.md "Known gaps". */}
          <div className="paper-card border-dashed p-6 text-sm text-muted-foreground">
            Officer performance and AI model-usage breakdowns aren't available yet — they depend on Module 7/8 (not built). This panel will appear once that backend support lands.
          </div>
        </>
      ) : null}
    </div>
  );
}
