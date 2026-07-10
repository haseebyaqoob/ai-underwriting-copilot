import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { fmtPKR } from "@/lib/utils";
import { useOfficerQueue } from "@/lib/yaqeen-queries";
import { SectionHeader, StatusChip, ConfidenceBadge } from "@/components/yaqeen/primitives";
import { Search } from "lucide-react";

export const Route = createFileRoute("/officer/queue")({ component: OfficerQueue });

function OfficerQueue() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<string>("");
  const { data, isLoading, isError, error } = useOfficerQueue({ page: 1, pageSize: 50, status: status || undefined, q: q || undefined });

  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="Queue" title="Applications awaiting review" sub="Scoped to your lending organization." />
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-1 items-center gap-2 rounded-lg border border-border bg-card/70 px-3 py-2 text-sm">
          <Search className="h-4 w-4 text-muted-foreground" />
          <input value={q} onChange={(e) => setQ(e.target.value)} className="w-full bg-transparent outline-none" placeholder="Search business, applicant or ID" />
        </div>
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-lg border border-input bg-card/70 px-3 py-2 text-sm">
          <option value="">All statuses</option>
          <option value="submitted">Submitted</option>
          <option value="in_review">In Review</option>
          <option value="needs_docs">Needs Docs</option>
        </select>
      </div>

      {isError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          Couldn't load the queue: {(error as Error).message}
        </div>
      )}

      {isLoading ? (
        <div className="paper-card h-40 animate-pulse" />
      ) : data && data.items.length === 0 ? (
        <div className="paper-card p-10 text-center text-sm text-muted-foreground">Nothing in the queue right now.</div>
      ) : (
        <div className="paper-card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Applicant</th>
                <th className="px-4 py-3">Business</th>
                <th className="px-4 py-3">Amount</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Confidence</th>
              </tr>
            </thead>
            <tbody className="[&_tr]:border-t [&_tr]:border-border/60">
              {data?.items.map((a) => (
                <tr key={a.id} className="hover:bg-muted/40">
                  <td className="px-4 py-3 font-mono text-xs">
                    <Link to="/officer/applications/$id" params={{ id: a.id }} className="underline underline-offset-4">{a.displayId}</Link>
                  </td>
                  <td className="px-4 py-3">{a.applicantName}</td>
                  <td className="px-4 py-3">{a.businessName}<div className="text-xs text-muted-foreground">{a.city}</div></td>
                  <td className="px-4 py-3">{fmtPKR(Number(a.amountPkr))}</td>
                  <td className="px-4 py-3"><StatusChip status={a.status} /></td>
                  <td className="px-4 py-3">{a.confidence != null ? <ConfidenceBadge value={a.confidence} /> : <span className="text-xs text-muted-foreground">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
