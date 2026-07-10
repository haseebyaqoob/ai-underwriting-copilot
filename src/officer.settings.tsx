import { createFileRoute } from "@tanstack/react-router";
import { SectionHeader, Chip } from "@/components/yaqeen/primitives";

export const Route = createFileRoute("/admin/users")({ component: UsersPage });

const users = Array.from({ length: 10 }).map((_, i) => ({
  id: `U-${1000+i}`,
  name: ["Adnan Rehman","Ayesha Malik","Bilal Khan","Sana Iqbal","Usman Sheikh","Zainab Fatima","Hassan Ali","Mariam Yousuf","Kamran Butt","Nadia Aslam"][i],
  role: i % 3 === 0 ? "Applicant" : i % 3 === 1 ? "Officer" : "Admin",
  status: i % 4 === 0 ? "invited" : "active",
  lastActive: `${i+1}d ago`,
}));

function UsersPage() {
  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="Users" title="All users" sub="Applicants, officers and administrators across the tenant." />
      <div className="paper-card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wider text-muted-foreground">
            <tr><th className="px-6 py-3">ID</th><th className="px-6 py-3">Name</th><th className="px-6 py-3">Role</th><th className="px-6 py-3">Status</th><th className="px-6 py-3">Last active</th></tr>
          </thead>
          <tbody className="[&_tr]:border-t [&_tr]:border-border/60">
            {users.map((u) => (
              <tr key={u.id} className="hover:bg-muted/40">
                <td className="px-6 py-3 font-mono text-xs">{u.id}</td>
                <td className="px-6 py-3">{u.name}</td>
                <td className="px-6 py-3"><Chip tone={u.role === "Admin" ? "navy" : u.role === "Officer" ? "gold" : "muted"}>{u.role}</Chip></td>
                <td className="px-6 py-3"><Chip tone={u.status === "active" ? "sage" : "clay"}>{u.status}</Chip></td>
                <td className="px-6 py-3 text-muted-foreground">{u.lastActive}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
