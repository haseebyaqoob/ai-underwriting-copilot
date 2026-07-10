import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { SectionHeader } from "@/components/yaqeen/primitives";
import {
  ChecklistCategorySection,
  EvidenceStrengthCard,
  EvidenceWalletPanel,
} from "@/components/yaqeen/evidence";
import {
  useApplicantApplications,
  useAttachFromWallet,
  useDeleteDocument,
  useEvidenceChecklist,
  useEvidenceWallet,
  useUploadDocument,
} from "@/lib/yaqeen-queries";
import { useDocumentWebSocket } from "@/lib/ws";
import type { EvidenceWalletItem } from "@/lib/yaqeen-types";
import { AlertCircle } from "lucide-react";

export const Route = createFileRoute("/applicant/upload")({ component: EvidencePage });

function EvidencePage() {
  const { data: appsPage, isLoading: appsLoading } = useApplicantApplications(1, 50);
  const apps = appsPage?.items ?? [];
  const [applicationId, setApplicationId] = useState<string>("");
  const activeAppId = applicationId || apps[0]?.id || "";

  useMemo(() => {
    if (!applicationId && apps.length > 0) setApplicationId(apps[0].id);
  }, [apps, applicationId]);

  const { data: checklist, isLoading: checklistLoading } = useEvidenceChecklist(activeAppId || undefined);
  const { data: wallet, isLoading: walletLoading } = useEvidenceWallet();
  // Live push: process_document_task emits document.uploaded/document.processed
  // over Redis pub/sub -> the WS connection manager -> this socket. Any
  // message on it means SOME document for this application changed
  // status, so the simplest correct thing is "a message arrived -> the
  // checklist/wallet reads used above are already react-query hooks and
  // will pick up fresh data on their own polling/staleness -- this call
  // just keeps the socket open so document_service's live-status story
  // (documented in the original upload page) still holds here.
  useDocumentWebSocket(activeAppId || undefined);

  const uploadMutation = useUploadDocument();
  const deleteMutation = useDeleteDocument();
  const attachMutation = useAttachFromWallet();

  const [uploadingKey, setUploadingKey] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [attachingId, setAttachingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const walletBySubtype = useMemo(() => {
    const map = new Map<string, EvidenceWalletItem>();
    for (const w of wallet ?? []) map.set(w.subtype, w);
    return map;
  }, [wallet]);

  const handleUpload = async (subtype: string, file: File, replacesDocumentId?: string) => {
    if (!activeAppId) {
      setError("Select an application first.");
      return;
    }
    setError(null);
    setUploadingKey(subtype);
    try {
      // subtype's checklist category also maps to a coarse DocumentType
      // via the backend's evidence_catalog -- the client only needs to
      // pass `subtype`; `document_type` here is a reasonable default the
      // backend overrides once it looks the subtype up (see
      // document_service.upload_document).
      await uploadMutation.mutateAsync({ applicationId: activeAppId, documentType: "other", subtype, file, replacesDocumentId });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploadingKey(null);
    }
  };

  const handleDelete = async (documentId: string) => {
    if (!activeAppId) return;
    setDeletingId(documentId);
    try {
      await deleteMutation.mutateAsync({ documentId, applicationId: activeAppId });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDeletingId(null);
    }
  };

  const handleAttach = async (item: EvidenceWalletItem) => {
    if (!activeAppId) {
      setError("Select an application first.");
      return;
    }
    setAttachingId(item.id);
    try {
      await attachMutation.mutateAsync({ applicationId: activeAppId, walletItemId: item.id });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setAttachingId(null);
    }
  };

  return (
    <div className="space-y-8">
      <SectionHeader
        eyebrow="Evidence"
        title="Evidence Checklist"
        sub="Verify your identity and business with the documents you already have — traditional records, digital wallets, or both. Nothing here needs to be perfect on the first try."
      />

      {appsLoading ? (
        <div className="paper-card h-16 animate-pulse" />
      ) : apps.length === 0 ? (
        <div className="paper-card p-6 text-sm text-muted-foreground">
          You don't have an application yet — <a href="/applicant/applications/new" className="underline underline-offset-4">start one</a> before adding evidence.
        </div>
      ) : (
        <label className="block max-w-md">
          <span className="mb-1.5 block text-xs font-medium text-foreground/80">Application</span>
          <select value={activeAppId} onChange={(e) => setApplicationId(e.target.value)} className="w-full rounded-lg border border-input bg-card/70 px-3 py-2.5 text-sm">
            {apps.map((a) => (
              <option key={a.id} value={a.id}>
                {a.displayId} · {a.businessName}
              </option>
            ))}
          </select>
        </label>
      )}

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-2.5 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" /> {error}
        </div>
      )}

      {activeAppId && (
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <div className="space-y-6 lg:order-1">
            {checklistLoading || !checklist ? (
              <div className="space-y-4">
                <div className="paper-card h-24 animate-pulse" />
                <div className="paper-card h-40 animate-pulse" />
                <div className="paper-card h-40 animate-pulse" />
              </div>
            ) : (
              checklist.categories.map((category) => (
                <ChecklistCategorySection
                  key={category.key}
                  category={category}
                  onUpload={handleUpload}
                  onDelete={handleDelete}
                  uploadingKey={uploadingKey}
                  deletingId={deletingId}
                  walletBySubtype={walletBySubtype}
                  onAttachFromWallet={handleAttach}
                />
              ))
            )}
          </div>
          <div className="space-y-6 lg:order-2">
            {checklist && <EvidenceStrengthCard strength={checklist.strength} />}
            <EvidenceWalletPanel items={wallet} isLoading={walletLoading} onAttach={handleAttach} attachingId={attachingId ?? undefined} />
          </div>
        </div>
      )}
    </div>
  );
}
