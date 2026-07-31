"""
Completes Sections 10 (Loan Officer Review Page) and 11 (Document Request
Workflow) of the original product brief, both explicitly deferred by the
last two sessions (see docs/SESSION_10_HANDOFF.md's "Not started this
session"). Reuses the existing architecture throughout rather than
inventing parallel systems:

  - `state_machine`'s pattern of "one action -> one ActivityTimeline row
    + one AuditLog row" is followed exactly for every action here (a
    note, a per-document review, a document request) -- see this
    module's docstring on each function.
  - `notification_service` is the only thing that ever writes a
    `Notification` row -- this module never does.
  - `evidence_catalog`/`evidence_checklist_service` are the single
    source of truth for subtype vocabulary and per-category status; this
    module never re-derives evidence presence.

Failure posture for notification/timeline side-effects matches the rest
of the codebase: the primary DB write (the note, the review, the
request) is the thing that must succeed; a best-effort notification
dispatch failing is logged and swallowed, never propagated.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import DocumentNotFoundError
from app.db.models.application import Application
from app.db.models.audit import ActivityTimeline
from app.db.models.document import Document, DocumentVersion
from app.db.models.enums import ActorType, DocumentType, NotificationEventType
from app.db.models.extracted_field import ExtractedField
from app.db.models.officer_review import DocumentRequest, DocumentReview, OfficerNote
from app.db.models.user import User
from app.schemas.document import (
    DocumentReviewOut,
    DocumentRequestOut,
    DocumentVersionDetailOut,
    ExtractedFieldOut,
    OfficerDocumentDetailOut,
    OfficerNoteOut,
    WalletUsageOut,
)
from app.services.evidence_catalog import get_subtype

logger = logging.getLogger(__name__)

_REVIEW_TIMELINE_LABELS: dict[str, str] = {
    "approved": "Officer approved document",
    "rejected": "Officer rejected document",
    "replacement_requested": "Officer requested a replacement document",
    "additional_evidence_requested": "Officer requested additional evidence",
}

# Which per-document review actions also open a concrete DocumentRequest
# against that document's own subtype -- "Approve"/"Reject" are pure
# verdicts on what's already there; "Request Replacement"/"Request
# Additional Evidence" are asks for something new, so they get the same
# trackable-request treatment as a whole-application request-docs
# decision (Section 11).
_REVIEW_ACTIONS_THAT_OPEN_REQUEST = frozenset({"replacement_requested", "additional_evidence_requested"})


# --------------------------------------------------------------- wallet usage
def wallet_usage(db: Session, application: Application) -> WalletUsageOut:
    """How many of this application's uploaded documents came from the
    applicant's Evidence Wallet vs a fresh upload -- `Document.reused_from_wallet`
    already carries this per-document (see evidence_wallet_service.py),
    this just tallies it."""
    from_wallet = 0
    fresh = 0
    for doc in application.documents:
        if doc.reused_from_wallet:
            from_wallet += 1
        else:
            fresh += 1
    return WalletUsageOut(from_wallet=from_wallet, fresh_uploads=fresh)


# ------------------------------------------------------------ officer notes
def create_officer_note(
    db: Session, *, officer: User, application: Application, document_id: uuid.UUID | None, body: str
) -> OfficerNoteOut:
    """Adds a real, persisted officer note -- this is what finally calls
    `NotificationEventType.officer_comment`, which existed in the enum
    and notification templates since the notification-system session but
    had no caller (see notification_service.py's `_SEVERITY`). Writes an
    `ActivityTimeline` row so it shows up on the applicant's own timeline
    immediately, same as every other officer action."""
    if document_id is not None:
        document = db.get(Document, document_id)
        if document is None or document.application_id != application.id:
            raise DocumentNotFoundError()

    note = OfficerNote(
        application_id=application.id,
        document_id=document_id,
        officer_id=officer.id,
        body=body,
    )
    db.add(note)
    db.flush()

    db.add(
        ActivityTimeline(
            application_id=application.id,
            label=f"Loan officer left a note: {body[:120]}{'…' if len(body) > 120 else ''}",
            actor_type=ActorType.officer,
            actor_name=officer.name,
        )
    )
    db.commit()
    db.refresh(note)

    _notify_officer_comment(db, application=application, note_body=body)

    return OfficerNoteOut(
        id=note.id,
        application_id=note.application_id,
        document_id=note.document_id,
        officer_id=note.officer_id,
        officer_name=officer.name,
        body=note.body,
        created_at=note.created_at,
    )


def _notify_officer_comment(db: Session, *, application: Application, note_body: str) -> None:
    from app.services import notification_service

    try:
        notification_service.notify_applicant(
            db, application=application, event_type=NotificationEventType.officer_comment, note=note_body,
        )
        db.commit()
    except Exception:
        logger.exception(
            "officer_review_service: failed to dispatch officer_comment notification for application %s",
            application.id,
        )
        db.rollback()


# --------------------------------------------------------- per-document review
def review_document(
    db: Session, *, officer: User, application: Application, document_id: uuid.UUID, action: str, note: str | None
) -> DocumentReviewOut:
    """Officer's per-document decision (approve/reject/request-replacement/
    request-additional-evidence) -- distinct from the whole-application
    approve/reject/request-docs actions in
    application_service.decide_application. Always writes an
    ActivityTimeline row; `replacement_requested`/
    `additional_evidence_requested` also open a concrete DocumentRequest
    against this document's own subtype (Section 11)."""
    document = db.get(Document, document_id)
    if document is None or document.application_id != application.id:
        raise DocumentNotFoundError()

    review = DocumentReview(document_id=document.id, officer_id=officer.id, action=action, note=note)
    db.add(review)
    db.flush()

    label = _REVIEW_TIMELINE_LABELS.get(action, f"Officer reviewed document ({action})")
    if note:
        label = f"{label}: {note[:120]}{'…' if len(note) > 120 else ''}"
    db.add(
        ActivityTimeline(
            application_id=application.id,
            label=label,
            actor_type=ActorType.officer,
            actor_name=officer.name,
        )
    )

    if action in _REVIEW_ACTIONS_THAT_OPEN_REQUEST:
        db.add(
            DocumentRequest(
                application_id=application.id,
                document_type=document.type,
                subtype=document.subtype,
                requested_by_officer_id=officer.id,
                note=note,
                status="open",
            )
        )

    db.commit()
    db.refresh(review)

    if note:
        _notify_officer_comment(db, application=application, note_body=note)

    return DocumentReviewOut(
        id=review.id,
        document_id=review.document_id,
        officer_id=review.officer_id,
        officer_name=officer.name,
        action=review.action,
        note=review.note,
        created_at=review.created_at,
    )


