import { createFileRoute } from "@tanstack/react-router";
import { SectionHeader } from "@/components/yaqeen/primitives";

export const Route = createFileRoute("/admin/config")({ component: C });

function C() {
  const groups = [
    { title: "Underwriting", rows: [["Score threshold", "620 auto-decline"], ["Confidence floor", "70%"], ["Human review", "Always for > PKR 2M"]] },
    { title: "Documents", rows: [["Accepted formats", "PDF · JPG · PNG · HEIC"], ["Max size", "25 MB"], ["Retention", "7 years"]] },
    { title: "Integrations", rows: [["Easypaisa API", "Connected"], ["JazzCash API", "Connected"], ["K-Electric API", "Connected"], ["FBR filings", "Read-only"]] },
  ];
  return (
    <div className="space-y-8">
      <SectionHeader eyebrow="Configuration" title="Tenant settings" />
      <div className="grid gap-6 md:grid-cols-3">
        {groups.map((g) => (
          <div key={g.title} className="paper-card p-6">
            <div className="font-serif text-lg">{g.title}</div>
            <div className="mt-4 divide-y divide-border/60">
              {g.rows.map(([l,v]) => (
                <div key={l} className="flex items-center justify-between py-2 text-sm">
                  <span className="text-muted-foreground">{l}</span>
                  <span>{v}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
