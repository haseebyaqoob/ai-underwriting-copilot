/**
 * TypeScript mirrors of backend/app/schemas/application.py and
 * document.py. Field names are camelCase because api-client.ts transforms
 * every JSON response's keys snake_case -> camelCase generically -- these
 * types describe the *post-transform* shape the rest of the app sees.
 *
 * `amount_pkr`/`total_volume_pkr` are Postgres NUMERIC columns, which
 * FastAPI/Pydantic serialize as JSON strings (not numbers) to avoid float
 * precision loss -- so `amountPkr` here is `string`, and call sites use
 * `Number(...)` before formatting with `fmtPKR`.
 */
import type { AppStatus } from "@/lib/utils";

export type RiskLevel = "low" | "moderate" | "elevated";
export type DocumentType =
  "khata" | "utility_bills" | "wallet_statements" | "tax_filing" | "invoice" | "other" | "cnic";
export type OcrStatus = "pending" | "processing" | "awaiting_vision" | "done" | "failed";

export interface TimelineEntry {
  at: string;
  label: string;
  actorType: string;
  actorName: string;
}

/** Real, computed from `evidence_transactions` grouped by document type --
 * replaces the old fabricated `EvidenceItem` fixture list entirely. One
 * entry per document type that has at least one normalized transaction. */
export interface EvidenceCoverage {
  sourceType: string;
  transactionCount: number;
  dateRangeStart: string | null;
  dateRangeEnd: string | null;
  avgConfidence: number;
}

/** Real, computed by the revenue estimator from `evidence_transactions`.
 * A band (low/high), not one blended number, and every `*MonthlyPkr`
 * field is `null` -- never a fabricated 0 or placeholder -- when there
 * isn't enough dated inflow evidence yet. */
export interface RevenueEstimate {
  verifiedFloorMonthlyPkr: string | null;
  blendedEstimateLowMonthlyPkr: string | null;
  blendedEstimateHighMonthlyPkr: string | null;
  windowStart: string | null;
  windowEnd: string | null;
  weeksOfData: number;
  monthsOfData: number;
  sourceTypesUsed: string[];
  plausibilityFlag: boolean;
  plausibilityNote: string | null;
}

export interface ScoreFactor {
  key: string;
  label: string;
  weightPct: number;
  factorScore: number;
  explanation: string;
}

export interface DebtExposure {
  status: string;
  note: string;
}

export interface ReadinessChecklistItem {
  key: string;
  label: string;
  met: boolean;
  detail: string;
}

/** Real "insufficient evidence" state -- rendered instead of a score when
 * fewer than 2 independent document types are present, the observed
 * window is under ~2 weeks, or the CNIC fails structural validation. A
 * first-class UI state, never a degraded/low score. */
export interface InsufficientEvidenceAssessment {
  status: "insufficient_evidence";
  reasons: string[];
  missingDocumentTypes: string[];
  documentTypesPresent: string[];
  weeksOfData: number;
  /** Application Review redesign: the same facts as `reasons`, as an
   * actionable checklist instead of prose paragraphs. */
  readinessChecklist: ReadinessChecklistItem[];
}

export interface ScoredAssessment {
  status: "scored";
  score: number;
  confidence: number;
  riskLevel: RiskLevel;
  factors: ScoreFactor[];
  debtExposure: DebtExposure;
  weeksOfData: number;
}

export type Assessment = ScoredAssessment | InsufficientEvidenceAssessment;

/** `message` is already the correct copy for whichever viewer requested
 * it (generic for a failed check on the applicant's own view, specific
 * for officer/admin) -- the backend picks it, never the frontend. */
export interface ConsistencyCheck {
  checkId: string;
  passed: boolean;
  message: string;
}

export type DecisionReasonCode =
  | "strong_cashflow_evidence"
  | "adequate_evidence_coverage"
  | "acceptable_debt_service_ratio"
  | "insufficient_evidence"
  | "high_risk_inconsistency"
  | "debt_service_coverage_low"
  | "income_instability"
  | "missing_wallet_statement"
  | "missing_khata"
  | "missing_utility_bill"
  | "missing_cnic"
  | "unclear_document_quality"
  | "other";

