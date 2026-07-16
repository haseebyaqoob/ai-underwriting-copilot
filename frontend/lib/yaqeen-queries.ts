import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type {
  AdminDashboard,
  ApplicantDashboard,
  ApplicationCreateInput,
  ApplicationDetail,
  DocumentQueueItem,
  DocumentReview,
  DocumentReviewAction,
  DocumentUploadResult,
  EvidenceChecklist,
  EvidenceWalletItem,
  Notification,
  NotificationList,
  OfficerApplicationDetail,
  OfficerDashboard,
  OfficerDocumentDetail,
  OfficerNote,
  PaginatedApplications,
} from "@/lib/yaqeen-types";

/* ------------------------------- applicant ------------------------------ */

export function useApplicantDashboard() {
  return useQuery({
    queryKey: ["applicant", "dashboard"],
    queryFn: () => api.get<ApplicantDashboard>("/applicant/dashboard"),
  });
}

export function useApplicantApplications(page = 1, pageSize = 10) {
  return useQuery({
    queryKey: ["applicant", "applications", page, pageSize],
    queryFn: () =>
      api.get<PaginatedApplications>(`/applicant/applications?page=${page}&page_size=${pageSize}`),
  });
}

export function useApplicantApplication(
  id: string | undefined,
  options?: Partial<UseQueryOptions<ApplicationDetail>>,
) {
  return useQuery({
    queryKey: ["applicant", "applications", id],
    queryFn: () => api.get<ApplicationDetail>(`/applicant/applications/${id}`),
    enabled: !!id,
    ...options,
  });
}

export function useCreateApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ApplicationCreateInput) =>
      api.post<ApplicationDetail>("/applicant/applications", input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["applicant", "applications"] });
      qc.invalidateQueries({ queryKey: ["applicant", "dashboard"] });
    },
  });
}

/** DRAFT -> SUBMITTED. Applications are created as drafts now (see the
 * state-machine writeup in the architecture doc); the wizard/detail page
 * must call this explicitly to move an application into the officer's
 * queue -- creating an application no longer submits it implicitly. */
export function useSubmitApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (applicationId: string) =>
      api.post<ApplicationDetail>(`/applicant/applications/${applicationId}/submit`),
    onSuccess: (_data, applicationId) => {
      qc.invalidateQueries({ queryKey: ["applicant", "applications"] });
      qc.invalidateQueries({ queryKey: ["applicant", "applications", applicationId] });
      qc.invalidateQueries({ queryKey: ["applicant", "dashboard"] });
    },
  });
}

export function useWithdrawApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (applicationId: string) =>
      api.post<ApplicationDetail>(`/applicant/applications/${applicationId}/withdraw`),
    onSuccess: (_data, applicationId) => {
      qc.invalidateQueries({ queryKey: ["applicant", "applications"] });
      qc.invalidateQueries({ queryKey: ["applicant", "applications", applicationId] });
      qc.invalidateQueries({ queryKey: ["applicant", "dashboard"] });
    },
  });
}

export function useDocumentQueue(
  applicationId?: string,
  options?: Partial<UseQueryOptions<{ items: DocumentQueueItem[] }>>,
) {
  return useQuery({
    queryKey: ["applicant", "documents", "queue", applicationId ?? "all"],
    queryFn: () =>
      api.get<{ items: DocumentQueueItem[] }>(
        `/applicant/documents/queue${applicationId ? `?application_id=${applicationId}` : ""}`,
      ),
    ...options,
  });
}

export function useUploadDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      applicationId: string;
      documentType: string;
      file: File;
      replacesDocumentId?: string;
      subtype?: string;
    }) => {
      const form = new FormData();
      form.append("application_id", input.applicationId);
      form.append("document_type", input.documentType);
      if (input.subtype) form.append("subtype", input.subtype);
      if (input.replacesDocumentId) form.append("replaces_document_id", input.replacesDocumentId);
      form.append("file", input.file);
      return api.postForm<DocumentUploadResult>("/applicant/documents", form);
    },
    onSuccess: (_data, input) => {
      qc.invalidateQueries({ queryKey: ["applicant", "documents"] });
      qc.invalidateQueries({
        queryKey: ["applicant", "evidence", "checklist", input.applicationId],
      });
      qc.invalidateQueries({ queryKey: ["applicant", "evidence", "wallet"] });
    },
  });
}

export function useDeleteDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ documentId }: { documentId: string; applicationId: string }) =>
      api.delete<void>(`/applicant/documents/${documentId}`),
    onSuccess: (_data, { applicationId }) => {
      qc.invalidateQueries({ queryKey: ["applicant", "documents"] });
      qc.invalidateQueries({ queryKey: ["applicant", "evidence", "checklist", applicationId] });
    },
  });
}

