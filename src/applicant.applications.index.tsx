import { createFileRoute } from "@tanstack/react-router";
import { SectionHeader } from "@/components/yaqeen/primitives";

export const Route = createFileRoute("/applicant/settings")({ component: SettingsPage });

function SettingsPage() {
  const rows = [
    { l: "Language", v: "English (Roman Urdu supported)" },
    { l: "Notifications", v: "Email + SMS + Easypaisa alert" },
    { l: "Two-factor authentication", v: "Enabled · OTP" },
    { l: "Data sharing", v: "Bank-only · no third parties" },
  ];
  return (
    <div className="space-y-8">
      <SectionHeader eyebrow="Settings" title="Preferences" />
      <div className="paper-card divide-y divide-border/60">
        {rows.map((r) => (
          <div key={r.l} className="flex items-center justify-between p-5">
            <div>
              <div className="font-medium">{r.l}</div>
              <div className="text-sm text-muted-foreground">{r.v}</div>
            </div>
            <button className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted">Edit</button>
          </div>
        ))}
      </div>
    </div>
  );
}
