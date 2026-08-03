import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Union

from pydantic import BaseModel, Field, ConfigDict, field_validator

from app.db.models.enums import ApplicationStatus, DecisionReasonCode, RiskLevel
from app.schemas.document import DocumentRequestOut, ReadinessChecklistItemOut, WalletUsageOut

_CNIC_DIGITS_RE = re.compile(r"^\d{13}$")


# --------------------------------------------------------------- requests
class ApplicationCreateIn(BaseModel):
    """
    Fields match the frontend's "New Application" wizard (business + loan
    steps, see applicant.applications.new.tsx). The evidence/review steps
    don't collect new fields of their own — evidence upload is Module 3.
    Creates the application in DRAFT (see app/services/state_machine.py);
    a separate explicit POST .../submit moves it to SUBMITTED.
    """

    business_name: str = Field(min_length=1, max_length=255)
    business_type: str = Field(min_length=1, max_length=120)
    owner_name: str = Field(min_length=1, max_length=255, description="Registered owner / CNIC name")
    city: str = Field(min_length=1, max_length=120)
    years_operating: int = Field(ge=0, le=100)
    employee_count: int = Field(ge=0, le=100_000)
    amount_pkr: Decimal = Field(gt=0, description="Requested amount")
    tenor_months: int = Field(ge=1, le=120)
    purpose: str = Field(min_length=1, max_length=255)
    preferred_repayment: str = Field(min_length=1, max_length=120)
    # --- Business page polish (this session): registration status is
    # required-with-a-default at the form level (radio, always answered)
    # but never blocks submission either way -- the brief is explicit
    # this product supports unregistered businesses. NTN/STRN stay
    # optional regardless of which status is picked (see
    # db/models/application.py's docstring for why).
    registration_status: Literal["registered", "unregistered"] = "unregistered"
    ntn: str | None = Field(default=None, max_length=20)
    strn: str | None = Field(default=None, max_length=20)
    # --- Loan page polish: applicant's own optional estimate, compared
    # against (never substituted for) the AI-computed
    # RevenueEstimateOut -- see revenue_estimator.py.
    monthly_estimated_revenue_pkr: Decimal | None = Field(default=None, ge=0)
    monthly_estimated_expenses_pkr: Decimal | None = Field(default=None, ge=0)
    # Optional at the schema level (nullable column, and the wizard may
    # create the application before the applicant reaches the CNIC field)
    # but validated strictly when present: accepts "42101-1234567-1" or
    # "4210112345671" and normalizes to 13 raw digits for storage. Never
    # echoed back unmasked to anyone but the owning applicant -- see
    # application_service._mask_cnic.
    cnic_number: str | None = Field(default=None, description="13-digit CNIC, with or without dashes")

    @field_validator("cnic_number")
    @classmethod
    def _normalize_cnic(cls, v: str | None) -> str | None:
        if v is None or v.strip() == "":
            return None
        digits = v.replace("-", "").replace(" ", "")
        if not _CNIC_DIGITS_RE.match(digits):
            raise ValueError("CNIC must be 13 digits (e.g. 42101-1234567-1)")
        return digits


class DecisionIn(BaseModel):
    """Body for approve/reject/request-docs. `reason_code` is required
    (structured, per architecture spec); `note` is optional free text.
    `missing_document_types` is only meaningful for request-docs and is
    pre-populated by the frontend from the assessment's own
    `missing_document_types` (see AssessmentOut) -- the backend doesn't
    trust the client's list blindly for anything except display/copy in
    the applicant-facing "needs docs" notice, so a wrong/missing value
    here doesn't affect scoring or evidence-floor logic."""

    reason_code: DecisionReasonCode
    note: str | None = Field(default=None, max_length=2000)
    missing_document_types: list[str] | None = None


class ReopenIn(BaseModel):
    reason_code: DecisionReasonCode
    note: str | None = Field(default=None, max_length=2000)


# ------------------------------------------------------------- sub-shapes
class TimelineEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    at: datetime
    label: str
    actor_type: str
    actor_name: str


