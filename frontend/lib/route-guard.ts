/**
 * Router-level RBAC guard used by role layouts.
 *
 * Note: reads `localStorage` directly so it works inside `beforeLoad`
 * (which is synchronous & runs before component render). SSR/prerender
 * skips the check; the component tree still re-checks via <AuthProvider>.
 */
import { redirect } from "@tanstack/react-router";
import { getStoredUser, type Role } from "@/lib/auth";

export function requireRole(role: Role, pathname: string) {
  if (typeof window === "undefined") return; // let client re-check post-hydrate
  const user = getStoredUser();
  if (!user) {
    throw redirect({ to: "/login", search: { redirect: pathname } as never });
  }
  if (user.role !== role) {
    throw redirect({ to: "/unauthorized" });
  }
}
