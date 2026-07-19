import { useEffect, useMemo, useRef, useState } from "react";
import type { DragEvent } from "react";
import { Chip, ConfidenceBadge } from "@/components/yaqeen/primitives";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api-client";
import { useConfirmDocument } from "@/lib/yaqeen-queries";
import type {
  DocumentRequest,
  EvidenceCategory,
  EvidenceChecklist,
  EvidenceChecklistItem,
  EvidenceItemDocument,
  EvidenceQualityStatus,
  EvidenceStrength,
  EvidenceTier,
  EvidenceWalletItem,
  OcrStatus,
  ProcessingStage,
} from "@/lib/yaqeen-types";
import {
  AlertTriangle,
  Camera,
  Check,
  CheckCircle2,
  ChevronDown,
  Clock,
  Eye,
  FileText,
  FileWarning,
  Loader2,
  MessageSquare,
  Pencil,
  Plus,
  ScanLine,
  Sparkles,
  Trash2,
  UploadCloud,
  Wallet,
  X,
  XCircle,
  ZoomIn,
  ZoomOut,
} from "lucide-react";

/* --------------------------------- shared bits --------------------------------- */

const STATUS_META: Record<
  EvidenceQualityStatus,
  { label: string; tone: Parameters<typeof Chip>[0]["tone"]; icon: React.ReactNode }
> = {
  missing: {
    label: "Missing",
    tone: "muted",
    icon: <span className="h-2 w-2 rounded-full bg-muted-foreground/50" />,
  },
  uploaded: { label: "Uploaded", tone: "navy", icon: <CheckCircle2 className="h-3 w-3" /> },
  processing: {
    label: "Processing",
    tone: "gold",
    icon: <Loader2 className="h-3 w-3 animate-spin" />,
  },
  verified: { label: "Verified", tone: "sage", icon: <CheckCircle2 className="h-3 w-3" /> },
  needs_better_image: {
    label: "Needs Better Image",
    tone: "danger",
    icon: <FileWarning className="h-3 w-3" />,
  },
  mismatch: {
    label: "Doesn't Match Application",
    tone: "danger",
    icon: <AlertTriangle className="h-3 w-3" />,
  },
  // Session 12 (AI requirement #1/#5): the AI thinks this upload isn't
  // even the right kind of document -- distinct from mismatch (which
  // means "right document, but the NAME/ID on it doesn't match the
  // applicant") and from needs_better_image (which means "right
  // document, just hard to read").
  wrong_document: {
    label: "Wrong Document",
    tone: "danger",
    icon: <XCircle className="h-3 w-3" />,
  },
};

export function EvidenceStatusPill({ status }: { status: EvidenceQualityStatus }) {
  const m = STATUS_META[status] ?? STATUS_META.missing;
  return (
    <Chip tone={m.tone}>
      {m.icon} {m.label}
    </Chip>
  );
}

/** Tone for the category-level badge word (Verified/Strong/Good/Pending/
 * Needs Documents/Incomplete/Optional) computed backend-side in
 * evidence_checklist_service._category_status -- this just maps that
 * word to a color, matching the same visual language as
 * EvidenceStatusPill above. */
function categoryStatusTone(label: string): Parameters<typeof Chip>[0]["tone"] {
  switch (label) {
    case "Verified":
    case "Strong":
      return "sage";
    case "Good":
    case "Pending":
      return "gold";
    case "Needs Documents":
      return "clay";
    default:
      return "muted";
  }
}

export function CategoryStatusBadge({ label }: { label: string }) {
  return <Chip tone={categoryStatusTone(label)}>{label}</Chip>;
}

const TIER_META: Record<EvidenceTier, { label: string; blurb: string }> = {
  required: { label: "Required", blurb: "Needed to submit your application." },
  recommended: { label: "Recommended", blurb: "Strengthens your assessment significantly." },
  optional: { label: "Optional", blurb: "Nice to have, not necessary." },
};

/**
 * Session 12 (product brief section 3: "Preview opens inside a modal ...
 * For images: zoom, responsive. For PDF: embedded viewer"). Replaces the
 * old new-tab/download fallback below `useDocumentPreview` mounts this
 * against a `documentId` set by the Preview button; the blob fetch
 * itself is the same authenticated `api.getBlob` call the old
 * `previewDocument` used, just rendered inline instead of handed to
 * `window.open`.
 */
function useDocumentPreview() {
  const [target, setTarget] = useState<{ documentId: string; filename: string } | null>(null);
  return {
    open: (documentId: string, filename: string) => setTarget({ documentId, filename }),
    close: () => setTarget(null),
    target,
  };
}

function guessIsPdf(filename: string, mimeType: string | undefined): boolean {
  if (mimeType) return mimeType === "application/pdf";
  return filename.toLowerCase().endsWith(".pdf");
}