class EvidenceCoverageOut(BaseModel):
    """
    Real, computed from `evidence_transactions` (grouped by source_type) --
    replaces Module 2's fabricated `EvidenceItemOut` list entirely. One
    row per document type that has at least one normalized transaction
    row, so an applicant who's only uploaded a utility bill sees exactly
    one row here, not six fabricated ones.
    """

    source_type: str
    transaction_count: int
    date_range_start: date | None
    date_range_end: date | None
    avg_confidence: float


class RevenueEstimateOut(BaseModel):
    """Real, computed by app/services/revenue_estimator.py from
    `evidence_transactions`. `None` fields mean there isn't enough dated
    inflow evidence yet to compute them -- never backfilled with a
    fabricated number. Deliberately a band (low/high), not one blended
    number, per the architecture spec."""

    verified_floor_monthly_pkr: str | None
    blended_estimate_low_monthly_pkr: str | None
    blended_estimate_high_monthly_pkr: str | None
    window_start: date | None
    window_end: date | None
    weeks_of_data: float
    months_of_data: float
    source_types_used: list[str]
    plausibility_flag: bool
    plausibility_note: str | None


class ScoreFactorOut(BaseModel):
    key: str
    label: str
    weight_pct: int
    factor_score: float
    explanation: str


class DebtExposureOut(BaseModel):
    status: str
    note: str


class InsufficientEvidenceOut(BaseModel):
    """Rendered instead of a score when the evidence floor isn't met --
    a real, first-class UI state (architecture spec: "This is a real UI
    state, not just a backend null"), never a degraded/low score."""

    status: Literal["insufficient_evidence"] = "insufficient_evidence"
    reasons: list[str]
    missing_document_types: list[str]
    document_types_present: list[str]
    weeks_of_data: float
    # Application Review redesign: the same facts as `reasons`, rendered
    # as an actionable checklist instead of prose paragraphs -- see
    # evidence_checklist_service.build_readiness_checklist. `reasons` is
    # kept for backward compatibility with any existing caller.
    readiness_checklist: list[ReadinessChecklistItemOut] = []


class ScoredAssessmentOut(BaseModel):
    status: Literal["scored"] = "scored"
    score: int
    confidence: float
    risk_level: RiskLevel
    factors: list[ScoreFactorOut]
    debt_exposure: DebtExposureOut
    weeks_of_data: float


AssessmentOut = Union[ScoredAssessmentOut, InsufficientEvidenceOut]


class ConsistencyCheckOut(BaseModel):
    """`message` is pre-selected server-side to match the viewer: officer/
    admin get the specific officer_message, the applicant always gets the
    generic applicant_message when a check fails (never the specific
    reason) — see app/services/consistency_checks.py's module docstring
    for why this split exists and must never be bypassed."""

    check_id: str
    passed: bool
    message: str


class ProcessingStepOut(BaseModel):
    """Mirrors workflow_stage_service.ProcessingStep field-for-field."""

    key: str
    label: str
    status: str  # "pending" | "in_progress" | "complete"
    detail: str


# ------------------------------------------------------------------ output
class ApplicationListItemOut(BaseModel):
    id: uuid.UUID
    display_id: str
    business_name: str
    city: str
    amount_pkr: Decimal
    purpose: str
    status: ApplicationStatus
    # Presentation-layer refinement of `status` -- see
    # app/services/workflow_stage_service.py's module docstring. Computed
    # fresh on every read, not stored.
    workflow_stage: str
    workflow_stage_label: str
    score: int | None = None
    confidence: float | None = None
    risk_level: RiskLevel | None = None
    documents_count: int = 0
    officer_name: str | None = None
    applicant_name: str
    created_at: datetime
    updated_at: datetime


class ApplicationDetailOut(ApplicationListItemOut):
    business_type: str | None = None
    owner_name: str | None = None
    years_operating: int | None = None
    employee_count: int | None = None
    tenor_months: int | None = None
    preferred_repayment: str | None = None
    registration_status: str = "unregistered"
    ntn: str | None = None
    strn: str | None = None
    monthly_estimated_revenue_pkr: Decimal | None = None
    monthly_estimated_expenses_pkr: Decimal | None = None
    # Masked (e.g. "42101-XXXXXXX-1") for every viewer except the owning
    # applicant looking at their own application -- application_service
    # decides which string lands here per-request, never the schema/route
    # layer, so masking can't accidentally be bypassed by a future
    # response-model change. None if the applicant hasn't supplied one yet.
    cnic_number: str | None = None

    evidence: list[EvidenceCoverageOut] = []
    timeline: list[TimelineEntryOut] = []
    revenue: RevenueEstimateOut | None = None
    assessment: AssessmentOut | None = None
    consistency_checks: list[ConsistencyCheckOut] = []
    # AI Processing page -- see workflow_stage_service.build_processing_steps.
    # Applicant-view only (officer/admin detail views don't need this).
    processing_steps: list[ProcessingStepOut] = []
    evidence_completion_pct: int = 0