/** Evidence review's "Looks correct? Confirm / Edit" step (product brief,
 * AI requirement #3). `edits` is optional -- omit it (or pass []) to
 * confirm the AI's reading as-is; pass corrected values to apply them and
 * confirm in the same call. See backend document_service
 * .confirm_extracted_fields's docstring for why this is never a claim of
 * document authenticity. */
export function useConfirmDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      documentId,
      edits,
    }: {
      documentId: string;
      applicationId: string;
      edits?: { fieldName: string; fieldValue: string }[];
    }) =>
      api.post<{
        documentId: string;
        documentVersionId: string;
        applicantConfirmedAt: string;
        fieldsEdited: number;
      }>(`/applicant/documents/${documentId}/confirm`, { edits: edits ?? [] }),
    onSuccess: (_data, { applicationId }) => {
      qc.invalidateQueries({ queryKey: ["applicant", "documents"] });
      qc.invalidateQueries({ queryKey: ["applicant", "evidence", "checklist", applicationId] });
    },
  });
}

export function useEvidenceChecklist(applicationId?: string) {
  return useQuery({
    queryKey: ["applicant", "evidence", "checklist", applicationId],
    queryFn: () =>
      api.get<EvidenceChecklist>(`/applicant/evidence/checklist?application_id=${applicationId}`),
    enabled: !!applicationId,
  });
}

export function useEvidenceWallet() {
  return useQuery({
    queryKey: ["applicant", "evidence", "wallet"],
    queryFn: () => api.get<EvidenceWalletItem[]>("/applicant/evidence/wallet"),
  });
}

export function useAttachFromWallet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { applicationId: string; walletItemId: string }) =>
      api.post<DocumentUploadResult>("/applicant/evidence/wallet/attach", input),
    onSuccess: (_data, input) => {
      qc.invalidateQueries({ queryKey: ["applicant", "documents"] });
      qc.invalidateQueries({
        queryKey: ["applicant", "evidence", "checklist", input.applicationId],
      });
      qc.invalidateQueries({ queryKey: ["applicant", "evidence", "wallet"] });
    },
  });
}

/* -------------------------------- officer -------------------------------- */

export function useOfficerDashboard() {
  return useQuery({
    queryKey: ["officer", "dashboard"],
    queryFn: () => api.get<OfficerDashboard>("/officer/dashboard"),
  });
}

export function useOfficerQueue(params?: {
  page?: number;
  pageSize?: number;
  status?: string;
  q?: string;
}) {
  const page = params?.page ?? 1;
  const pageSize = params?.pageSize ?? 10;
  const qs = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (params?.status) qs.set("status", params.status);
  if (params?.q) qs.set("q", params.q);
  return useQuery({
    queryKey: ["officer", "queue", page, pageSize, params?.status, params?.q],
    queryFn: () => api.get<PaginatedApplications>(`/officer/queue?${qs.toString()}`),
  });
}

export function useOfficerApplication(id: string | undefined) {
  return useQuery({
    queryKey: ["officer", "applications", id],
    queryFn: () => api.get<OfficerApplicationDetail>(`/officer/applications/${id}`),
    enabled: !!id,
  });
}

/** Completes Section 10: every uploaded document's own review sub-view --
 * preview metadata, every version's extracted fields, previous versions,
 * officer notes, and per-document review history. */
export function useOfficerApplicationDocuments(applicationId: string | undefined) {
  return useQuery({
    queryKey: ["officer", "applications", applicationId, "documents"],
    queryFn: () =>
      api.get<OfficerDocumentDetail[]>(`/officer/applications/${applicationId}/documents`),
    enabled: !!applicationId,
  });
}

/** Section 10's Evidence Summary -- same per-category tiering/status
 * vocabulary as the applicant's own Evidence page, entered from the
 * officer side. */
export function useOfficerEvidenceChecklist(applicationId: string | undefined) {
  return useQuery({
    queryKey: ["officer", "applications", applicationId, "evidence-checklist"],
    queryFn: () =>
      api.get<EvidenceChecklist>(`/officer/applications/${applicationId}/evidence-checklist`),
    enabled: !!applicationId,
  });
}

/** A real officer note, applicant-visible on their timeline the moment
 * it's left. Optionally scoped to one document via `documentId`. */
export function useAddOfficerNote(applicationId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { body: string; documentId?: string }) =>
      api.post<OfficerNote>(`/officer/applications/${applicationId}/notes`, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["officer", "applications", applicationId] });
      qc.invalidateQueries({ queryKey: ["officer", "applications", applicationId, "documents"] });
    },
  });
}