export interface ApplicationListItem {
  id: string;
  displayId: string;
  businessName: string;
  city: string;
  amountPkr: string;
  purpose: string;
  status: AppStatus;
  /** Presentation-layer refinement of `status` -- see
   * backend/app/services/workflow_stage_service.py. */
  workflowStage: WorkflowStageKey;
  workflowStageLabel: string;
  score: number | null;
  confidence: number | null;
  riskLevel: RiskLevel | null;
  documentsCount: number;
  officerName: string | null;
  applicantName: string;
  createdAt: string;
  updatedAt: string;
}

export type WorkflowStageKey =
  | "draft"
  | "documents_processing"
  | "evidence_verified"
  | "ai_underwriting"
  | "officer_review"
  | "additional_evidence_requested"
  | "approved"
  | "rejected"
  | "withdrawn";

export interface ProcessingStep {
  key: string;
  label: string;
  status: "pending" | "in_progress" | "complete";
  detail: string;
}

export interface ApplicationDetail extends ApplicationListItem {
  businessType: string | null;
  ownerName: string | null;
  yearsOperating: number | null;
  employeeCount: number | null;
  tenorMonths: number | null;
  preferredRepayment: string | null;
  registrationStatus: "registered" | "unregistered";
  ntn: string | null;
  strn: string | null;
  monthlyEstimatedRevenuePkr: string | null;
  monthlyEstimatedExpensesPkr: string | null;
  /** Full CNIC for the owning applicant's own view; masked
   * ("42101-XXXXXXX-1") for officer/admin views -- the backend decides
   * which one this is, per-request, in application_service.py. */
  cnicNumber: string | null;
  evidence: EvidenceCoverage[];
  timeline: TimelineEntry[];
  revenue: RevenueEstimate | null;
  assessment: Assessment | null;
  consistencyChecks: ConsistencyCheck[];
  /** AI Processing page's step list -- see workflow_stage_service.py.
   * Real, not a fixed-duration fake sequence: each step's status is read
   * off actual document/assessment state. */
  processingSteps: ProcessingStep[];
  evidenceCompletionPct: number;
}

export interface PaginatedApplications {
  items: ApplicationListItem[];
  total: number;
  page: number;
  pageSize: number;
}

export interface EvidenceSummaryLine {
  key: string;
  label: string;
  status: string;
}

export interface ApplicantDashboard {
  activeApplicationCount: number;
  totalApplicationCount: number;
  recentApplications: ApplicationListItem[];
  activityTimeline: TimelineEntry[];
  primaryApplicationId: string | null;
  evidenceCompletionPct: number | null;
  missingRequiredEvidence: string[];
  /** Dashboard redesign: friendly replacement for the raw completion
   * percentage -- e.g. "Identity — Verified", "Financial Records —
   * Needs Documents". */
  evidenceSummary: EvidenceSummaryLine[];
  /** Dashboard redesign: single computed "what do I do next" instruction
   * -- the first still-missing required checklist item, e.g. "Shop
   * Interior Photo". `null` once nothing required is missing. */
  nextStepLabel: string | null;
  /** True when a saved Evidence Wallet item already matches the next
   * step's subtype -- lets the dashboard offer "Use from Wallet" instead
   * of "Upload" for that one line. */
  nextStepWalletAvailable: boolean;
  walletReusableCount: number;
  aiActivity: TimelineEntry[];
}

export interface OfficerDashboard {
  queueCount: number;
  approvalsLast30d: number;
  rejectionsLast30d: number;
  avgTimeToDecisionMinutes: number | null;
  statusBreakdown: Record<string, number>;
}

export interface AdminDashboard {
  totalApplications: number;
  submittedLast30d: number;
  approvalRate: number | null;
  statusBreakdown: Record<string, number>;
  totalVolumePkr: string;
}

export interface ApplicationCreateInput {
  businessName: string;
  businessType: string;
  ownerName: string;
  city: string;
  yearsOperating: number;
  employeeCount: number;
  amountPkr: number;
  tenorMonths: number;
  purpose: string;
  preferredRepayment: string;
  cnicNumber?: string | null;
  registrationStatus: "registered" | "unregistered";
  ntn?: string | null;
  strn?: string | null;
  monthlyEstimatedRevenuePkr?: number | null;
  monthlyEstimatedExpensesPkr?: number | null;
}