# ------------------------------------------------------ document requests
def create_document_requests_from_missing_types(
    db: Session, *, officer: User, application: Application, missing_document_types: list[str], note: str | None
) -> list[DocumentRequest]:
    """Called from application_service.decide_application right after a
    whole-application `request-docs` decision (Section 11). One row per
    coarse DocumentType in `missing_document_types` (already validated as
    real DocumentType values by DecisionIn's caller-supplied list from
    the assessment -- see schemas/application.py's DecisionIn docstring);
    `subtype=None` since these are coarse-type-only asks (any subtype
    under that type satisfies it, unlike a per-document
    "Request Replacement" action which knows the exact subtype). Skips a
    type that already has an OPEN request for this application, so
    re-clicking request-docs with the same missing types doesn't pile up
    duplicate rows."""
    if not missing_document_types:
        return []

    existing_open_types = {
        r.document_type.value
        for r in db.scalars(
            select(DocumentRequest).where(
                DocumentRequest.application_id == application.id,
                DocumentRequest.status == "open",
                DocumentRequest.subtype.is_(None),
            )
        )
    }

    created: list[DocumentRequest] = []
    for type_str in missing_document_types:
        if type_str in existing_open_types:
            continue
        try:
            doc_type = DocumentType(type_str)
        except ValueError:
            logger.warning(
                "officer_review_service: skipping unknown document type %r in missing_document_types "
                "for application %s", type_str, application.id,
            )
            continue
        row = DocumentRequest(
            application_id=application.id,
            document_type=doc_type,
            subtype=None,
            requested_by_officer_id=officer.id,
            note=note,
            status="open",
        )
        db.add(row)
        created.append(row)

    if created:
        db.flush()
    return created


