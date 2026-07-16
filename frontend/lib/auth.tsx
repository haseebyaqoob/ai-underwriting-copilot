/**
 * Real auth layer, backed by the FastAPI backend's JWT + rotating
 * refresh-token flow (see backend/app/api/v1/auth.py).
 *
 * IMPORTANT FINDING (documented in ARCHITECTURE_AND_PROGRESS.md): despite
 * this session's brief describing auth as already wired to the real
 * backend, the version of this file found in the zip was still a fully
 * mock, localStorage-only implementation (fake DEMO_ACCOUNTS login,
 * random client-generated ids on "signup"). It never called the backend
 * at all. This session replaces it for real.
 *
 * The access token itself is kept in memory only (see api-client.ts). A
 * *non-sensitive* mirror of the user's public profile shape
 * ({id,email,name,role,org} -- no token) is kept in localStorage purely
 * so route-guard.ts's synchronous `beforeLoad` check has something to
 * read before the async session-restore (refresh-cookie -> /auth/me)
 * completes. This is the same tradeoff the original mock file's comment
 * already called out ("reads localStorage directly so it works inside
 * beforeLoad, which is synchronous").
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError, bootstrapSession, setAccessToken } from "@/lib/api-client";

export type Role = "applicant" | "loan_officer" | "admin";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: Role;
  org?: string;
}

const STORAGE_KEY = "yaqeen.auth.user";

export const ROLE_HOME: Record<Role, string> = {
  applicant: "/applicant/dashboard",
  loan_officer: "/officer/dashboard",
  admin: "/admin/dashboard",
};

export const ROLE_LABEL: Record<Role, string> = {
  applicant: "Applicant",
  loan_officer: "Loan Officer",
  admin: "Administrator",
};

/** Which top-level route prefix each role is allowed to access. */
export const ROLE_PREFIX: Record<Role, string> = {
  applicant: "/applicant",
  loan_officer: "/officer",
  admin: "/admin",
};

export interface DemoAccount {
  email: string;
  password: string;
  role: Role;
  blurb: string;
}

/** Officer/admin accounts seeded for real by backend/scripts/seed_dev_data.py
 * -- kept here only to autofill the login form for local dev convenience,
 * never used to fabricate a session client-side (login always calls the
 * real API). There's no seeded applicant account (matches seed_dev_data.py
 * -- applicants sign up for real via /auth/signup). */
export const DEMO_ACCOUNTS: DemoAccount[] = [
  { email: "fatima.officer@bankalfa.pk", password: "demo1234", role: "loan_officer", blurb: "Underwrites applications on the queue" },
  { email: "admin@yaqeen.pk", password: "demo1234", role: "admin", blurb: "Manages officers, models & audit" },
];

/* --------------------------- storage helpers --------------------------- */

export function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

function writeStoredUser(user: AuthUser | null) {
  if (typeof window === "undefined") return;
  if (user) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
  else window.localStorage.removeItem(STORAGE_KEY);
  window.dispatchEvent(new CustomEvent("yaqeen:auth", { detail: user }));
}

/* ------------------------------ real API calls -------------------------- */

interface AuthResponse {
  accessToken: string;
  tokenType: string;
  user: AuthUser;
}

export async function signInWithPassword(email: string, password: string): Promise<AuthUser> {
  try {
    const res = await api.post<AuthResponse>("/auth/login", { email, password }, { anonymous: true });
    setAccessToken(res.accessToken);
    writeStoredUser(res.user);
    return res.user;
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) throw new Error("Invalid email or password.");
    throw e;
  }
}

export async function signUpApplicant(input: { name: string; email: string; password: string; org?: string }): Promise<AuthUser> {
  try {
    const res = await api.post<AuthResponse>("/auth/signup", input, { anonymous: true });
    setAccessToken(res.accessToken);
    writeStoredUser(res.user);
    return res.user;
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) throw new Error("An account with that email already exists.");
    if (e instanceof ApiError) throw new Error(e.message);
    throw e;
  }
}

export async function signOutRemote() {
  try {
    await api.post("/auth/logout");
  } catch {
    // Best-effort -- clear local state regardless of whether the network
    // call succeeded (matches how a revoked/expired refresh cookie should
    // still let the user land back on /login).
  }
  setAccessToken(null);
  writeStoredUser(null);
}

/** Restores a session on page load: tries the httpOnly refresh cookie,
 * then confirms it with a real /auth/me call so the in-memory user object
 * is never trusted from localStorage alone. */
async function restoreSession(): Promise<AuthUser | null> {
  const refreshed = await bootstrapSession();
  if (!refreshed) {
    writeStoredUser(null);
    return null;
  }
  try {
    const me = await api.get<AuthUser>("/auth/me");
    writeStoredUser(me);
    return me;
  } catch {
    setAccessToken(null);
    writeStoredUser(null);
    return null;
  }
}

export function canAccessPath(user: AuthUser | null, pathname: string): boolean {
  if (!user) return false;
  const allowed = ROLE_PREFIX[user.role];
  return pathname === allowed || pathname.startsWith(allowed + "/");
}

/* --------------------------- React context ---------------------------- */

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<AuthUser>;
  signUp: (input: { name: string; email: string; password: string; org?: string }) => Promise<AuthUser>;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    restoreSession().then((u) => {
      if (!cancelled) {
        setUser(u);
        setLoading(false);
      }
    });
    const onAuth = (e: Event) => setUser((e as CustomEvent<AuthUser | null>).detail ?? null);
    window.addEventListener("yaqeen:auth", onAuth as EventListener);
    return () => {
      cancelled = true;
      window.removeEventListener("yaqeen:auth", onAuth as EventListener);
    };
  }, []);

  const doSignOut = useCallback(() => {
    signOutRemote();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    signIn: async (email, password) => {
      const u = await signInWithPassword(email, password);
      setUser(u);
      return u;
    },
    signUp: async (input) => {
      const u = await signUpApplicant(input);
      setUser(u);
      return u;
    },
    signOut: doSignOut,
  }), [user, loading, doSignOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