/** Per-document approve/reject/request-replacement/request-additional-
 * evidence -- distinct from the whole-application decisions above.
 * `replacement_requested`/`additional_evidence_requested` also open a
 * trackable DocumentRequest against this document's subtype (Section 11),
 * which is why this also invalidates the application detail (its
 * `openDocumentRequests` changes) and not just the documents list. */
export function useReviewDocument(applicationId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      documentId,
      action,
      note,
    }: {
      documentId: string;
      action: DocumentReviewAction;
      note?: string;
    }) => api.post<DocumentReview>(`/officer/documents/${documentId}/review`, { action, note }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["officer", "applications", applicationId] });
      qc.invalidateQueries({ queryKey: ["officer", "applications", applicationId, "documents"] });
    },
  });
}

function useOfficerApplicationAction(path: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ applicationId, body }: { applicationId: string; body?: unknown }) =>
      api.post<OfficerApplicationDetail>(`/officer/applications/${applicationId}/${path}`, body),
    onSuccess: (_data, { applicationId }) => {
      qc.invalidateQueries({ queryKey: ["officer", "queue"] });
      qc.invalidateQueries({ queryKey: ["officer", "applications", applicationId] });
      qc.invalidateQueries({ queryKey: ["officer", "dashboard"] });
    },
  });
}

/** SUBMITTED -> IN_REVIEW. */
export function useStartReview() {
  return useOfficerApplicationAction("start-review");
}

/** IN_REVIEW -> APPROVED. Body: { reasonCode, note? } (DecisionInput). */
export function useApproveApplication() {
  return useOfficerApplicationAction("approve");
}

/** IN_REVIEW -> REJECTED. Body: { reasonCode, note? }. */
export function useRejectApplication() {
  return useOfficerApplicationAction("reject");
}

/** IN_REVIEW -> NEEDS_DOCS. Body: { reasonCode, note?, missingDocumentTypes? }. */
export function useRequestDocs() {
  return useOfficerApplicationAction("request-docs");
}

/** APPROVED/REJECTED -> IN_REVIEW, requires an explicit logged reason. */
export function useReopenApplication() {
  return useOfficerApplicationAction("reopen");
}

/* --------------------------------- admin --------------------------------- */

export function useAdminDashboard() {
  return useQuery({
    queryKey: ["admin", "dashboard"],
    queryFn: () => api.get<AdminDashboard>("/admin/dashboard"),
  });
}

/* ----------------------------- notifications ------------------------------
 * Role-agnostic on purpose -- see backend/app/api/v1/notifications.py's
 * module docstring: every query is scoped to the current user, not a
 * role, so the same hooks serve applicant.notifications.tsx and
 * officer.notifications.tsx. */

export function useNotifications(params?: {
  page?: number;
  pageSize?: number;
  unreadOnly?: boolean;
}) {
  const page = params?.page ?? 1;
  const pageSize = params?.pageSize ?? 20;
  const qs = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (params?.unreadOnly) qs.set("unread_only", "true");
  return useQuery({
    queryKey: ["notifications", "list", page, pageSize, params?.unreadOnly ?? false],
    queryFn: () => api.get<NotificationList>(`/notifications?${qs.toString()}`),
    // Polling fallback for clients whose WS connection is down/unsupported
    // -- see lib/ws.ts's useNotificationsWebSocket, which invalidates this
    // same query key immediately on a live `notification.created` push,
    // making this interval a backstop rather than the primary channel.
    refetchInterval: 30_000,
  });
}

export function useUnreadNotificationCount() {
  return useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: () => api.get<{ unreadCount: number }>("/notifications/unread-count"),
    refetchInterval: 30_000,
  });
}

export function useMarkNotificationRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: string) =>
      api.post<Notification>(`/notifications/${notificationId}/read`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ markedRead: number }>("/notifications/read-all"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useNotificationPreferences() {
  return useQuery({
    queryKey: ["notifications", "preferences"],
    queryFn: () => api.get<{ notificationsEnabled: boolean }>("/notifications/preferences"),
  });
}

export function useUpdateNotificationPreferences() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (notificationsEnabled: boolean) =>
      api.patch<{ notificationsEnabled: boolean }>("/notifications/preferences", {
        notificationsEnabled,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications", "preferences"] });
    },
  });
}

/* -------------------------------- profile -------------------------------- */

export function useChangePassword() {
  return useMutation({
    mutationFn: (input: { currentPassword: string; newPassword: string }) =>
      api.post<void>("/auth/change-password", input),
  });
}