export interface DocumentQueueItem {
  documentId: string;
  documentVersionId: string;
  versionNo: number;
  type: DocumentType;
  originalFilename: string;
  sizeBytes: number;
  ocrStatus: OcrStatus;
  confidence: number | null;
  note: string;
  createdAt: string;
}

export interface DocumentUploadResult {
  documentId: string;
  documentVersionId: string;
  versionNo: number;
  type: DocumentType;
  originalFilename: string;
  sizeBytes: number;
  ocrStatus: OcrStatus;
}

/* --------------------------- Evidence Checklist / Wallet -------------------------- *
 * Mirrors backend/app/schemas/document.py's EvidenceChecklistOut/
 * EvidenceWalletItemOut. `EvidenceQualityStatus` is intentionally a plain
 * string union here, not a backend-shared const, matching the backend's
 * own "plain String column, not a native ENUM" choice (see
 * app/db/models/enums.py's EvidenceQualityStatus docstring) -- both sides
 * expect this list to keep growing.
 */
export type EvidenceQualityStatus =
  | "missing"
  | "uploaded"
  | "processing"
  | "verified"
  | "needs_better_image"
  | "mismatch"
  | "wrong_document";

/** Session 12 -- the granular sub-stage within `ocrStatus`, mirrors
 * backend `DocumentVersion.processing_stage`. Drives the "Uploading ->
 * Reading document -> Extracting text -> Extracting fields -> Running
 * validation -> Finished" progress line (product brief section 9). */
export type ProcessingStage =
  | "uploading"
  | "reading_document"
  | "extracting_text"
  | "extracting_fields"
  | "running_validation"
  | "done"
  | "failed"
  | "wrong_document";

export interface ExtractedFieldItem {
  fieldName: string;
  fieldValue: string;
  valueType: string;
  confidence: number;
  sourcePage: number | null;
  extractionSource: string;
}

export interface EvidenceItemDocument {
  documentId: string;
  documentVersionId: string;
  originalFilename: string;
  sizeBytes: number;
  ocrStatus: OcrStatus;
  processingStage: ProcessingStage | null;
  qualityStatus: EvidenceQualityStatus;
  qualityIssues: string[];
  qualityGuidance: string | null;
  confidence: number | null;
  extractedName: string | null;
  extractedIdNumber: string | null;
  nameMatch: boolean | null;
  idNumberMatch: boolean | null;
  reusedFromWallet: boolean;
  createdAt: string;
  /** Session 12 (AI requirement #1/#5): set once a document-type check has
   * run. `typeMatch === false` means the AI thinks this isn't the expected
   * document at all -- see `detectedDocumentType`/`typeMismatchReason`. */
  detectedDocumentType: string | null;
  typeMatch: boolean | null;
  typeMismatchReason: string | null;
  /** Session 12 (AI requirement #3): set once the applicant has confirmed
   * the extracted reading is accurate. NOT a document-authenticity claim
   * -- see backend DocumentVersion.applicant_confirmed_at's docstring. */
  applicantConfirmedAt: string | null;
  extractedFields: ExtractedFieldItem[];
}

export type EvidenceTier = "required" | "recommended" | "optional";

export interface EvidenceChecklistItem {
  subtype: string;
  label: string;
  required: boolean;
  tier: EvidenceTier;
  allowMultiple: boolean;
  helperText: string;
  status: EvidenceQualityStatus;
  documents: EvidenceItemDocument[];
  /** Section 11 (Document Request workflow): true when a loan officer has
   * an OPEN request against this exact subtype (or its coarse document
   * type). Evidence page renders this with a distinct "Requested by your
   * loan officer" treatment and floats it to the top of its tier group. */
  requested: boolean;
  requestNote: string | null;
}

export interface EvidenceCategory {
  key: string;
  label: string;
  items: EvidenceChecklistItem[];
  completionPct: number;
  /** Badge word ("Verified"/"Strong"/"Good"/"Pending"/"Needs Documents")
   * + one-line detail ("2 documents uploaded") -- replaces a raw
   * percentage in the UI. `completionPct` above only sizes a progress
   * bar's fill; it's never rendered as a number. */
  statusLabel: string;
  statusDetail: string;
}

