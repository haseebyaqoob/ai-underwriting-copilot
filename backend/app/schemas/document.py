import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import DocumentType, OcrStatus


class DocumentUploadOut(BaseModel):
    """Response to a successful POST /applicant/documents."""

    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    document_version_id: uuid.UUID
    version_no: int
    type: DocumentType
    original_filename: str
    size_bytes: int
    ocr_status: OcrStatus


class DocumentQueueItemOut(BaseModel):
    """
    Matches the shape of the "Recent uploads" panel in applicant.upload.tsx
    (`{name, size, confidence, status, note}`) as closely as a real,
    persisted record can — see docs/ARCHITECTURE_AND_PROGRESS.md for the
    field-naming note (snake_case here vs the frontend's shape; no frontend
    route calls this endpoint yet so there's no contract being broken).
    """

    document_id: uuid.UUID
    document_version_id: uuid.UUID
    version_no: int
    type: DocumentType
    original_filename: str
    size_bytes: int
    ocr_status: OcrStatus
    confidence: float | None
    note: str
    created_at: datetime


class DocumentQueueOut(BaseModel):
    items: list[DocumentQueueItemOut]


# ---------------------------------------------------------------------------
# Evidence Checklist / Evidence Wallet -- see
# app/services/evidence_checklist_service.py and evidence_wallet_service.py
# for the assembly logic these mirror field-for-field.
# ---------------------------------------------------------------------------


class ExtractedFieldEditIn(BaseModel):
    """One field value being corrected by the applicant before/instead of
    confirming as-is. `field_name` must match an existing ExtractedField
    on the document's latest version."""

    field_name: str
    field_value: str = Field(max_length=2000)


class DocumentConfirmIn(BaseModel):
    """Body for POST /applicant/documents/{document_id}/confirm.

    `edits` is optional: an applicant can either confirm the AI's reading
    as-is (empty/omitted list) or correct one or more fields first, which
    applies the edits AND records the confirmation in the same call --
    see document_service.confirm_extracted_fields. Editing a field always
    marks it `extraction_source="applicant_corrected"` rather than
    silently overwriting what the AI actually read, per the product
    brief's \"applicant confirming does not mean the document is
    authentic\" distinction: we keep the provenance, not just the value.
    """

    edits: list[ExtractedFieldEditIn] = Field(default_factory=list)


class DocumentConfirmOut(BaseModel):
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    applicant_confirmed_at: datetime
    fields_edited: int


class EvidenceItemDocumentOut(BaseModel):
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    original_filename: str
    size_bytes: int
    ocr_status: str
    processing_stage: str | None
    quality_status: str
    quality_issues: list[str]
    quality_guidance: str | None
    confidence: float | None
    extracted_name: str | None
    extracted_id_number: str | None
    name_match: bool | None
    id_number_match: bool | None
    reused_from_wallet: bool
    created_at: str
    # Session 12 additions -----------------------------------------
    detected_document_type: str | None
    type_match: bool | None
    type_mismatch_reason: str | None
    applicant_confirmed_at: datetime | None
    extracted_fields: list["ExtractedFieldOut"] = []


class EvidenceChecklistItemOut(BaseModel):
    subtype: str
    label: str
    required: bool
    tier: str  # "required" | "recommended" | "optional"
    allow_multiple: bool
    helper_text: str
    status: str
    documents: list[EvidenceItemDocumentOut]
    # Section 11 (Document Request workflow): True when an officer has an
    # OPEN DocumentRequest against this exact subtype (or its coarse
    # document_type, for a whole-application request-docs decision that
    # didn't name a specific subtype) -- see
    # evidence_checklist_service.build_checklist's request-matching logic.
    # The Evidence page renders this with a distinct "Requested by your
    # loan officer" treatment and floats it to the top of its tier group.
    requested: bool = False
    request_note: str | None = None


class EvidenceCategoryOut(BaseModel):
    key: str
    label: str
    items: list[EvidenceChecklistItemOut]
    completion_pct: int
    # Badge word ("Verified"/"Strong"/"Good"/"Pending"/"Needs Documents")
    # + one-line human detail ("2 documents uploaded") -- what the
    # Evidence page renders. `completion_pct` stays on the payload only
    # to size a progress-bar fill, never shown as a number.
    status_label: str
    status_detail: str


class EvidenceStrengthFactorOut(BaseModel):
    key: str
    label: str
    status: str
    detail: str


class EvidenceStrengthOut(BaseModel):
    factors: list[EvidenceStrengthFactorOut]
    overall_completion_pct: int


class EvidenceChecklistOut(BaseModel):
    application_id: uuid.UUID
    categories: list[EvidenceCategoryOut]
    overall_completion_pct: int
    strength: EvidenceStrengthOut
    # Section 11 (Document Request workflow): the Evidence Page Banner's
    # data source -- every OPEN DocumentRequest on this application, so
    # the banner can summarize them without a second round trip. Forward
    # reference (DocumentRequestOut is defined further down this file) --
    # resolved via model_rebuild() at the bottom of the module.
    open_requests: list["DocumentRequestOut"] = []


class EvidenceWalletItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subtype: str
    label: str
    category: str
    status: str
    original_filename: str
    latest_document_id: uuid.UUID | None
    latest_document_version_id: uuid.UUID | None
    times_reused: int
    # Distinct applications (owned by this user) currently holding a
    # document of this subtype -- see
    # evidence_wallet_service.applications_using_count. Product brief:
    # "number of applications using it".
    applications_using_count: int = 0
    updated_at: datetime


class AttachFromWalletIn(BaseModel):
    application_id: uuid.UUID
    wallet_item_id: uuid.UUID


class ReadinessChecklistItemOut(BaseModel):
    """Application Review's actionable checklist -- see
    evidence_checklist_service.build_readiness_checklist."""

    key: str
    label: str
    met: bool
    detail: str


# ---------------------------------------------------------------------------
# Section 10/11: Loan Officer review page + Document Request workflow -- see
# app/services/officer_review_service.py for the assembly logic these
# mirror field-for-field.
# ---------------------------------------------------------------------------


class OfficerNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    document_id: uuid.UUID | None
    officer_id: uuid.UUID | None
    officer_name: str | None
    body: str
    created_at: datetime


class OfficerNoteCreateIn(BaseModel):
    """Body for POST /officer/applications/{id}/notes. `document_id` is
    optional -- omit it for a whole-application note, set it to scope the
    note to one specific document (surfaced in that document's review
    sub-view). Either way it lands on the applicant's own timeline (see
    officer_review_service.create_officer_note) and fires
    `NotificationEventType.officer_comment`."""

    body: str = Field(min_length=1, max_length=2000)
    document_id: uuid.UUID | None = None


class DocumentRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    document_type: DocumentType
    subtype: str | None
    subtype_label: str | None
    note: str | None
    status: str  # "open" | "fulfilled" | "cancelled"
    requested_by_officer_name: str | None
    fulfilled_by_document_id: uuid.UUID | None
    fulfilled_at: datetime | None
    created_at: datetime


class DocumentReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    officer_id: uuid.UUID | None
    officer_name: str | None
    action: str  # "approved" | "rejected" | "replacement_requested" | "additional_evidence_requested"
    note: str | None
    created_at: datetime


class DocumentReviewCreateIn(BaseModel):
    """Body for POST /officer/documents/{document_id}/review. Per-document
    decision, distinct from the whole-application approve/reject/
    request-docs actions in application_service.decide_application.
    `replacement_requested`/`additional_evidence_requested` also create a
    concrete, trackable `DocumentRequest` row (see
    officer_review_service.review_document) tied to this exact document's
    evidence-catalog subtype, so it surfaces on the applicant's Evidence
    page the same way a whole-application request-docs decision does."""

    action: Literal["approved", "rejected", "replacement_requested", "additional_evidence_requested"]
    note: str | None = Field(default=None, max_length=2000)


class ExtractedFieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field_name: str
    field_value: str
    value_type: str
    confidence: float
    source_page: int | None
    extraction_source: str


class DocumentVersionDetailOut(BaseModel):
    """One row per `DocumentVersion` -- the officer per-document review
    sub-view's "previous versions" list, each with its own extracted
    fields (DocumentVersion history + ExtractedField rows already exist,
    per the brief's "surface it fully, don't re-derive it")."""

    document_version_id: uuid.UUID
    version_no: int
    size_bytes: int
    page_count: int | None
    ocr_status: OcrStatus
    processing_stage: str | None
    confidence: float | None
    quality_status: str
    quality_issues: list[str]
    quality_guidance: str | None
    extracted_name: str | None
    extracted_id_number: str | None
    extracted_expiry_date: str | None
    name_match: bool | None
    id_number_match: bool | None
    detected_document_type: str | None
    type_match: bool | None
    type_mismatch_reason: str | None
    # Officers see confirmation status but never a claim of authenticity
    # (see DocumentVersion.applicant_confirmed_at's model docstring) --
    # this is "the applicant said this reading is accurate", nothing more.
    applicant_confirmed_at: datetime | None
    extracted_fields: list[ExtractedFieldOut]
    created_at: datetime


class OfficerDocumentDetailOut(BaseModel):
    """One uploaded document's full officer review sub-view: preview
    metadata, every version's extracted fields, officer notes scoped to
    this document, its review action history, and whether it fulfilled an
    open document request."""

    document_id: uuid.UUID
    type: DocumentType
    subtype: str | None
    subtype_label: str | None
    original_filename: str
    reused_from_wallet: bool
    uploaded_at: datetime
    current_review_status: str | None  # latest DocumentReview.action, or None if never reviewed
    versions: list[DocumentVersionDetailOut]
    notes: list[OfficerNoteOut]
    reviews: list[DocumentReviewOut]


class WalletUsageOut(BaseModel):
    """Officer review page's "Wallet Usage" panel -- how many of this
    application's uploaded documents came from the applicant's Evidence
    Wallet vs a fresh upload."""

    from_wallet: int
    fresh_uploads: int


# Resolves EvidenceChecklistOut.open_requests' forward reference to
# DocumentRequestOut, defined later in this same module.
EvidenceChecklistOut.model_rebuild()

# Resolves EvidenceItemDocumentOut.extracted_fields' forward reference to
# ExtractedFieldOut, defined later in this same module (Session 12).
EvidenceItemDocumentOut.model_rebuild()
