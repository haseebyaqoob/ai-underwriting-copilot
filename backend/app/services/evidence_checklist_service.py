"""
Evidence Checklist read model. Assembles the Evidence page's 6 category
sections (Identity / Business Financial Records / Digital Transactions /
Business Proof / Business Photos / Additional Evidence) and the Evidence
Strength summary card from the existing `Document`/`DocumentVersion`
rows -- no new extraction, no new tables beyond what's needed to store the
quality/cross-check fields themselves (see db/models/document.py).

Pure read/assembly, same shape as application_service.py's dashboard
assembly -- no writes happen here.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import DocumentAccessDeniedError, DocumentNotFoundError
from app.db.models.application import Application
from app.db.models.document import Document, DocumentVersion
from app.db.models.officer_review import DocumentRequest
from app.db.models.user import User
from app.services.evidence_catalog import (
    EVIDENCE_CATEGORIES,
    EVIDENCE_CATEGORY_ORDER,
    EVIDENCE_SUBTYPES,
)


def _latest_version(doc: Document) -> DocumentVersion | None:
    return doc.versions[-1] if doc.versions else None


def _item_status(subtype_key: str, docs: list[Document]) -> str:
    """Rolls a checklist item's (possibly several) documents up into one
    status. "Worst wins" for actionable states (a still-processing or
    still-needs-fixing document should not be hidden behind an already-
    verified sibling upload), "any verified" is enough for required
    single-slot items like CNIC front."""
    if not docs:
        return "missing"
    versions = [v for d in docs for v in [_latest_version(d)] if v is not None]
    if not versions:
        return "uploaded"
    statuses = {v.quality_status for v in versions}
    if "wrong_document" in statuses:
        return "wrong_document"
    if "needs_better_image" in statuses:
        return "needs_better_image"
    if "mismatch" in statuses:
        return "mismatch"
    if "processing" in statuses:
        return "processing"
    if statuses == {"verified"}:
        return "verified"
    return "uploaded"


@dataclass
class ExtractedFieldItem:
    field_name: str
    field_value: str
    value_type: str
    confidence: float
    source_page: int | None
    extraction_source: str


@dataclass
class ChecklistItemDoc:
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    original_filename: str
    size_bytes: int
    ocr_status: str
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
    processing_stage: str | None = None
    detected_document_type: str | None = None
    type_match: bool | None = None
    type_mismatch_reason: str | None = None
    applicant_confirmed_at: datetime | None = None
    extracted_fields: list[ExtractedFieldItem] = field(default_factory=list)


@dataclass
class ChecklistItem:
    subtype: str
    label: str
    required: bool
    tier: str  # "required" | "recommended" | "optional" -- see evidence_catalog.EvidenceTier
    allow_multiple: bool
    helper_text: str
    status: str
    documents: list[ChecklistItemDoc]
    # Section 11 (Document Request workflow): True when an officer has an
    # OPEN DocumentRequest matching this subtype (or its coarse
    # document_type, for a whole-application request that didn't name a
    # specific subtype) -- see _requested_map below.
    requested: bool = False
    request_note: str | None = None


@dataclass
class ChecklistCategory:
    key: str
    label: str
    items: list[ChecklistItem]
    completion_pct: int
    # Replaces a raw percentage in the UI (see redesign brief's "remove
    # percentage progress"): a short word ("Verified"/"Strong"/"Good"/
    # "Pending"/"Needs Documents") plus a one-line human detail
    # ("2 documents uploaded"). `completion_pct` is kept on the payload
    # for the progress-bar *fill width* only -- never rendered as a
    # number by the frontend.
    status_label: str
    status_detail: str


@dataclass
class EvidenceStrengthFactor:
    key: str
    label: str
    status: str  # "strong" | "partial" | "missing"
    detail: str


@dataclass
class EvidenceStrength:
    factors: list[EvidenceStrengthFactor]
    overall_completion_pct: int


@dataclass
class EvidenceChecklist:
    application_id: uuid.UUID
    categories: list[ChecklistCategory]
    overall_completion_pct: int
    strength: EvidenceStrength
    open_requests: list[DocumentRequest] = field(default_factory=list)


@dataclass
class ReadinessChecklistItem:
    key: str
    label: str
    met: bool
    detail: str


def _get_owned_application(db: Session, applicant: User, application_id: uuid.UUID) -> Application:
    application = db.get(
        Application,
        application_id,
        options=[
            selectinload(Application.documents)
            .selectinload(Document.versions)
            .selectinload(DocumentVersion.extracted_fields)
        ],
    )
    if application is None:
        raise DocumentNotFoundError()
    if application.applicant_id != applicant.id:
        raise DocumentAccessDeniedError()
    return application


def build_checklist(db: Session, *, applicant: User, application_id: uuid.UUID) -> EvidenceChecklist:
    application = _get_owned_application(db, applicant, application_id)
    return build_checklist_for_application(db, application)


def build_checklist_for_officer(db: Session, application: Application) -> EvidenceChecklist:
    """Officer review page's Evidence Summary (Section 10) -- same
    computation as the applicant's own Evidence page, just entered from
    an already org-scope-checked `Application` (see
    application_service.get_org_scoped_application) instead of an
    ownership check, since an officer is never the owning applicant."""
    return build_checklist_for_application(db, application)


def build_checklist_for_application(db: Session, application: Application) -> EvidenceChecklist:

    docs_by_subtype: dict[str, list[Document]] = {}
    for doc in application.documents:
        key = doc.subtype or "additional_evidence"
        docs_by_subtype.setdefault(key, []).append(doc)

    # Section 11 (Document Request workflow): an open request either
    # names an exact subtype (a per-document "Request Replacement"/
    # "Request Additional Evidence" action) or just a coarse
    # document_type (a whole-application request-docs decision) -- build
    # both lookup shapes once so every subtype's ChecklistItem can be
    # marked in O(1) below instead of re-querying per item.
    open_requests = db.scalars(
        select(DocumentRequest).where(
            DocumentRequest.application_id == application.id, DocumentRequest.status == "open"
        )
    ).all()
    requested_by_subtype: dict[str, str | None] = {r.subtype: r.note for r in open_requests if r.subtype}
    requested_by_type: dict = {r.document_type: r.note for r in open_requests if r.subtype is None}

    categories: list[ChecklistCategory] = []
    total_weight = 0
    satisfied_weight = 0.0

    for cat_key in EVIDENCE_CATEGORY_ORDER:
        subtypes = [s for s in EVIDENCE_SUBTYPES.values() if s.category == cat_key]
        items: list[ChecklistItem] = []
        cat_total = 0
        cat_satisfied = 0.0
        for s in subtypes:
            docs = docs_by_subtype.get(s.key, [])
            status = _item_status(s.key, docs)
            weight = 2 if s.required else 1
            total_weight += weight
            cat_total += weight
            if status == "verified":
                satisfied_weight += weight
                cat_satisfied += weight
            elif status in ("uploaded", "processing"):
                satisfied_weight += weight * 0.5
                cat_satisfied += weight * 0.5
            # needs_better_image / mismatch / missing contribute 0

            item_docs = []
            for d in sorted(docs, key=lambda d: d.versions[-1].created_at if d.versions else d.id.int):
                v = _latest_version(d)
                if v is None:
                    continue
                item_docs.append(
                    ChecklistItemDoc(
                        document_id=d.id,
                        document_version_id=v.id,
                        original_filename=d.original_filename,
                        size_bytes=v.size_bytes,
                        ocr_status=v.ocr_status.value,
                        processing_stage=v.processing_stage,
                        quality_status=v.quality_status,
                        quality_issues=list(v.quality_issues or []),
                        quality_guidance=v.quality_guidance,
                        confidence=float(v.confidence) if v.confidence is not None else None,
                        extracted_name=v.extracted_name,
                        extracted_id_number=v.extracted_id_number,
                        name_match=v.name_match,
                        id_number_match=v.id_number_match,
                        reused_from_wallet=d.reused_from_wallet,
                        created_at=v.created_at.isoformat(),
                        detected_document_type=v.detected_document_type,
                        type_match=v.type_match,
                        type_mismatch_reason=v.type_mismatch_reason,
                        applicant_confirmed_at=v.applicant_confirmed_at,
                        extracted_fields=[
                            ExtractedFieldItem(
                                field_name=ef.field_name,
                                field_value=ef.field_value,
                                value_type=ef.value_type,
                                confidence=float(ef.confidence),
                                source_page=ef.source_page,
                                extraction_source=ef.extraction_source,
                            )
                            for ef in v.extracted_fields
                        ],
                    )
                )

            requested = s.key in requested_by_subtype or s.document_type in requested_by_type
            request_note = requested_by_subtype.get(s.key) or requested_by_type.get(s.document_type)

            items.append(
                ChecklistItem(
                    subtype=s.key,
                    label=s.label,
                    required=s.required,
                    tier=s.tier,
                    allow_multiple=s.allow_multiple,
                    helper_text=s.helper_text,
                    status=status,
                    documents=item_docs,
                    requested=requested,
                    request_note=request_note,
                )
            )

        cat_completion = round((cat_satisfied / cat_total) * 100) if cat_total else 0
        status_label, status_detail = _category_status(items)
        categories.append(
            ChecklistCategory(
                key=cat_key,
                label=EVIDENCE_CATEGORIES[cat_key],
                items=items,
                completion_pct=cat_completion,
                status_label=status_label,
                status_detail=status_detail,
            )
        )

    overall_pct = round((satisfied_weight / total_weight) * 100) if total_weight else 0
    strength = _build_strength(categories, docs_by_subtype)

    return EvidenceChecklist(
        application_id=application.id,
        categories=categories,
        overall_completion_pct=overall_pct,
        strength=strength,
        open_requests=list(open_requests),
    )


def _category_status(items: list[ChecklistItem]) -> tuple[str, str]:
    """
    Turns a category's items into the short badge word + one-line detail
    shown on the Evidence page instead of a raw percentage (redesign
    brief: "Remove percentage progress... replace with meaningful
    progress indicators", with the explicit example badges "Verified /
    Strong / Good / Pending / Needs Documents"). Required items dominate
    the verdict (a category can't be "Verified" while a required slot is
    empty, no matter how many optional extras are attached); categories
    with no required items at all (e.g. Digital Transactions) are judged
    on how much verified evidence has piled up instead.
    """
    if not items:
        return "Incomplete", "Not applicable"

    required_items = [i for i in items if i.tier == "required"]
    uploaded_count = sum(1 for i in items if i.status != "missing")
    verified_count = sum(1 for i in items if i.status == "verified")
    needs_attention = any(i.status in ("needs_better_image", "mismatch", "wrong_document") for i in items)

    if required_items:
        required_missing = [i for i in required_items if i.status == "missing"]
        if required_missing:
            label = "Needs Documents"
        elif needs_attention:
            label = "Needs Documents"
        elif all(i.status == "verified" for i in required_items):
            label = "Verified"
        else:
            label = "Pending"
    else:
        if needs_attention:
            label = "Needs Documents"
        elif verified_count >= 2:
            label = "Strong"
        elif verified_count >= 1 or uploaded_count >= 2:
            label = "Good"
        elif uploaded_count >= 1:
            label = "Pending"
        else:
            label = "Needs Documents" if any(i.tier == "recommended" for i in items) else "Optional"

    if uploaded_count == 0:
        detail = "No documents yet"
    elif uploaded_count == 1:
        detail = "1 document uploaded"
    else:
        detail = f"{uploaded_count} documents uploaded"
    return label, detail


def _category_by_key(categories: list[ChecklistCategory], key: str) -> ChecklistCategory | None:
    return next((c for c in categories if c.key == key), None)


def _build_strength(categories: list[ChecklistCategory], docs_by_subtype: dict[str, list[Document]]) -> EvidenceStrength:
    """
    The "Evidence Strength" card: a short, plain-English rollup a business
    owner (or a demo audience) can read at a glance, independent of the
    detailed per-item checklist below it. Five factors, matching the
    product's requested layout (Identity / Business Activity / Financial
    Evidence / Address Evidence / Digital Transactions).
    """

    def factor_for(cat_key: str, label: str, strong_note: str, partial_note: str, missing_note: str) -> EvidenceStrengthFactor:
        cat = _category_by_key(categories, cat_key)
        pct = cat.completion_pct if cat else 0
        if pct >= 90:
            return EvidenceStrengthFactor(key=cat_key, label=label, status="strong", detail=strong_note)
        if pct > 0:
            return EvidenceStrengthFactor(key=cat_key, label=label, status="partial", detail=partial_note)
        return EvidenceStrengthFactor(key=cat_key, label=label, status="missing", detail=missing_note)

    identity = factor_for(
        "identity", "Identity", "Verified", "In progress", "Not started",
    )

    # "Business Activity" isn't a single checklist category -- it blends
    # business_photos (has a shop actually been shown) with business_proof
    # (utility/trade-license evidence the business exists at the claimed
    # address), matching the product's requested "Business Activity" line
    # without inventing a 7th checklist category the applicant would have
    # to separately fill out.
    photos_cat = _category_by_key(categories, "business_photos")
    proof_cat = _category_by_key(categories, "business_proof")
    activity_pct = round(((photos_cat.completion_pct if photos_cat else 0) + (proof_cat.completion_pct if proof_cat else 0)) / 2)
    if activity_pct >= 90:
        activity = EvidenceStrengthFactor("business_activity", "Business Activity", "strong", "Strong")
    elif activity_pct > 0:
        activity = EvidenceStrengthFactor("business_activity", "Business Activity", "partial", "Building up")
    else:
        activity = EvidenceStrengthFactor("business_activity", "Business Activity", "missing", "Not started")

    financial_cat = _category_by_key(categories, "business_financial")
    financial_doc_count = sum(len(v) for k, v in docs_by_subtype.items() if EVIDENCE_SUBTYPES.get(k, None) and EVIDENCE_SUBTYPES[k].category == "business_financial")
    if financial_cat and financial_cat.completion_pct >= 90:
        financial = EvidenceStrengthFactor("financial_evidence", "Financial Evidence", "strong", f"{financial_doc_count} document(s)")
    elif financial_doc_count > 0:
        financial = EvidenceStrengthFactor("financial_evidence", "Financial Evidence", "partial", f"{financial_doc_count} of 5 suggested documents")
    else:
        financial = EvidenceStrengthFactor("financial_evidence", "Financial Evidence", "missing", "No documents yet")

    address = factor_for(
        "business_proof", "Address Evidence", "Consistent", "In progress", "Not started",
    )

    digital = factor_for(
        "digital_transactions", "Digital Transactions", "Available", "In progress", "Not available",
    )

    factors = [identity, activity, financial, address, digital]
    overall = round(sum(1 if f.status == "strong" else 0.5 if f.status == "partial" else 0 for f in factors) / len(factors) * 100)
    return EvidenceStrength(factors=factors, overall_completion_pct=overall)


def build_readiness_checklist(
    checklist: EvidenceChecklist,
    *,
    independent_types_count: int,
    weeks_of_data: float,
) -> list[ReadinessChecklistItem]:
    """
    Application Review's "actionable guidance" checklist -- replaces the
    old raw sentence ("Only 0 independent document type(s) present...")
    with the same underlying evidence-floor facts
    (scoring.evidence_floor_check / MIN_INDEPENDENT_DOCUMENT_TYPES,
    MIN_OBSERVED_DAYS) rendered as a checklist an applicant can act on
    one line at a time. Deliberately reuses the checklist categories
    already built for the Evidence page rather than re-deriving evidence
    presence from `evidence_transactions` a second time, so the two
    pages can never disagree about what's been uploaded.
    """
    def cat_uploaded(key: str) -> bool:
        cat = _category_by_key(checklist.categories, key)
        return bool(cat) and any(i.status != "missing" for i in cat.items)

    has_financial = cat_uploaded("business_financial") or cat_uploaded("digital_transactions")
    has_activity_proof = cat_uploaded("business_photos") or cat_uploaded("business_proof")
    has_address = cat_uploaded("business_proof")
    days_of_data = weeks_of_data * 7

    return [
        ReadinessChecklistItem(
            key="financial_record",
            label="One financial record",
            met=has_financial,
            detail="Khata, ledger, invoices, or a bank/wallet statement",
        ),
        ReadinessChecklistItem(
            key="business_activity",
            label="One proof of business activity",
            met=has_activity_proof,
            detail="A shop photo, trade license, or utility bill",
        ),
        ReadinessChecklistItem(
            key="address_verification",
            label="One address verification",
            met=has_address,
            detail="Utility bill or rent agreement",
        ),
        ReadinessChecklistItem(
            key="independent_sources",
            label="At least two independent evidence sources",
            met=independent_types_count >= 2,
            detail=f"{independent_types_count} of 2 so far",
        ),
        ReadinessChecklistItem(
            key="date_span",
            label="Documents spanning at least 14 days",
            met=days_of_data >= 14,
            detail=f"{days_of_data:.0f} of 14 days covered",
        ),
    ]


def to_out(db: Session, checklist: EvidenceChecklist):
    """Shared serializer -- used by both /applicant/evidence/checklist
    and /officer/applications/{id}/evidence-checklist (Section 10's
    Evidence Summary) so the two endpoints can never drift out of sync
    on shape. Lazy imports here (not at module top) purely to keep this
    module's own import graph shallow -- schemas/document.py and
    officer_review_service don't need to be loaded for every caller of
    this module, only ones that serialize."""
    from app.schemas.document import (
        EvidenceCategoryOut,
        EvidenceChecklistItemOut,
        EvidenceChecklistOut,
        EvidenceItemDocumentOut,
        EvidenceStrengthFactorOut,
        EvidenceStrengthOut,
    )
    from app.services import officer_review_service

    return EvidenceChecklistOut(
        application_id=checklist.application_id,
        overall_completion_pct=checklist.overall_completion_pct,
        strength=EvidenceStrengthOut(
            overall_completion_pct=checklist.strength.overall_completion_pct,
            factors=[EvidenceStrengthFactorOut(**f.__dict__) for f in checklist.strength.factors],
        ),
        categories=[
            EvidenceCategoryOut(
                key=c.key,
                label=c.label,
                completion_pct=c.completion_pct,
                status_label=c.status_label,
                status_detail=c.status_detail,
                items=[
                    EvidenceChecklistItemOut(
                        subtype=i.subtype,
                        label=i.label,
                        required=i.required,
                        tier=i.tier,
                        allow_multiple=i.allow_multiple,
                        helper_text=i.helper_text,
                        status=i.status,
                        documents=[EvidenceItemDocumentOut(**d.__dict__) for d in i.documents],
                        requested=i.requested,
                        request_note=i.request_note,
                    )
                    for i in c.items
                ],
            )
            for c in checklist.categories
        ],
        open_requests=[officer_review_service.document_request_out(db, r) for r in checklist.open_requests],
    )