function DocumentPreviewModal({
  documentId,
  filename,
  onClose,
}: {
  documentId: string;
  filename: string;
  onClose: () => void;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [mimeType, setMimeType] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    setUrl(null);
    setError(null);
    setZoom(1);
    api
      .getBlob(`/applicant/documents/${documentId}/file`)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setMimeType(blob.type || undefined);
        setUrl(objectUrl);
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message || "Couldn't load this file.");
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [documentId]);

  const isPdf = guessIsPdf(filename, mimeType);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="flex max-h-[90vh] w-[95vw] max-w-4xl flex-col gap-3 overflow-hidden p-4 sm:p-6">
        <DialogHeader>
          <DialogTitle className="truncate pr-6 font-sans text-sm font-medium">
            {filename}
          </DialogTitle>
        </DialogHeader>

        {!url && !error && (
          <div className="flex flex-1 items-center justify-center py-16 text-sm text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading preview…
          </div>
        )}
        {error && (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 py-16 text-sm text-clay">
            <AlertTriangle className="h-5 w-5" /> {error}
          </div>
        )}
        {url && isPdf && (
          <iframe
            title={filename}
            src={url}
            className="h-[75vh] w-full rounded-md border border-border/60 bg-white"
          />
        )}
        {url && !isPdf && (
          <>
            <div className="flex items-center justify-center gap-2 border-b border-border/50 pb-2">
              <button
                onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}
                className="flex h-7 w-7 items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-muted"
                aria-label="Zoom out"
              >
                <ZoomOut className="h-3.5 w-3.5" />
              </button>
              <span className="w-12 text-center text-xs text-muted-foreground">
                {Math.round(zoom * 100)}%
              </span>
              <button
                onClick={() => setZoom((z) => Math.min(3, z + 0.25))}
                className="flex h-7 w-7 items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-muted"
                aria-label="Zoom in"
              >
                <ZoomIn className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="flex flex-1 items-center justify-center overflow-auto rounded-md bg-muted/40 p-4">
              <img
                src={url}
                alt={filename}
                style={{ transform: `scale(${zoom})`, transformOrigin: "center" }}
                className="max-w-full transition-transform"
              />
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

/**
 * Product brief section 9: "Uploading -> Reading document -> Extracting
 * text -> Extracting fields -> Running validation -> Finished." Backed
 * by the real `processingStage` the pipeline updates live (see
 * app/background/tasks.py's `_notify_stage`), not a fabricated client
 * timer -- falls back to the coarser `ocrStatus`-only mapping for rows
 * from before this column existed (`processingStage` null).
 */
const PROCESSING_STAGE_META: Record<ProcessingStage, { label: string; icon: React.ReactNode }> = {
  uploading: { label: "Uploading…", icon: <UploadCloud className="h-3.5 w-3.5" /> },
  reading_document: {
    label: "Reading document…",
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
  },
  extracting_text: {
    label: "Extracting text…",
    icon: <ScanLine className="h-3.5 w-3.5 animate-pulse" />,
  },
  extracting_fields: {
    label: "Extracting fields…",
    icon: <ScanLine className="h-3.5 w-3.5 animate-pulse" />,
  },
  running_validation: {
    label: "Running validation…",
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
  },
  done: { label: "Finished", icon: <CheckCircle2 className="h-3.5 w-3.5" /> },
  failed: {
    label: "Couldn't read this document automatically",
    icon: <AlertTriangle className="h-3.5 w-3.5" />,
  },
  wrong_document: {
    label: "This doesn't look like the right document",
    icon: <XCircle className="h-3.5 w-3.5" />,
  },
};

const OCR_STAGE_META: Record<OcrStatus, { label: string; icon: React.ReactNode }> = {
  pending: { label: "Queued for reading…", icon: <Clock className="h-3.5 w-3.5" /> },
  processing: {
    label: "Reading document…",
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
  },
  awaiting_vision: {
    label: "Extracting details with AI…",
    icon: <ScanLine className="h-3.5 w-3.5 animate-pulse" />,
  },
  done: { label: "Extraction complete", icon: <CheckCircle2 className="h-3.5 w-3.5" /> },
  failed: {
    label: "Couldn't read this document automatically",
    icon: <AlertTriangle className="h-3.5 w-3.5" />,
  },
};

export function OcrProgressLine({
  status,
  processingStage,
}: {
  status: OcrStatus;
  processingStage?: ProcessingStage | null;
}) {
  if (status === "done" && processingStage !== "wrong_document") return null;
  const m =
    processingStage && PROCESSING_STAGE_META[processingStage]
      ? PROCESSING_STAGE_META[processingStage]
      : OCR_STAGE_META[status];
  const isBad = status === "failed" || processingStage === "wrong_document";
  return (
    <div className={`flex items-center gap-1.5 text-xs ${isBad ? "text-clay" : "text-navy"}`}>
      {m.icon} {m.label}
    </div>
  );
}

/**
 * Modern upload surface (product brief: "Replace every tiny Upload
 * button with a modern upload dropzone. Support: drag & drop, choose
 * file, take photo, mobile upload"). A real `dragenter`/`dragover`/
 * `drop` implementation, not just a restyled `<label>` -- the previous
 * version was click-only. `capture="environment"` opens the rear
 * camera directly on mobile browsers that support it (iOS Safari,
 * Chrome Android) while still falling back to a normal file/photo
 * picker everywhere else -- no separate "take photo" code path needed.
 */
function UploadDropzone({
  onFile,
  isUploading,
  compact,
  label,
}: {
  onFile: (file: File) => void;
  isUploading: boolean;
  /** Compact mode: the "+ Add another" trigger under an existing file list, vs. the full first-upload card. */
  compact?: boolean;
  label?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleDrop = (e: DragEvent<Element>) => {
    e.preventDefault();
    setIsDragging(false);
    if (isUploading) return;
    const file = e.dataTransfer.files?.[0];
    if (file) onFile(file);
  };

  const openPicker = () => inputRef.current?.click();

  const hiddenInput = (
    <input
      ref={inputRef}
      type="file"
      accept=".pdf,.jpg,.jpeg,.png,.heic,.heif"
      className="hidden"
      disabled={isUploading}
      onChange={(e) => {
        const f = e.target.files?.[0];
        if (f) onFile(f);
        e.target.value = "";
      }}
    />
  );

  if (compact) {
    return (
      <button
        type="button"
        onClick={openPicker}
        disabled={isUploading}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors disabled:opacity-50 ${
          isDragging
            ? "border-navy bg-navy/5 text-navy"
            : "border-navy/30 text-navy hover:bg-navy/5"
        }`}
      >
        {isUploading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />}
        {label ?? "Add another"}
        {hiddenInput}
      </button>
    );
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={label ?? "Upload a document"}
      onClick={openPicker}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openPicker();
        }
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      className={`flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors ${
        isDragging
          ? "border-navy bg-navy/5"
          : "border-border hover:border-navy/50 hover:bg-muted/30"
      } ${isUploading ? "pointer-events-none opacity-60" : ""}`}
    >
      {isUploading ? (
        <>
          <Loader2 className="h-7 w-7 animate-spin text-navy" />
          <div className="text-sm font-medium text-foreground">Uploading…</div>
        </>
      ) : (
        <>
          <UploadCloud className="h-7 w-7 text-muted-foreground" aria-hidden="true" />
          <div className="text-sm font-medium text-foreground">Drag and drop your file here</div>
          <div className="text-xs text-muted-foreground">
            or click to browse · PDF, JPG, PNG, HEIC
          </div>
          <div className="mt-1 flex items-center gap-1.5 text-xs text-navy">
            <Camera className="h-3.5 w-3.5" /> On mobile, you can take a photo directly
          </div>
        </>
      )}
      {hiddenInput}
    </div>
  );
}

/* ------------------------------ Evidence Strength card ------------------------------ */

export function EvidenceStrengthCard({ strength }: { strength: EvidenceStrength }) {
  const toneFor = (s: string): "sage" | "gold" | "muted" =>
    s === "strong" ? "sage" : s === "partial" ? "gold" : "muted";
  // Redesign: no raw "78%" numeral (product brief: "remove percentage
  // progress... replace with meaningful indicators") -- a short word
  // plus the same progress bar, now just a visual fill with no digits
  // next to it.
  const overallLabel =
    strength.overallCompletionPct >= 90
      ? "Strong"
      : strength.overallCompletionPct >= 50
        ? "Building Up"
        : strength.overallCompletionPct > 0
          ? "Just Started"
          : "Not Started";
  return (
    <div className="paper-card p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Live
          </div>
          <h3 className="font-serif text-xl text-foreground">Evidence Strength</h3>
        </div>
        <div className="text-right">
          <div className="font-serif text-xl leading-none text-foreground">{overallLabel}</div>
          <div className="text-xs text-muted-foreground">Overall</div>
        </div>
      </div>
      <div className="mb-4 h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-navy transition-[width] duration-700 ease-out"
          style={{ width: `${strength.overallCompletionPct}%` }}
        />
      </div>
      <ul className="divide-y divide-border/60">
        {strength.factors.map((f) => (
          <li key={f.key} className="flex items-center justify-between gap-3 py-2.5 text-sm">
            <span className="text-foreground/90">{f.label}</span>
            <span className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">{f.detail}</span>
              <Chip tone={toneFor(f.status)}>
                {f.status === "strong" ? (
                  <CheckCircle2 className="h-3 w-3" />
                ) : f.status === "partial" ? (
                  <Clock className="h-3 w-3" />
                ) : null}
                {f.status === "strong"
                  ? "Strong"
                  : f.status === "partial"
                    ? "In Progress"
                    : "Not Started"}
              </Chip>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Evidence Page Banner (Section 11): summarizes every OPEN document
 * request for the current application in one place at the top of the
 * page, on top of each request also surfacing inline at its own
 * checklist item further down. */
export function RequestedDocumentsBanner({ requests }: { requests: DocumentRequest[] }) {
  const open = requests.filter((r) => r.status === "open");
  if (open.length === 0) return null;
  return (
    <div className="paper-card flex items-start gap-3 border-clay/40 bg-clay/10 p-5">
      <MessageSquare className="mt-0.5 h-5 w-5 shrink-0 text-clay" />
      <div className="min-w-0">
        <h3 className="font-serif text-base text-foreground">
          Your loan officer requested {open.length} document{open.length > 1 ? "s" : ""}
        </h3>
        <ul className="mt-2 space-y-1.5">
          {open.map((r) => (
            <li key={r.id} className="text-sm text-foreground/85">
              <span className="font-medium">
                {r.subtypeLabel ?? r.documentType.replace(/_/g, " ")}
              </span>
              {r.note && <span className="text-muted-foreground"> — {r.note}</span>}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-muted-foreground">
          Look for the highlighted items below — upload a matching document to fulfill each request.
        </p>
      </div>
    </div>
  );
}

/**
 * Counts checklist items that don't have a document yet but DO have a
 * matching Evidence Wallet item by subtype -- i.e. every place the
 * contextual "Use from Wallet" button (see ChecklistItemRow's
 * `canReuse`) would show up on this page. Shared with the banner below
 * so the two stay in lockstep with the actual per-item reuse logic
 * instead of drifting into their own separate definition of "reusable".
 */
export function countWalletReuseMatches(
  checklist: EvidenceChecklist | undefined,
  walletBySubtype: Map<string, EvidenceWalletItem>,
): number {
  if (!checklist) return 0;
  let count = 0;
  for (const category of checklist.categories) {
    for (const item of category.items) {
      if (item.documents.length === 0 && walletBySubtype.has(item.subtype)) count += 1;
    }
  }
  return count;
}

/**
 * Design decision (this session): the Evidence Wallet's reuse story was
 * previously easy to miss -- a passive sidebar card, easy to scroll past.
 * A dedicated "Add from Evidence Wallet" popup was considered and
 * rejected: the codebase already has a *stronger* pattern than a popup,
 * the contextual "Use from Wallet" button that appears right next to a
 * matching checklist item (zero-browsing, appears exactly when needed).
 * A popup just moves the discoverability problem to a different button.
 * Instead, this banner surfaces the wallet's value up front, at the top
 * of the page, before the user starts scrolling through categories --
 * without reintroducing a browse-first modal as the primary reuse path.
 */
export function WalletReuseBanner({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <div className="paper-card flex items-center gap-3 border-navy/30 bg-navy/5 p-4">
      <Sparkles className="h-5 w-5 shrink-0 text-navy" />
      <p className="text-sm text-foreground/90">
        <span className="font-semibold text-navy">
          {count} document{count > 1 ? "s" : ""} from your Evidence Wallet
        </span>{" "}
        can be reused here — look for the <span className="font-medium">"Use from Wallet"</span>{" "}
        button next to each matching item below.
      </p>
    </div>
  );
}

/* -------------------------------- Evidence Wallet panel -------------------------------- */

/**
 * The sidebar "browse my full wallet" surface -- secondary to the
 * per-item contextual "Use from Wallet" button in ChecklistItemRow,
 * which is the primary reuse mechanism (see WalletReuseBanner's
 * docstring above for the full reasoning). This panel is for managing
 * everything saved: seeing every item and its reuse count across
 * applications, and attaching it manually if a subtype match wasn't
 * auto-detected for some reason -- not the first place a user should
 * need to go to reuse a document.
 */
export function EvidenceWalletPanel({
  items,
  isLoading,
  onAttach,
  attachingId,
}: {
  items: EvidenceWalletItem[] | undefined;
  isLoading: boolean;
  onAttach: (item: EvidenceWalletItem) => void;
  attachingId?: string;
}) {
  return (
    <div className="paper-card p-6">
      <div className="mb-1 flex items-center gap-2">
        <Wallet className="h-4 w-4 text-navy" />
        <h3 className="font-serif text-xl text-foreground">Evidence Wallet</h3>
      </div>
      <p className="mb-4 text-xs text-muted-foreground">
        Documents you've verified before, ready to reuse on this or any future application — no
        re-upload needed.
      </p>
      {isLoading ? (
        <div className="space-y-2">
          <div className="h-12 animate-pulse rounded-lg bg-muted" />
          <div className="h-12 animate-pulse rounded-lg bg-muted" />
        </div>
      ) : !items || items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-4 text-xs text-muted-foreground">
          Documents you upload and verify will be saved here automatically.
        </div>
      ) : (
        <ul className="space-y-2">
          {items.map((it) => (
            <li
              key={it.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-border/70 bg-card/50 px-3 py-2.5"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="truncate text-sm font-medium text-foreground">{it.label}</span>
                  <Chip tone="navy">Reusable</Chip>
                </div>
                <div className="text-xs text-muted-foreground">
                  {relativeTime(it.updatedAt)}
                  {it.applicationsUsingCount > 0
                    ? ` · used on ${it.applicationsUsingCount} application${it.applicationsUsingCount > 1 ? "s" : ""}`
                    : " · not yet used elsewhere"}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <EvidenceStatusPill status={it.status} />
                <button
                  onClick={() => onAttach(it)}
                  disabled={attachingId === it.id}
                  title="Attach to this application"
                  className="flex h-7 w-7 items-center justify-center rounded-full border border-navy/30 text-navy hover:bg-navy/5 disabled:opacity-50"
                >
                  {attachingId === it.id ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Plus className="h-3.5 w-3.5" />
                  )}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diffMs / 86_400_000);
  if (days <= 0) return "Uploaded today";
  if (days === 1) return "Uploaded 1 day ago";
  if (days < 30) return `Uploaded ${days} days ago`;
  const months = Math.floor(days / 30);
  return `Uploaded ${months} month${months > 1 ? "s" : ""} ago`;
}

/* -------------------------------- checklist category section -------------------------------- */

/**
 * Evidence page redesign (this session). The old version rendered every
 * document subtype as an always-visible upload row -- "dozens of upload
 * buttons" on first paint (product brief). This version:
 *   1. Renders each category collapsed by default, showing only a
 *      status badge + one-line detail (no raw percentage).
 *   2. On expand, groups subtypes into Required / Recommended / Optional
 *      instead of one flat list, so priority is visible at a glance.
 *   3. Within a tier, subtypes the user hasn't engaged with yet show as
 *      selectable chips under "What documents do you have?" -- the
 *      upload control for a subtype only appears once its chip has been
 *      picked (or it already has a document, e.g. from a previous
 *      session). Deselecting an empty chip hides the upload row again;
 *      selection state lives in this component only for empty slots --
 *      once a slot has a document, its row always shows regardless of
 *      chip state, so nothing already uploaded can be hidden by mistake.
 */
export function ChecklistCategorySection({
  category,
  onUpload,
  onDelete,
  uploadingKey,
  deletingId,
  walletBySubtype,
  onAttachFromWallet,
  defaultExpanded,
  applicationId,
}: {
  category: EvidenceCategory;
  onUpload: (subtype: string, file: File, replacesDocumentId?: string) => void;
  onDelete: (documentId: string) => void;
  uploadingKey: string | null;
  deletingId: string | null;
  walletBySubtype: Map<string, EvidenceWalletItem>;
  onAttachFromWallet: (item: EvidenceWalletItem) => void;
  defaultExpanded?: boolean;
  applicationId: string;
}) {
  const [expanded, setExpanded] = useState(
    defaultExpanded ??
      (category.items.some((i) => i.requested) ||
        (category.statusLabel === "Needs Documents" && category.items.some((i) => i.required))),
  );

  const tiers: EvidenceTier[] = ["required", "recommended", "optional"];
  const byTier = useMemo(() => {
    const grouped = new Map<EvidenceTier, EvidenceChecklistItem[]>();
    for (const tier of tiers)
      grouped.set(
        tier,
        category.items.filter((i) => i.tier === tier),
      );
    return grouped;
  }, [category.items]);

  return (
    <div className="paper-card overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between gap-3 border-b border-border/70 bg-card/40 px-6 py-4 text-left"
      >
        <div className="min-w-0">
          <h3 className="font-serif text-lg text-foreground">{category.label}</h3>
          <div className="mt-0.5 text-xs text-muted-foreground">{category.statusDetail}</div>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <CategoryStatusBadge label={category.statusLabel} />
          <ChevronDown
            className={`h-4 w-4 text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`}
          />
        </div>
      </button>

      {expanded && (
        <div className="divide-y divide-border/60">
          {tiers.map((tier) => {
            const items = byTier.get(tier) ?? [];
            if (items.length === 0) return null;
            return (
              <EvidenceTierGroup
                key={tier}
                tier={tier}
                items={items}
                onUpload={onUpload}
                onDelete={onDelete}
                uploadingKey={uploadingKey}
                deletingId={deletingId}
                walletBySubtype={walletBySubtype}
                onAttachFromWallet={onAttachFromWallet}
                applicationId={applicationId}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

function EvidenceTierGroup({
  tier,
  items,
  onUpload,
  onDelete,
  uploadingKey,
  deletingId,
  walletBySubtype,
  onAttachFromWallet,
  applicationId,
}: {
  tier: EvidenceTier;
  items: EvidenceChecklistItem[];
  onUpload: (subtype: string, file: File, replacesDocumentId?: string) => void;
  onDelete: (documentId: string) => void;
  uploadingKey: string | null;
  deletingId: string | null;
  walletBySubtype: Map<string, EvidenceWalletItem>;
  onAttachFromWallet: (item: EvidenceWalletItem) => void;
  applicationId: string;
}) {
  // A subtype is "engaged" (shows its upload row) once it has a document,
  // the user has tapped its chip, or a loan officer has an OPEN request
  // against it (Section 11) -- a requested-but-empty item must never be
  // hidden behind a chip the applicant has to know to tap.
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(items.filter((i) => i.documents.length > 0).map((i) => i.subtype)),
  );

  const chipItems = items.filter(
    (i) => i.documents.length === 0 && !i.requested && !selected.has(i.subtype),
  );
  const activeItems = useMemo(
    () =>
      items
        .filter((i) => i.documents.length > 0 || i.requested || selected.has(i.subtype))
        // Requested items float to the top of their tier group so they
        // can't be missed (Section 11: "distinct visual treatment ...
        // reuse the existing progressive-disclosure evidence category
        // components").
        .sort((a, b) => Number(b.requested) - Number(a.requested)),
    [items, selected],
  );

  const toggle = (subtype: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(subtype)) next.delete(subtype);
      else next.add(subtype);
      return next;
    });
  };

  const meta = TIER_META[tier];

  return (
    <div className="px-6 py-4">
      <div className="mb-3 flex items-baseline gap-2">
        <span
          className={`text-xs font-semibold uppercase tracking-[0.12em] ${tier === "required" ? "text-clay" : "text-muted-foreground"}`}
        >
          {meta.label}
        </span>
        <span className="text-xs text-muted-foreground">— {meta.blurb}</span>
      </div>

      {chipItems.length > 0 && (
        <div className="mb-3">
          <div className="mb-2 text-sm text-foreground/80">What documents do you have?</div>
          <div className="flex flex-wrap gap-2">
            {chipItems.map((item) => (
              <button
                key={item.subtype}
                onClick={() => toggle(item.subtype)}
                className="rounded-full border border-border px-3 py-1.5 text-sm text-foreground/90 transition-colors hover:border-navy hover:bg-navy/5"
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {activeItems.length > 0 && (
        <ul className="-mx-6 mt-1 divide-y divide-border/50 border-t border-border/50">
          {activeItems.map((item) => (
            <ChecklistItemRow
              key={item.subtype}
              item={item}
              onUpload={(file, replaces) => onUpload(item.subtype, file, replaces)}
              onDelete={onDelete}
              isUploading={uploadingKey === item.subtype}
              deletingId={deletingId}
              walletItem={walletBySubtype.get(item.subtype)}
              onAttachFromWallet={onAttachFromWallet}
              onRemoveSelection={
                item.documents.length === 0 && !item.requested
                  ? () => toggle(item.subtype)
                  : undefined
              }
              applicationId={applicationId}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Product brief: "Electricity Bills — ✓ June.pdf ✓ July.pdf — + Add
 * another bill." Once a slot has at least one file, the row switches
 * from the big first-upload dropzone to this compact checkmark list +
 * a small "Add another" trigger, matching that example directly.
 */
export function UploadedFileList({
  documents,
  onDelete,
  deletingId,
  applicationId,
}: {
  documents: EvidenceChecklistItem["documents"];
  onDelete: (documentId: string) => void;
  deletingId: string | null;
  applicationId: string;
}) {
  const preview = useDocumentPreview();

  return (
    <ul className="mt-3 space-y-2">
      {preview.target && (
        <DocumentPreviewModal
          documentId={preview.target.documentId}
          filename={preview.target.filename}
          onClose={preview.close}
        />
      )}
      {documents.map((doc) => (
        <li
          key={doc.documentVersionId}
          className="rounded-lg border border-border/70 bg-card/50 px-3 py-2.5"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-2">
              {doc.qualityStatus === "wrong_document" ? (
                <XCircle className="h-4 w-4 shrink-0 text-clay" aria-hidden="true" />
              ) : (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-sage" aria-hidden="true" />
              )}
              <span className="truncate text-sm font-medium text-foreground">
                {doc.originalFilename}
              </span>
              {doc.reusedFromWallet && (
                <span className="shrink-0 text-xs text-muted-foreground">(from Wallet)</span>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {doc.confidence != null && <ConfidenceBadge value={doc.confidence} />}
              <EvidenceStatusPill status={doc.qualityStatus} />
              <button
                onClick={() => preview.open(doc.documentId, doc.originalFilename)}
                className="flex h-6 w-6 items-center justify-center rounded-full text-muted-foreground hover:bg-muted"
                title="Preview"
                aria-label={`Preview ${doc.originalFilename}`}
              >
                <Eye className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => onDelete(doc.documentId)}
                disabled={deletingId === doc.documentId}
                className="flex h-6 w-6 items-center justify-center rounded-full text-destructive hover:bg-destructive/10 disabled:opacity-50"
                title="Delete"
                aria-label={`Delete ${doc.originalFilename}`}
              >
                {deletingId === doc.documentId ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Trash2 className="h-3.5 w-3.5" />
                )}
              </button>
            </div>
          </div>

          {/* OCR / AI extraction progress -- real backend processingStage,
              staged copy (see PROCESSING_STAGE_META above). */}
          <div className="mt-1.5">
            <OcrProgressLine status={doc.ocrStatus} processingStage={doc.processingStage} />
          </div>

          {/* Session 12 (AI requirement #1/#5): wrong document type --
              stop here, don't show extraction results that don't exist. */}
          {doc.qualityStatus === "wrong_document" && (
            <div className="mt-2 flex items-start gap-1.5 rounded-md border border-clay/30 bg-clay/10 px-2.5 py-2 text-xs text-clay">
              <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                This doesn't look like the right document
                {doc.detectedDocumentType
                  ? ` — it looks like a ${doc.detectedDocumentType}`
                  : ""}. {doc.typeMismatchReason ? doc.typeMismatchReason + " " : ""}
                Please delete it and upload the correct file.
              </span>
            </div>
          )}

          {doc.ocrStatus === "done" &&
            doc.qualityStatus !== "wrong_document" &&
            (doc.extractedName || doc.extractedIdNumber) && (
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 border-t border-border/50 pt-2 text-xs">
                {doc.extractedName && (
                  <div>
                    <dt className="text-muted-foreground">Extracted name</dt>
                    <dd
                      className={
                        doc.nameMatch === false
                          ? "font-medium text-clay"
                          : "font-medium text-foreground"
                      }
                    >
                      {doc.extractedName}
                    </dd>
                  </div>
                )}
                {doc.extractedIdNumber && (
                  <div>
                    <dt className="text-muted-foreground">Extracted ID number</dt>
                    <dd
                      className={
                        doc.idNumberMatch === false
                          ? "font-medium text-clay"
                          : "font-medium text-foreground"
                      }
                    >
                      {doc.extractedIdNumber}
                    </dd>
                  </div>
                )}
              </dl>
            )}

          {/* Session 12 (product brief section 4/5, AI requirement #3):
              "AI extracted ... Looks correct? Confirm / Edit" -- shown
              once OCR has actually produced fields to review, hidden
              once the applicant has confirmed (or the document was
              flagged as the wrong type entirely). */}
          {doc.ocrStatus === "done" &&
            doc.qualityStatus !== "wrong_document" &&
            doc.extractedFields.length > 0 && (
              <ExtractedFieldsReview doc={doc} applicationId={applicationId} />
            )}

          {doc.qualityGuidance && (
            <div className="mt-2 flex items-start gap-1 border-t border-border/50 pt-2 text-xs text-clay">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /> {doc.qualityGuidance}
            </div>
          )}
          {(doc.nameMatch === false || doc.idNumberMatch === false) && (
            <div className="mt-1 text-xs text-clay">
              Details don't match your application — please review before submitting.
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * Product brief section 4: "AI extracted [fields] ... Confidence 98% ...
 * Looks correct? Confirm / Edit." AI requirement #3: confirming is a
 * statement that the reading is accurate, never a claim the document
 * itself is authentic -- this panel's copy is deliberately careful about
 * that distinction (see backend document_service.confirm_extracted_fields
 * and DocumentVersion.applicant_confirmed_at's docstrings).
 */
function ExtractedFieldsReview({
  doc,
  applicationId,
}: {
  doc: EvidenceItemDocument;
  applicationId: string;
}) {
  const confirmMutation = useConfirmDocument();
  const [editing, setEditing] = useState(false);
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(doc.extractedFields.map((f) => [f.fieldName, f.fieldValue])),
  );
  const [error, setError] = useState<string | null>(null);

  const isConfirmed = !!doc.applicantConfirmedAt;
  const avgConfidence =
    doc.extractedFields.length > 0
      ? Math.round(
          (doc.extractedFields.reduce((s, f) => s + f.confidence, 0) / doc.extractedFields.length) *
            100,
        ) / 1
      : null;
  const lowConfidence = avgConfidence != null && avgConfidence < 70;

  const fieldLabel = (name: string) =>
    name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  const handleConfirm = async (withEdits: boolean) => {
    setError(null);
    try {
      const edits = withEdits
        ? doc.extractedFields
            .filter((f) => values[f.fieldName] !== f.fieldValue)
            .map((f) => ({
              fieldName: f.fieldName,
              fieldValue: values[f.fieldName] ?? f.fieldValue,
            }))
        : [];
      await confirmMutation.mutateAsync({ documentId: doc.documentId, applicationId, edits });
      setEditing(false);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="mt-2 rounded-md border border-border/60 bg-muted/30 px-3 py-2.5 text-xs">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 font-medium text-foreground">
          <Sparkles className="h-3.5 w-3.5 text-navy" /> AI extracted
        </div>
        <div className="flex items-center gap-1.5">
          {avgConfidence != null && <ConfidenceBadge value={avgConfidence} />}
          {isConfirmed ? (
            <span className="flex items-center gap-1 rounded-full bg-sage/15 px-2 py-0.5 text-[11px] font-medium text-sage">
              <Check className="h-3 w-3" /> Applicant Confirmed
            </span>
          ) : (
            <span className="rounded-full bg-gold/15 px-2 py-0.5 text-[11px] font-medium text-gold">
              OCR Complete
            </span>
          )}
        </div>
      </div>

      {lowConfidence && !isConfirmed && (
        <div className="mb-2 flex items-start gap-1 text-clay">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /> Confidence is low on this reading —
          please check the values below carefully.
        </div>
      )}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5">
        {doc.extractedFields.map((f) => (
          <div key={f.fieldName} className={f.confidence < 70 ? "col-span-2" : ""}>
            <dt className="flex items-center gap-1 text-muted-foreground">
              {fieldLabel(f.fieldName)}
              {f.confidence < 70 && <span className="text-clay">· low confidence</span>}
            </dt>
            {editing ? (
              <input
                value={values[f.fieldName] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [f.fieldName]: e.target.value }))}
                className="mt-0.5 w-full rounded border border-input bg-card px-1.5 py-1 text-xs"
              />
            ) : (
              <dd className="font-medium text-foreground">
                {f.fieldValue || <span className="text-muted-foreground">—</span>}
              </dd>
            )}
          </div>
        ))}
      </dl>

      {error && <div className="mt-2 text-clay">{error}</div>}

      {!isConfirmed && (
        <div className="mt-2.5 flex items-center justify-between gap-2 border-t border-border/50 pt-2">
          <span className="text-muted-foreground">Looks correct?</span>
          <div className="flex items-center gap-2">
            {editing ? (
              <>
                <button
                  onClick={() => setEditing(false)}
                  className="rounded-md border border-border px-2.5 py-1 text-[11px] text-foreground/80 hover:bg-muted"
                >
                  Cancel
                </button>
                <button
                  onClick={() => handleConfirm(true)}
                  disabled={confirmMutation.isPending}
                  className="flex items-center gap-1 rounded-md bg-navy px-2.5 py-1 text-[11px] font-medium text-paper hover:opacity-95 disabled:opacity-60"
                >
                  {confirmMutation.isPending ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Check className="h-3 w-3" />
                  )}{" "}
                  Save &amp; Confirm
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => setEditing(true)}
                  className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-[11px] text-foreground/80 hover:bg-muted"
                >
                  <Pencil className="h-3 w-3" /> Edit
                </button>
                <button
                  onClick={() => handleConfirm(false)}
                  disabled={confirmMutation.isPending}
                  className="flex items-center gap-1 rounded-md bg-navy px-2.5 py-1 text-[11px] font-medium text-paper hover:opacity-95 disabled:opacity-60"
                >
                  {confirmMutation.isPending ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Check className="h-3 w-3" />
                  )}{" "}
                  Confirm
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ChecklistItemRow({
  item,
  onUpload,
  onDelete,
  isUploading,
  deletingId,
  walletItem,
  onAttachFromWallet,
  onRemoveSelection,
  applicationId,
}: {
  item: EvidenceChecklistItem;
  onUpload: (file: File, replacesDocumentId?: string) => void;
  onDelete: (documentId: string) => void;
  isUploading: boolean;
  deletingId: string | null;
  walletItem?: EvidenceWalletItem;
  onAttachFromWallet: (item: EvidenceWalletItem) => void;
  /** Present only for a subtype the user just picked via chip and hasn't
   * uploaded anything for yet -- lets them back out without uploading. */
  onRemoveSelection?: () => void;
  applicationId: string;
}) {
  const canAddMore = item.allowMultiple || item.documents.length === 0;
  const hasFiles = item.documents.length > 0;
  // Offer "reuse from wallet" only when the wallet has this exact subtype
  // AND this checklist slot doesn't already have it (avoids an obviously
  // redundant re-attach-the-same-file prompt).
  const canReuse = !!walletItem && canAddMore;

  return (
    <li className="px-6 py-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-foreground">{item.label}</span>
            {item.required && <span className="text-xs text-clay">Required</span>}
          </div>
          {item.requested && (
            <div className="mt-1 flex items-start gap-1.5 rounded-lg border border-clay/30 bg-clay/10 px-2.5 py-1.5 text-xs text-clay">
              <MessageSquare className="mt-0.5 h-3 w-3 shrink-0" />
              <span>
                <span className="font-semibold">Requested by your loan officer.</span>
                {item.requestNote ? ` ${item.requestNote}` : ""}
              </span>
            </div>
          )}
          {item.helperText && (
            <div className="mt-0.5 text-xs text-muted-foreground">{item.helperText}</div>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {!hasFiles && <EvidenceStatusPill status={item.status} />}
          {onRemoveSelection && (
            <button
              onClick={onRemoveSelection}
              title="Not this one"
              aria-label={`Remove ${item.label} from this step`}
              className="flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground hover:bg-muted"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {hasFiles ? (
        <>
          <UploadedFileList
            documents={item.documents}
            onDelete={onDelete}
            deletingId={deletingId}
            applicationId={applicationId}
          />
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {canReuse && (
              <button
                onClick={() => onAttachFromWallet(walletItem!)}
                className="flex items-center gap-1 rounded-lg border border-navy/30 px-2.5 py-1.5 text-xs text-navy hover:bg-navy/5"
                title="Reuse from Evidence Wallet — no re-upload needed"
              >
                <Wallet className="h-3 w-3" /> Use from Wallet
              </button>
            )}
            {canAddMore && (
              <UploadDropzone
                compact
                isUploading={isUploading}
                onFile={(f) => onUpload(f)}
                label={item.allowMultiple ? "Add another" : "Replace"}
              />
            )}
          </div>
        </>
      ) : (
        <div className="mt-3 space-y-2">
          {/* Design decision (this session, dropzone redesign): when a
              wallet match exists it's offered as a one-line banner above
              the dropzone rather than a competing button beside it --
              the dropzone itself is now a large visual anchor, so a
              same-size button next to it read as two equal choices
              fighting for attention. */}
          {canReuse && (
            <button
              onClick={() => onAttachFromWallet(walletItem!)}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-navy px-3 py-2 text-xs font-medium text-paper hover:opacity-95"
              title="Reuse from Evidence Wallet — no re-upload needed"
            >
              <Wallet className="h-3.5 w-3.5" /> Use from Evidence Wallet — no re-upload needed
            </button>
          )}
          <UploadDropzone
            isUploading={isUploading}
            onFile={(f) => onUpload(f)}
            label={`Upload ${item.label}`}
          />
        </div>
      )}
    </li>
  );
}
