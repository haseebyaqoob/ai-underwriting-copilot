"""
Enums shared across models. Kept as plain Python str-Enums (rendered as
Postgres native ENUM types via SQLAlchemy) rather than free-text columns,
so an invalid status can't be written by a typo in application code.
"""
import enum


class Role(str, enum.Enum):
    applicant = "applicant"
    loan_officer = "loan_officer"
    admin = "admin"


class UserStatus(str, enum.Enum):
    active = "active"
    invited = "invited"
    disabled = "disabled"


class OrgType(str, enum.Enum):
    applicant_business = "applicant_business"
    lender = "lender"


class ApplicationStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    in_review = "in_review"
    needs_docs = "needs_docs"
    approved = "approved"
    rejected = "rejected"
    # Added this session (state-machine formalization): an applicant can
    # withdraw from DRAFT/SUBMITTED/NEEDS_DOCS. Terminal, like
    # approved/rejected, but distinct so the UI/reporting can tell "the
    # applicant walked away" apart from "the bank said no". See
    # app/services/state_machine.py for the full transition table.
    withdrawn = "withdrawn"


class TransactionDirection(str, enum.Enum):
    """
    Used on `evidence_transactions.direction`. `inflow`/`outflow` are real
    money-movement transactions (wallet-statement lines, khata cash-sale
    entries) that feed the revenue estimator's verified-floor/blended
    calculations. `scale_proxy` is NOT a cash-flow transaction at all --
    it's a business-scale signal (a utility bill's amount_payable, an
    invoice's implied volume) used only for the plausibility-band sanity
    check, never summed into the revenue estimate itself.
    """

    inflow = "inflow"
    outflow = "outflow"
    scale_proxy = "scale_proxy"


class DecisionReasonCode(str, enum.Enum):
    """
    Structured reason codes for officer decisions (approve/reject/
    request-more-docs), per the architecture spec's "reason-code enum +
    optional free text" requirement. One shared enum rather than three
    separate ones -- simpler for the audit log and for the admin config
    screen (Module 8) that will eventually let these be relabeled.
    """

    strong_cashflow_evidence = "strong_cashflow_evidence"
    adequate_evidence_coverage = "adequate_evidence_coverage"
    acceptable_debt_service_ratio = "acceptable_debt_service_ratio"
    insufficient_evidence = "insufficient_evidence"
    high_risk_inconsistency = "high_risk_inconsistency"
    debt_service_coverage_low = "debt_service_coverage_low"
    income_instability = "income_instability"
    missing_wallet_statement = "missing_wallet_statement"
    missing_khata = "missing_khata"
    missing_utility_bill = "missing_utility_bill"
    missing_cnic = "missing_cnic"
    unclear_document_quality = "unclear_document_quality"
    other = "other"


class DocumentType(str, enum.Enum):
    khata = "khata"
    utility_bills = "utility_bills"
    wallet_statements = "wallet_statements"
    tax_filing = "tax_filing"
    invoice = "invoice"
    other = "other"
    # Added this session (CNIC capture feature): a photo of the applicant's
    # CNIC card. Deliberately not added to router.py's
    # `_DETERMINISTIC_PARSERS` map -- there's no fuzzy-match field layout
    # for a CNIC card, so it falls through to the same LLM-vision path
    # `khata` uses, automatically, via the existing "no parser registered"
    # branch.
    cnic = "cnic"


class OcrStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    # Module 4 addition: a document has been through the deterministic
    # pipeline (or was khata, which never goes through it) and is now
    # waiting on Module 5's LLM vision path. Kept as a distinct, visible
    # status per the Module 4 spec ("khata... should sit in a
    # clearly-flagged 'awaiting vision extraction' state") rather than
    # silently reusing `processing`, even though in this session the LLM
    # step usually runs immediately after within the same Celery task —
    # if Module 5's provider is ever slow/rate-limited/down, this status
    # is what makes that visible instead of looking stuck on "processing".
    awaiting_vision = "awaiting_vision"
    done = "done"
    failed = "failed"


