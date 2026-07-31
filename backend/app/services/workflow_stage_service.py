"""
Derives two related, REAL-signal-driven views from the same underlying
data (the Evidence Checklist + the computed revenue/assessment/
consistency-check results, all already real per Session 7/8):

1. `build_processing_steps` -- the step-by-step list the AI Processing
   page shows right after submission ("Reading Identity Documents --
   Complete", etc). The product brief explicitly allows this to be
   "simulated progress" as long as "architecture should support real
   progress later" -- this session goes further and makes it REAL now:
   each step's status is read off actual `DocumentVersion.ocr_status`/
   `quality_status` values and whether `revenue_estimator`/`scoring`/
   `consistency_checks` have actually produced a result, not a
   time-based fake sequence. The tradeoff, stated plainly: because it's
   real, a step can sit on "in_progress" for as long as the underlying
   Celery task takes (this session's own tasks.py has `max_retries=0`
   and no timeout handling -- see Session 7's own flagged gap), rather
   than always resolving in a fixed number of seconds. No countdown
   timer is faked to paper over that.

2. `derive_stage` -- the coarser workflow-stage label used on the
   Applicant Dashboard (Documents Processing / Evidence Verified / AI
   Underwriting / Officer Review / Additional Evidence Requested /
   Approved / Rejected / ...). Deliberately NOT a new
   `ApplicationStatus` enum value or DB column -- see this module's own
   docstring note below on why "Decision Ready" from the brief isn't
   modeled -- this is a presentation-layer refinement computed fresh on
   every read from the EXISTING 7-value `ApplicationStatus` plus the
   same checklist/assessment signals as `build_processing_steps`.
   Preserves the state machine (app/services/state_machine.py)
   untouched, per the "preserve existing architecture" instruction.

Both functions are pure -- no DB access, no writes -- callers
(application_service.py) pass in data they've already computed for
other reasons (the checklist, the revenue/assessment/consistency
results), so this costs zero extra queries.
"""
from dataclasses import dataclass

from app.db.models.enums import ApplicationStatus
from app.schemas.application import ConsistencyCheckOut, RevenueEstimateOut
from app.services.evidence_checklist_service import ChecklistCategory, ChecklistItemDoc, EvidenceChecklist

_ACTIVE_OCR_STATUSES = {"pending", "processing", "awaiting_vision"}


@dataclass
class ProcessingStep:
    key: str
    label: str
    status: str  # "pending" | "in_progress" | "complete"
    detail: str


@dataclass
class WorkflowStage:
    key: str
    label: str


def _all_docs(checklist: EvidenceChecklist) -> list[ChecklistItemDoc]:
    return [d for c in checklist.categories for i in c.items for d in i.documents]


def _category(checklist: EvidenceChecklist, key: str) -> ChecklistCategory | None:
    return next((c for c in checklist.categories if c.key == key), None)


def _category_status(cat: ChecklistCategory | None) -> str:
    if cat is None:
        return "pending"
    docs = [d for i in cat.items for d in i.documents]
    if not docs:
        return "pending"
    if any(d.ocr_status in _ACTIVE_OCR_STATUSES or d.quality_status == "processing" for d in docs):
        return "in_progress"
    return "complete"


