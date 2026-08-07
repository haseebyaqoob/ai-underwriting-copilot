import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.rbac import require_officer, require_officer_or_admin
from app.db.models.enums import ApplicationStatus
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.application import (
    DecisionIn,
    OfficerApplicationDetailOut,
    OfficerDashboardOut,
    PaginatedApplicationsOut,
    ReopenIn,
)
from app.schemas.document import (
    DocumentReviewCreateIn,
    DocumentReviewOut,
    EvidenceChecklistOut,
    OfficerDocumentDetailOut,
    OfficerNoteCreateIn,
    OfficerNoteOut,
)
from app.services import application_service, document_service

router = APIRouter(prefix="/officer", tags=["officer"])


@router.get("/queue", response_model=PaginatedApplicationsOut)
def queue(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    status: ApplicationStatus | None = Query(default=None),
    q: str | None = Query(default=None, description="Search by id, business, or city"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer_or_admin),
):
    return application_service.officer_queue(db, current_user, page, page_size, status, q)


@router.get("/applications/{application_id}", response_model=OfficerApplicationDetailOut)
def get_application(
    application_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer_or_admin),
):
    return application_service.get_officer_application_detail(db, current_user, application_id)


@router.get("/applications/{application_id}/documents", response_model=list[OfficerDocumentDetailOut])
def get_application_documents(
    application_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer_or_admin),
):
    """Completes Section 10: every uploaded document's own review
    sub-view -- preview metadata, every version's extracted fields,
    previous versions, officer notes, and per-document review history."""
    return application_service.list_officer_documents(db, current_user, application_id)


@router.get("/applications/{application_id}/evidence-checklist", response_model=EvidenceChecklistOut)
def get_application_evidence_checklist(
    application_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer_or_admin),
):
    """Completes Section 10's Evidence Summary: per-category status,
    reusing the exact Required/Recommended/Optional tiering and status
    vocabulary from the Evidence Wallet redesign -- no raw percentages."""
    return application_service.get_officer_evidence_checklist(db, current_user, application_id)


@router.post("/applications/{application_id}/notes", response_model=OfficerNoteOut, status_code=201)
def add_note(
    application_id: uuid.UUID,
    payload: OfficerNoteCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer_or_admin),
):
    """A real officer note, applicant-visible on their timeline the
    moment it's left. Optionally scoped to one document via
    `document_id`. Fires `NotificationEventType.officer_comment`."""
    return application_service.add_officer_note(
        db, current_user, application_id, payload.document_id, payload.body
    )


@router.get("/documents/{document_id}/file")
def get_document_file(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer_or_admin),
):
    """Per-document review sub-view's "Preview" action (Section 10)."""
    raw_bytes, mime_type, filename = document_service.get_document_file_for_officer(
        db, org_id=current_user.org_id, document_id=document_id
    )
    return Response(content=raw_bytes, media_type=mime_type, headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.post("/documents/{document_id}/review", response_model=DocumentReviewOut, status_code=201)
def review_document(
    document_id: uuid.UUID,
    payload: DocumentReviewCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer_or_admin),
):
    """Per-document approve/reject/request-replacement/request-additional-
    evidence -- distinct from the whole-application approve/reject/
    request-docs actions below. `replacement_requested`/
    `additional_evidence_requested` also open a trackable DocumentRequest
    against this document's subtype (Section 11)."""
    return application_service.review_document(db, current_user, document_id, payload.action, payload.note)


@router.post("/applications/{application_id}/start-review", response_model=OfficerApplicationDetailOut)
def start_review(
    application_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer_or_admin),
):
    """SUBMITTED -> IN_REVIEW."""
    return application_service.start_review(db, current_user, application_id)


@router.post("/applications/{application_id}/approve", response_model=OfficerApplicationDetailOut)
def approve(
    application_id: uuid.UUID,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer_or_admin),
):
    return application_service.decide_application(db, current_user, application_id, "approve", payload)


@router.post("/applications/{application_id}/reject", response_model=OfficerApplicationDetailOut)
def reject(
    application_id: uuid.UUID,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer_or_admin),
):
    return application_service.decide_application(db, current_user, application_id, "reject", payload)


@router.post("/applications/{application_id}/request-docs", response_model=OfficerApplicationDetailOut)
def request_docs(
    application_id: uuid.UUID,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer_or_admin),
):
    """Completes Section 11: also creates concrete, trackable
    DocumentRequest rows for each of `payload.missing_document_types`
    (see application_service.decide_application)."""
    return application_service.decide_application(db, current_user, application_id, "request_docs", payload)


@router.post("/applications/{application_id}/reopen", response_model=OfficerApplicationDetailOut)
def reopen(
    application_id: uuid.UUID,
    payload: ReopenIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer_or_admin),
):
    """APPROVED/REJECTED -> IN_REVIEW, requires an explicit logged reason."""
    return application_service.reopen_application(db, current_user, application_id, payload)


@router.get("/dashboard", response_model=OfficerDashboardOut)
def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer_or_admin),
):
    return application_service.officer_dashboard(db, current_user)