class EvidenceStatus(str, enum.Enum):
    validated = "validated"
    review = "review"


class RiskLevel(str, enum.Enum):
    low = "low"
    moderate = "moderate"
    elevated = "elevated"


class ActorType(str, enum.Enum):
    applicant = "applicant"
    ai = "ai"
    officer = "officer"
    system = "system"


class NotificationType(str, enum.Enum):
    info = "info"
    action_required = "action_required"
    decision = "decision"


class NotificationEventType(str, enum.Enum):
    """
    Specific notification kinds from the brief. Kept separate from
    `NotificationType` (which stays a small "how should this render"
    severity enum: info/action_required/decision) so the UI can keep
    using `type` for badge color/icon while `event_type` carries the
    precise, filterable, analytics-friendly meaning ("what happened").
    A plain string column (see the migration), not a native Postgres
    ENUM -- this list is product copy and likely to grow, and a native
    ENUM would need a hand-written `ALTER TYPE ... ADD VALUE` migration
    per new value (same reasoning as `EvidenceQualityStatus` above).
    """

    # Applicant-facing
    application_submitted = "application_submitted"
    document_uploaded = "document_uploaded"
    document_verified = "document_verified"
    additional_evidence_requested = "additional_evidence_requested"
    ai_assessment_started = "ai_assessment_started"
    ai_assessment_completed = "ai_assessment_completed"
    application_approved = "application_approved"
    application_rejected = "application_rejected"
    officer_comment = "officer_comment"
    status_changed = "status_changed"

    # Loan-officer-facing
    new_application_submitted = "new_application_submitted"
    applicant_uploaded_new_evidence = "applicant_uploaded_new_evidence"
    applicant_updated_existing_evidence = "applicant_updated_existing_evidence"
    applicant_replied_to_request = "applicant_replied_to_request"
    application_withdrawn = "application_withdrawn"


class EvidenceQualityStatus(str, enum.Enum):
    """
    Per-`DocumentVersion` quality/verification state shown on the Evidence
    Checklist and Evidence Wallet. Deliberately a plain `String` column in
    the DB (see the evidence-checklist migration), not a Postgres native
    ENUM like `DocumentType`/`OcrStatus` -- this status is UI-facing and
    likely to grow new values (e.g. a future "expired" for an out-of-date
    CNIC) faster than the extraction-pipeline enums above, and a native
    Postgres ENUM requires a hand-written `ALTER TYPE ... ADD VALUE`
    migration per new value (see b7e1c4a92f10_cnic_capture.py's downgrade
    note) -- friction we don't want on a status that's still evolving.

    This is intentionally a DIFFERENT axis from `OcrStatus`: `OcrStatus`
    tracks the extraction pipeline's own progress (pending/processing/
    done/failed); `EvidenceQualityStatus` tracks whether the *image itself*
    is good enough and, for identity documents, whether what was read
    cross-checks against the application -- a document can be
    `OcrStatus.done` and still be `needs_better_image` (extraction
    succeeded technically but the AI quality pass flagged glare/blur/a
    cropped edge, or a name mismatch).
    """

    missing = "missing"  # no document uploaded yet for this checklist slot
    uploaded = "uploaded"  # file received, not yet processed
    processing = "processing"  # queued/running through OCR + quality assessment
    verified = "verified"  # quality assessment passed (and, for identity docs, cross-check matched)
    needs_better_image = "needs_better_image"  # quality assessment flagged an actionable IMAGE problem (blur/glare/crop/low-res)
    # Added after a real bug report: identity documents (CNIC front/back)
    # whose OCR'd name/CNIC number doesn't match the application's own
    # fields used to be lumped into `needs_better_image`, which told the
    # applicant to "retake the photo" -- useless advice when the photo
    # itself is perfectly clear and the real problem is a typo on the
    # Business page (or the wrong person's CNIC). Kept as its own value
    # so the UI can give accurate, actionable guidance for each case.
    mismatch = "mismatch"  # image quality is fine; extracted identity fields don't match the application