export interface EvidenceStrengthFactor {
  key: string;
  label: string;
  status: "strong" | "partial" | "missing";
  detail: string;
}

export interface EvidenceStrength {
  factors: EvidenceStrengthFactor[];
  overallCompletionPct: number;
}

export interface EvidenceChecklist {
  applicationId: string;
  categories: EvidenceCategory[];
  overallCompletionPct: number;
  strength: EvidenceStrength;
  /** Section 11: every OPEN DocumentRequest on this application -- the
   * Evidence Page Banner's data source. */
  openRequests: DocumentRequest[];
}

export interface EvidenceWalletItem {
  id: string;
  subtype: string;
  label: string;
  category: string;
  status: EvidenceQualityStatus;
  originalFilename: string;
  latestDocumentId: string | null;
  latestDocumentVersionId: string | null;
  timesReused: number;
  /** Distinct applications currently holding a document of this
   * subtype -- the Evidence Wallet redesign's "number of applications
   * using it". */
  applicationsUsingCount: number;
  updatedAt: string;
}

/* ------------------------------ notifications ---------------------------- */

export type NotificationSeverity = "info" | "action_required" | "decision";

export interface Notification {
  id: string;
  title: string;
  body: string;
  type: NotificationSeverity;
  eventType: string | null;
  applicationId: string | null;
  documentId: string | null;
  read: boolean;
  createdAt: string;
}

export interface NotificationList {
  items: Notification[];
  total: number;
  unreadCount: number;
  page: number;
  pageSize: number;
}

/* --------------------- Section 10/11: officer review page --------------------- *
 * Mirrors backend/app/schemas/document.py + application.py's new
 * OfficerNoteOut/DocumentRequestOut/DocumentReviewOut/
 * OfficerDocumentDetailOut/WalletUsageOut/OfficerApplicationDetailOut.
 */

export interface OfficerNote {
  id: string;
  applicationId: string;
  documentId: string | null;
  officerId: string | null;
  officerName: string | null;
  body: string;
  createdAt: string;
}

export interface DocumentRequest {
  id: string;
  applicationId: string;
  documentType: DocumentType;
  subtype: string | null;
  subtypeLabel: string | null;
  note: string | null;
  status: "open" | "fulfilled" | "cancelled";
  requestedByOfficerName: string | null;
  fulfilledByDocumentId: string | null;
  fulfilledAt: string | null;
  createdAt: string;
}

export type DocumentReviewAction =
  "approved" | "rejected" | "replacement_requested" | "additional_evidence_requested";

export interface DocumentReview {
  id: string;
  documentId: string;
  officerId: string | null;
  officerName: string | null;
  action: DocumentReviewAction;
  note: string | null;
  createdAt: string;
}

export interface ExtractedField {
  fieldName: string;
  fieldValue: string;
  valueType: string;
  confidence: number;
  sourcePage: number | null;
  extractionSource: string;
}

export interface DocumentVersionDetail {
  documentVersionId: string;
  versionNo: number;
  sizeBytes: number;
  pageCount: number | null;
  ocrStatus: OcrStatus;
  processingStage: ProcessingStage | null;
  confidence: number | null;
  qualityStatus: EvidenceQualityStatus;
  qualityIssues: string[];
  qualityGuidance: string | null;
  extractedName: string | null;
  extractedIdNumber: string | null;
  extractedExpiryDate: string | null;
  nameMatch: boolean | null;
  idNumberMatch: boolean | null;
  detectedDocumentType: string | null;
  typeMatch: boolean | null;
  typeMismatchReason: string | null;
  applicantConfirmedAt: string | null;
  extractedFields: ExtractedField[];
  createdAt: string;
}

export interface OfficerDocumentDetail {
  documentId: string;
  type: DocumentType;
  subtype: string | null;
  subtypeLabel: string | null;
  originalFilename: string;
  reusedFromWallet: boolean;
  uploadedAt: string;
  currentReviewStatus: DocumentReviewAction | null;
  versions: DocumentVersionDetail[];
  notes: OfficerNote[];
  reviews: DocumentReview[];
}

export interface WalletUsage {
  fromWallet: number;
  freshUploads: number;
}

export interface OfficerApplicationDetail extends ApplicationDetail {
  walletUsage: WalletUsage;
  openDocumentRequests: DocumentRequest[];
}