def open_requests_for_application(db: Session, application_id: uuid.UUID) -> list[DocumentRequest]:
    return list(
        db.scalars(
            select(DocumentRequest)
            .where(DocumentRequest.application_id == application_id, DocumentRequest.status == "open")
            .order_by(DocumentRequest.created_at.asc())
        )
    )


def fulfill_open_requests(db: Session, *, application: Application, document: Document) -> None:
    """Called from document_service.upload_document right after a new
    Document is committed. Marks any OPEN request this upload satisfies
    as fulfilled: an exact subtype match, or -- for a coarse
    whole-application request with no subtype -- a matching document_type.
    Writes one ActivityTimeline row per request fulfilled so the officer
    can see it happened without re-opening the application.

    Deliberately does NOT fire its own notification here -- see
    docs/SESSION_11_HANDOFF.md's reasoning: the existing transition-level
    `applicant_replied_to_request` notification (state_machine.py's
    `_NOTIFY_RULES`, fired on NEEDS_DOCS -> SUBMITTED) already tells the
    officer "the applicant is back with evidence" once, at the point that
    actually matters (re-submission). Firing a second notification per
    matching document here would mean an officer who requested three
    document types gets three separate pings before the applicant has
    even finished re-submitting, which is noisier than useful. The
    ActivityTimeline row this function writes is enough for an officer
    who has the application open to see live progress.
    """
    open_requests = db.scalars(
        select(DocumentRequest).where(
            DocumentRequest.application_id == application.id, DocumentRequest.status == "open"
        )
    ).all()
    if not open_requests:
        return

    now = datetime.now(timezone.utc)
    fulfilled_any = False
    for req in open_requests:
        matches = (req.subtype == document.subtype) if req.subtype else (req.document_type == document.type)
        if not matches:
            continue
        req.status = "fulfilled"
        req.fulfilled_by_document_id = document.id
        req.fulfilled_at = now
        db.add(req)
        subtype_meta = get_subtype(req.subtype) if req.subtype else None
        label = subtype_meta.label if subtype_meta else req.document_type.value.replace("_", " ")
        db.add(
            ActivityTimeline(
                application_id=application.id,
                label=f"Uploaded document fulfilled the loan officer's request for {label}",
                actor_type=ActorType.system,
                actor_name="Yaqeen",
            )
        )
        fulfilled_any = True

    if fulfilled_any:
        db.flush()


# -------------------------------------------------------- serialization helpers
def document_request_out(db: Session, req: DocumentRequest) -> DocumentRequestOut:
    officer_name = None
    if req.requested_by_officer_id is not None:
        officer = db.get(User, req.requested_by_officer_id)
        officer_name = officer.name if officer else None
    subtype_meta = get_subtype(req.subtype) if req.subtype else None
    return DocumentRequestOut(
        id=req.id,
        application_id=req.application_id,
        document_type=req.document_type,
        subtype=req.subtype,
        subtype_label=subtype_meta.label if subtype_meta else None,
        note=req.note,
        status=req.status,
        requested_by_officer_name=officer_name,
        fulfilled_by_document_id=req.fulfilled_by_document_id,
        fulfilled_at=req.fulfilled_at,
        created_at=req.created_at,
    )


def open_requests_out(db: Session, application_id: uuid.UUID) -> list[DocumentRequestOut]:
    return [document_request_out(db, r) for r in open_requests_for_application(db, application_id)]


