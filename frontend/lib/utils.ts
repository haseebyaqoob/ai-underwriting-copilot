import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Moved here from the now-deleted mock-data.ts -- this is a generic
 * currency formatter, not mock data, so it belongs in the shared utils
 * module rather than disappearing along with the fixtures. */
export function fmtPKR(n: number) {
  if (n >= 1_000_000) return `PKR ${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `PKR ${(n / 1_000).toFixed(0)}K`;
  return `PKR ${n}`;
}

export type AppStatus = "draft" | "submitted" | "in_review" | "needs_docs" | "approved" | "rejected" | "withdrawn";

export function statusLabel(s: AppStatus) {
  return {
    draft: "Draft",
    submitted: "Submitted",
    in_review: "In Review",
    needs_docs: "Needs Docs",
    approved: "Approved",
    rejected: "Rejected",
    withdrawn: "Withdrawn",
  }[s];
}