def build_processing_steps(
    *,
    checklist: EvidenceChecklist,
    revenue: RevenueEstimateOut | None,
    assessment_computed: bool,
    consistency_checks: list[ConsistencyCheckOut],
    application_status: ApplicationStatus,
) -> list[ProcessingStep]:
    identity = _category_status(_category(checklist, "identity"))
    business_financial = _category_status(_category(checklist, "business_financial"))
    business_proof = _category_status(_category(checklist, "business_proof"))
    digital = _category_status(_category(checklist, "digital_transactions"))

    all_docs = _all_docs(checklist)
    any_active = any(d.ocr_status in _ACTIVE_OCR_STATUSES or d.quality_status == "processing" for d in all_docs)
    comparing_status = "pending" if not all_docs else ("in_progress" if any_active else "complete")

    revenue_ready = revenue is not None and (
        revenue.verified_floor_monthly_pkr is not None or revenue.blended_estimate_low_monthly_pkr is not None
    )
    revenue_status = (
        "complete"
        if revenue_ready
        else "pending" if business_financial == "pending" and digital == "pending" else "in_progress"
    )

    address_status = (
        "complete"
        if len(consistency_checks) > 0
        else "pending" if business_proof == "pending" and identity == "pending" else "in_progress"
    )

    underwriting_status = "complete" if assessment_computed else ("in_progress" if comparing_status == "complete" else "pending")

    officer_package_status = (
        "pending"
        if application_status == ApplicationStatus.draft
        else "complete" if underwriting_status == "complete" else "in_progress"
    )

    def detail_for(status: str, doc_count: int, noun: str) -> str:
        if status == "complete":
            return f"{doc_count} document(s) processed" if doc_count else "No documents needed for this step"
        if status == "in_progress":
            return f"Reading {noun}…"
        return "Waiting for documents"

    id_count = len(_all_docs_in(checklist, "identity"))
    fin_count = len(_all_docs_in(checklist, "business_financial"))
    proof_count = len(_all_docs_in(checklist, "business_proof"))
    digital_count = len(_all_docs_in(checklist, "digital_transactions"))

    return [
        ProcessingStep("reading_identity", "Reading Identity Documents", identity, detail_for(identity, id_count, "your CNIC")),
        ProcessingStep("reading_business_records", "Reading Business Records", business_financial, detail_for(business_financial, fin_count, "your khata/ledger")),
        ProcessingStep("reading_utility_bills", "Reading Utility & Business Proof", business_proof, detail_for(business_proof, proof_count, "your utility bills")),
        ProcessingStep("reading_digital_transactions", "Reading Digital Transactions", digital, detail_for(digital, digital_count, "your wallet/bank statements")),
        ProcessingStep("extracting_revenue", "Extracting Revenue", revenue_status, "Estimating monthly revenue from dated evidence" if revenue_status == "in_progress" else ("Revenue estimate ready" if revenue_status == "complete" else "Waiting for financial evidence")),
        ProcessingStep("checking_address_consistency", "Checking Address Consistency", address_status, "Comparing addresses across documents" if address_status == "in_progress" else ("Consistency checks complete" if address_status == "complete" else "Waiting for address evidence")),
        ProcessingStep("comparing_documents", "Comparing Documents", comparing_status, "Cross-referencing all uploaded evidence" if comparing_status == "in_progress" else ("All documents compared" if comparing_status == "complete" else "Waiting for documents")),
        ProcessingStep("generating_underwriting_summary", "Generating Underwriting Summary", underwriting_status, "Computing the Yaqeen assessment" if underwriting_status == "in_progress" else ("Underwriting summary ready" if underwriting_status == "complete" else "Waiting on document comparison")),
        ProcessingStep("preparing_officer_package", "Preparing Officer Package", officer_package_status, "Assembling the package for loan officer review" if officer_package_status == "in_progress" else ("Ready for officer review" if officer_package_status == "complete" else "Not submitted yet")),
    ]


def _all_docs_in(checklist: EvidenceChecklist, category_key: str) -> list[ChecklistItemDoc]:
    cat = _category(checklist, category_key)
    if cat is None:
        return []
    return [d for i in cat.items for d in i.documents]


# Deviation from the brief, flagged: the brief's dashboard example list
# includes "Decision Ready" as a stage between officer review and
# Approved/Rejected. This architecture has no real signal for that
# state -- `decide_application` (application_service.py) moves
# IN_REVIEW straight to APPROVED/REJECTED in one atomic call, so there
# is no persisted "officer has decided but the record isn't saved yet"
# moment to read a stage off of. Inventing one would mean either a fake
# UI-only delay (contradicts "real progress" above) or a new DB status
# (contradicts "preserve existing state machine"). Left out; if a future
# session wants it, `decide_application` would need a two-phase write
# (e.g. AuditLog with the decision pre-committed, application status
# updated in a slightly-later step) to give it a genuine signal.
_STAGE_LABELS: dict[str, str] = {
    "draft": "Draft",
    "documents_processing": "Documents Processing",
    "evidence_verified": "Evidence Verified",
    "ai_underwriting": "AI Underwriting",
    "officer_review": "Officer Review",
    "additional_evidence_requested": "Additional Evidence Requested",
    "approved": "Approved",
    "rejected": "Rejected",
    "withdrawn": "Withdrawn",
}


def derive_stage(
    *,
    application_status: ApplicationStatus,
    checklist: EvidenceChecklist,
    assessment_computed: bool,
) -> WorkflowStage:
    if application_status == ApplicationStatus.draft:
        key = "draft"
    elif application_status == ApplicationStatus.withdrawn:
        key = "withdrawn"
    elif application_status == ApplicationStatus.approved:
        key = "approved"
    elif application_status == ApplicationStatus.rejected:
        key = "rejected"
    elif application_status == ApplicationStatus.needs_docs:
        key = "additional_evidence_requested"
    elif application_status == ApplicationStatus.in_review:
        key = "officer_review"
    else:
        # SUBMITTED: subdivide using the same real signals as
        # build_processing_steps, cheaply re-derived here rather than
        # threading the full step list through (callers that need both
        # call build_processing_steps separately -- see
        # application_service._to_detail).
        all_docs = _all_docs(checklist)
        any_active = any(d.ocr_status in _ACTIVE_OCR_STATUSES or d.quality_status == "processing" for d in all_docs)
        if any_active:
            key = "documents_processing"
        else:
            required_unsatisfied = any(
                item.required and item.status != "verified"
                for cat in checklist.categories
                for item in cat.items
            )
            if required_unsatisfied:
                key = "documents_processing"
            elif not assessment_computed:
                key = "evidence_verified"
            else:
                key = "ai_underwriting"

    return WorkflowStage(key=key, label=_STAGE_LABELS[key])
