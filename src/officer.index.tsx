import { createFileRoute } from "@tanstack/react-router";
import { SectionHeader, Chip } from "@/components/yaqeen/primitives";

export const Route = createFileRoute("/admin/permissions")({ component: P });

const perms = [
  { role: "Applicant", caps: ["Create application", "Upload evidence", "View own decision"] },
  { role: "Loan Officer", caps: ["View queue", "Open application", "Approve / reject", "Request docs", "Reassign"] },
  { role: "Administrator", caps: ["Manage users", "Manage officers", "Configure system", "View all audit logs", "Model usage"] },
];

function P() {
  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="Governance" title="Role permissions" sub="Roles never see another role's interface." />
      <div className="grid gap-4 md:grid-cols-3">
        {perms.map((p) => (
          <div key={p.role} className="paper-card p-5">
            <Chip tone="navy">{p.role}</Chip>
            <ul className="mt-4 space-y-2 text-sm">
              {p.caps.map((c) => <li key={c} className="flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-gold" /> {c}</li>)}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
