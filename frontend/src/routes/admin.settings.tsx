import { createFileRoute } from "@tanstack/react-router";
import { SectionHeader } from "@/components/yaqeen/primitives";

export const Route = createFileRoute("/admin/settings")({ component: S });

function S() {
  const rows = [
    { l: "Tenant name", v: "Bank Alfa · Karachi" },
    { l: "Timezone", v: "Asia/Karachi (PKT)" },
    { l: "Default currency", v: "PKR" },
    { l: "SSO", v: "Azure AD · Enabled" },
  ];
  return (
    <div className="space-y-8">
      <SectionHeader eyebrow="Settings" title="Administrator preferences" />
      <div className="paper-card divide-y divide-border/60">
        {rows.map((r) => (
          <div key={r.l} className="flex items-center justify-between p-5">
            <div><div className="font-medium">{r.l}</div><div className="text-sm text-muted-foreground">{r.v}</div></div>
            <button className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted">Edit</button>
          </div>
        ))}
      </div>
    </div>
  );
}
