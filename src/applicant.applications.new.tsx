import { createFileRoute } from "@tanstack/react-router";
import { SectionHeader, StatCard } from "@/components/yaqeen/primitives";

export const Route = createFileRoute("/applicant/profile")({ component: ProfilePage });

function ProfilePage() {
  return (
    <div className="space-y-8">
      <SectionHeader eyebrow="Profile" title="Adnan Rehman" sub="Al-Madina Kiryana · Karachi" />
      <div className="grid gap-4 md:grid-cols-4">
        <StatCard label="CNIC" value="42101-•••••-1" />
        <StatCard label="Business type" value="Kiryana" />
        <StatCard label="Years operating" value="4" />
        <StatCard label="Employees" value="3" />
      </div>
      <div className="paper-card p-6 grid gap-4 md:grid-cols-2">
        <Info label="Registered address" value="Shop 12, Block 14, Gulistan-e-Johar, Karachi" />
        <Info label="Phone (Easypaisa)" value="+92 300 ••• 4421" />
        <Info label="Bank account" value="Bank Alfa · ending 8814" />
        <Info label="Tax jurisdiction" value="SRB Sindh" />
      </div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1">{value}</div>
    </div>
  );
}