class OfficerApplicationDetailOut(ApplicationDetailOut):
    """Completes Section 10 of the original brief -- the officer review
    page's full payload. A superset of `ApplicationDetailOut` (every
    applicant-visible field is still here, unmasked business fields plus
    the masked CNIC, same as before), plus the officer-only additions:
    Wallet Usage and the application's open Document Requests. The full
    per-document review sub-view (preview, versions, extracted fields,
    officer notes, review actions) is deliberately its own endpoint
    (`GET /officer/applications/{id}/documents`) rather than embedded
    here, so this payload stays a reasonable size for the queue's
    quick-open case."""

    wallet_usage: WalletUsageOut
    open_document_requests: list[DocumentRequestOut] = []


class PaginatedApplicationsOut(BaseModel):
    items: list[ApplicationListItemOut]
    total: int
    page: int
    page_size: int


class EvidenceSummaryLineOut(BaseModel):
    """One line of the dashboard's "Evidence Status" card (redesign
    brief: replace "Evidence Completion 2%" with friendly lines like
    "Identity Verified" / "Business Evidence Needed"). `status` is the
    same badge vocabulary as EvidenceCategoryOut.status_label so the
    dashboard and Evidence page never disagree."""

    key: str
    label: str
    status: str


class ApplicantDashboardOut(BaseModel):
    active_application_count: int
    total_application_count: int
    recent_applications: list[ApplicationListItemOut]
    activity_timeline: list[TimelineEntryOut]
    # Dashboard workflow redesign (this session): all computed for the
    # single most-recently-updated ACTIVE application (submitted or
    # later, not draft/withdrawn/terminal) -- the brief's mockup shows
    # one "Evidence Completion 78%" figure, which only makes sense
    # pinned to one application, not averaged across several. `None`
    # when there is no active application (nothing to show progress on).
    primary_application_id: uuid.UUID | None = None
    evidence_completion_pct: int | None = None
    missing_required_evidence: list[str] = []
    # Friendly replacement for the raw `evidence_completion_pct` number
    # on the dashboard card itself -- see EvidenceSummaryLineOut.
    # `evidence_completion_pct`/`missing_required_evidence` above are
    # kept for backward compatibility with any existing caller.
    evidence_summary: list[EvidenceSummaryLineOut] = []
    # Dashboard redesign (this session): "what do I do next?" as a single,
    # computed instruction rather than making the applicant infer it from
    # `missing_required_evidence`'s full list. The FIRST still-missing
    # required checklist item, in the same fixed category/item order the
    # Evidence Checklist itself renders in -- so this always agrees with
    # whichever item the Evidence Wizard would auto-land the applicant on
    # (see frontend EvidenceWizard's `initialStep` logic, same "first
    # incomplete required thing" rule, computed independently here so the
    # dashboard doesn't need to fetch the whole wizard to show one line).
    # `None` when nothing required is missing (fully ready to submit, or
    # no active application at all).
    next_step_label: str | None = None
    next_step_wallet_available: bool = False
    wallet_reusable_count: int = 0
    # Subset of activity_timeline filtered to actor_type == "ai" -- the
    # brief's "Display latest AI activity" requirement, kept as its own
    # field rather than making the caller filter activity_timeline
    # client-side.
    ai_activity: list[TimelineEntryOut] = []


class OfficerDashboardOut(BaseModel):
    queue_count: int
    approvals_last_30d: int
    rejections_last_30d: int
    avg_time_to_decision_minutes: float | None
    status_breakdown: dict[str, int]


class AdminDashboardOut(BaseModel):
    total_applications: int
    submitted_last_30d: int
    approval_rate: float | None
    status_breakdown: dict[str, int]
    total_volume_pkr: Decimal