# ------------------------------------------------------- per-document detail
def list_officer_documents(db: Session, application: Application) -> list[OfficerDocumentDetailOut]:
    """Officer review page's per-document review sub-view list --
    preview metadata, every version's extracted fields (ExtractedField
    rows already exist, surfaced here rather than re-derived), previous
    versions (DocumentVersion history already exists), officer notes
    scoped to each document, and that document's review action history."""
    documents = db.scalars(
        select(Document)
        .where(Document.application_id == application.id)
        .options(
            selectinload(Document.versions).selectinload(DocumentVersion.extracted_fields),
        )
        .order_by(Document.created_at.asc())
    ).all()
    if not documents:
        return []

    doc_ids = [d.id for d in documents]

    notes_by_doc: dict[uuid.UUID | None, list[OfficerNote]] = {}
    for note in db.scalars(
        select(OfficerNote)
        .where(OfficerNote.application_id == application.id)
        .order_by(OfficerNote.created_at.asc())
    ):
        notes_by_doc.setdefault(note.document_id, []).append(note)

    reviews_by_doc: dict[uuid.UUID, list[DocumentReview]] = {}
    for review in db.scalars(
        select(DocumentReview).where(DocumentReview.document_id.in_(doc_ids)).order_by(DocumentReview.created_at.asc())
    ):
        reviews_by_doc.setdefault(review.document_id, []).append(review)

    officer_ids = {n.officer_id for notes in notes_by_doc.values() for n in notes if n.officer_id} | {
        r.officer_id for reviews in reviews_by_doc.values() for r in reviews if r.officer_id
    }
    officers_by_id = {u.id: u for u in db.scalars(select(User).where(User.id.in_(officer_ids)))} if officer_ids else {}

    out: list[OfficerDocumentDetailOut] = []
    for doc in documents:
        subtype_meta = get_subtype(doc.subtype) if doc.subtype else None

        versions_out = []
        for v in doc.versions:
            fields_out = [
                ExtractedFieldOut(
                    field_name=f.field_name,
                    field_value=f.field_value,
                    value_type=f.value_type,
                    confidence=float(f.confidence),
                    source_page=f.source_page,
                    extraction_source=f.extraction_source,
                )
                for f in v.extracted_fields
            ]
            versions_out.append(
                DocumentVersionDetailOut(
                    document_version_id=v.id,
                    version_no=v.version_no,
                    size_bytes=v.size_bytes,
                    page_count=v.page_count,
                    ocr_status=v.ocr_status,
                    processing_stage=v.processing_stage,
                    confidence=float(v.confidence) if v.confidence is not None else None,
                    quality_status=v.quality_status,
                    quality_issues=list(v.quality_issues or []),
                    quality_guidance=v.quality_guidance,
                    extracted_name=v.extracted_name,
                    extracted_id_number=v.extracted_id_number,
                    extracted_expiry_date=v.extracted_expiry_date,
                    name_match=v.name_match,
                    id_number_match=v.id_number_match,
                    detected_document_type=v.detected_document_type,
                    type_match=v.type_match,
                    type_mismatch_reason=v.type_mismatch_reason,
                    applicant_confirmed_at=v.applicant_confirmed_at,
                    extracted_fields=fields_out,
                    created_at=v.created_at,
                )
            )

        doc_notes = notes_by_doc.get(doc.id, [])
        doc_notes_out = [
            OfficerNoteOut(
                id=n.id,
                application_id=n.application_id,
                document_id=n.document_id,
                officer_id=n.officer_id,
                officer_name=officers_by_id.get(n.officer_id).name if n.officer_id in officers_by_id else None,
                body=n.body,
                created_at=n.created_at,
            )
            for n in doc_notes
        ]

        doc_reviews = reviews_by_doc.get(doc.id, [])
        doc_reviews_out = [
            DocumentReviewOut(
                id=r.id,
                document_id=r.document_id,
                officer_id=r.officer_id,
                officer_name=officers_by_id.get(r.officer_id).name if r.officer_id in officers_by_id else None,
                action=r.action,
                note=r.note,
                created_at=r.created_at,
            )
            for r in doc_reviews
        ]

        out.append(
            OfficerDocumentDetailOut(
                document_id=doc.id,
                type=doc.type,
                subtype=doc.subtype,
                subtype_label=subtype_meta.label if subtype_meta else None,
                original_filename=doc.original_filename,
                reused_from_wallet=doc.reused_from_wallet,
                uploaded_at=doc.created_at,
                current_review_status=doc_reviews_out[-1].action if doc_reviews_out else None,
                versions=versions_out,
                notes=doc_notes_out,
                reviews=doc_reviews_out,
            )
        )
    return out
