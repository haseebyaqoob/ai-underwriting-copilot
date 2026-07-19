import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { Bell, Search, Settings, ChevronRight, LogOut } from "lucide-react";
import { Logo } from "@/components/yaqeen/Logo";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { useDocumentWebSocket } from "@/lib/ws";
import { useUnreadNotificationCount } from "@/lib/yaqeen-queries";

export interface NavItem { to: string; label: string; icon: ReactNode; end?: boolean }

export function RoleShell({ role, nav, children }: { role: "Applicant" | "Loan Officer" | "Administrator"; nav: NavItem[]; children: ReactNode }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const active = (n: NavItem) => n.end ? pathname === n.to : pathname === n.to || pathname.startsWith(n.to + "/");
  const crumb = nav.find(active)?.label ?? "";
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const initials = (user?.name ?? "YQ").split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  const handleSignOut = () => { signOut(); navigate({ to: "/login", replace: true }); };

  // One persistent WS connection per role layout (lives as long as this
  // shell does) so the unread-notification badge updates live, not just
  // on the 30s polling fallback -- see lib/ws.ts and
  // backend/app/services/notification_service.py's `notification.created`
  // event.
  useDocumentWebSocket();
  const { data: unread } = useUnreadNotificationCount();
  const unreadCount = unread?.unreadCount ?? 0;
  const isApplicant = role === "Applicant";
  // Section 9 only shipped an inbox for applicants and loan officers (see
  // routes/applicant.notifications.tsx, routes/officer.notifications.tsx)
  // -- there's no /admin/notifications route, so the bell stays a plain
  // (non-navigating) icon for Administrator rather than linking to a 404.
  const notificationsHref = role === "Applicant" ? "/applicant/notifications" : role === "Loan Officer" ? "/officer/notifications" : null;

  return (
    <div className="min-h-screen bg-background">
      <div className="flex min-h-screen">
        <aside className="hidden w-64 shrink-0 border-r border-border bg-sidebar/70 backdrop-blur md:flex md:flex-col">
          <div className="flex h-16 items-center px-5 border-b border-sidebar-border">
            <Logo />
          </div>
          <div className="px-3 py-4">
            <div className="mb-2 px-3 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{role}</div>
            <nav className="space-y-0.5">
              {nav.map((n) => (
                <Link key={n.to} to={n.to} className={cn(
                  "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition",
                  active(n) ? "bg-navy text-paper shadow-elegant" : "text-foreground/80 hover:bg-sidebar-accent"
                )}>
                  <span className={cn("grid h-6 w-6 place-items-center rounded-md", active(n) ? "text-gold" : "text-muted-foreground")}>{n.icon}</span>
                  <span className="truncate">{n.label}</span>
                  {n.label === "Notifications" && unreadCount > 0 && (
                    <span className="ml-auto grid h-5 min-w-5 place-items-center rounded-full bg-gold px-1 text-[10px] font-semibold text-navy">
                      {unreadCount > 99 ? "99+" : unreadCount}
                    </span>
                  )}
                </Link>
              ))}
            </nav>
          </div>
          <div className="mt-auto p-4">
            <div className="paper-card p-4">
              <div className="text-xs text-muted-foreground">Signed in as</div>
              <div className="mt-1 truncate text-sm font-medium">{user?.name ?? "Guest"}</div>
              <div className="truncate text-[11px] text-muted-foreground">{user?.email}{user?.org ? ` · ${user.org}` : ""}</div>
              <button onClick={handleSignOut} className="mt-3 inline-flex items-center gap-1.5 text-xs text-navy-soft hover:text-navy underline underline-offset-4">
                <LogOut className="h-3 w-3" /> Sign out
              </button>
            </div>
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b border-border bg-background/80 px-5 backdrop-blur">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <span>{role}</span>
              <ChevronRight className="h-3.5 w-3.5" />
              <span className="text-foreground">{crumb}</span>
            </div>
            <div className="ml-auto flex items-center gap-2">
              {/* Section 8: the global search bar is applicant-portal-only
                  clutter removed per the nav-cleanup brief -- left in place
                  for officer/admin, which weren't in scope for this pass. */}
              {!isApplicant && (
                <div className="hidden items-center gap-2 rounded-lg border border-border bg-card/70 px-3 py-1.5 text-sm text-muted-foreground md:flex">
                  <Search className="h-4 w-4" />
                  <span className="w-56">Search applications, docs…</span>
                  <kbd className="ml-2 rounded bg-muted px-1.5 py-0.5 text-[10px]">⌘K</kbd>
                </div>
              )}
              {notificationsHref ? (
                <Link
                  to={notificationsHref}
                  className="relative grid h-9 w-9 place-items-center rounded-lg border border-border bg-card/70 hover:bg-muted"
                >
                  <Bell className="h-4 w-4" />
                  {unreadCount > 0 && (
                    <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-gold px-1 text-[9px] font-semibold text-navy">
                      {unreadCount > 9 ? "9+" : unreadCount}
                    </span>
                  )}
                </Link>
              ) : (
                <button className="relative grid h-9 w-9 place-items-center rounded-lg border border-border bg-card/70 hover:bg-muted">
                  <Bell className="h-4 w-4" />
                </button>
              )}
              {/* Section 8: standalone Settings entry point removed for the
                  applicant portal -- every settings feature now lives on
                  the Profile page instead. */}
              {!isApplicant && (
                <button className="grid h-9 w-9 place-items-center rounded-lg border border-border bg-card/70 hover:bg-muted"><Settings className="h-4 w-4" /></button>
              )}
              <div className="ml-1 grid h-9 w-9 place-items-center rounded-full bg-navy text-paper text-xs font-medium" title={user?.email}>{initials}</div>
            </div>
          </header>
          <main className="px-6 py-8 md:px-10">{children}</main>
        </div>
      </div>
    </div>
  );
}
