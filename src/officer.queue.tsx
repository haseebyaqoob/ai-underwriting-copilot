import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { fmtPKR } from "@/lib/utils";
import { useApplicantApplications } from "@/lib/yaqeen-queries";
import { SectionHeader, WorkflowStageChip, ConfidenceBadge } from "@/components/yaqeen/primitives";
import { Search } from "lucide-react";

export const Route = createFileRoute("/applicant/applications/")({ component: AppList });

function AppList() {
  const [search, setSearch] = useState("");
  const { data, isLoading, isError, error } = useApplicantApplications(1, 50);

  const items = (data?.items ?? []).filter((a) =>
    search.trim() === "" ||
    a.displayId.toLowerCase().includes(search.toLowerCase()) ||
    a.businessName.toLowerCase().includes(search.toLowerCase()) ||
    a.city.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="Applications" title="All your loan applications" sub="Track status, evidence and officer feedback across every application." />
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-1 items-center gap-2 rounded-lg border border-border bg-card/70 px-3 py-2 text-sm">
          <Search className="h-4 w-4 text-muted-foreground" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} className="w-full bg-transparent outline-none" placeholder="Search by ID, business or city" />
        </div>
      </div>

      {isError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          Couldn't load applications: {(error as Error).message}
        </div>
      )}

      {isLoading ? (
        <div className="paper-card h-40 animate-pulse" />
      ) : items.length === 0 ? (
        <div className="paper-card p-10 text-center text-sm text-muted-foreground">
          {data && data.items.length === 0
            ? "You haven't submitted any applications yet."
            : "No applications match your search."}
        </div>
      ) : (
        <div className="paper-card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Business</th>
                <th className="px-4 py-3">Amount</th>
                <th className="px-4 py-3">Stage</th>
                <th className="px-4 py-3">Confidence</th>
                <th className="px-4 py-3">Updated</th>
              </tr>
            </thead>
            <tbody className="[&_tr]:border-t [&_tr]:border-border/60">
              {items.map((a) => (
                <tr key={a.id} className="hover:bg-muted/40">
                  <td className="px-4 py-3 font-mono text-xs">
                    <Link to="/applicant/applications/$id" params={{ id: a.id }} className="underline underline-offset-4">{a.displayId}</Link>
                  </td>
                  <td className="px-4 py-3">{a.businessName}<div className="text-xs text-muted-foreground">{a.city} · {a.purpose}</div></td>
                  <td className="px-4 py-3">{fmtPKR(Number(a.amountPkr))}</td>
                  <td className="px-4 py-3"><WorkflowStageChip stage={a.workflowStage} label={a.workflowStageLabel} /></td>
                  <td className="px-4 py-3">{a.confidence != null ? <ConfidenceBadge value={a.confidence} /> : <span className="text-xs text-muted-foreground">—</span>}</td>
                  <td className="px-4 py-3 text-muted-foreground">{new Date(a.updatedAt).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
