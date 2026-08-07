import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.rbac import require_applicant
from app.db.models.enums import DocumentType
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.application import (
    ApplicantDashboardOut,
    ApplicationCreateIn,
    ApplicationDetailOut,
    PaginatedApplicationsOut,
)
from app.schemas.document import (
    AttachFromWalletIn,
    DocumentConfirmIn,
    DocumentConfirmOut,
    DocumentQueueOut,
    DocumentUploadOut,
    EvidenceChecklistOut,
    EvidenceWalletItemOut,
)
from app.services import application_service, document_service, evidence_checklist_service, evidence_wallet_service
from app.services.evidence_catalog import get_subtype

router = APIRouter(prefix="/applicant", tags=["applicant"])


@router.post("/applications", response_model=ApplicationDetailOut, status_code=201)
def create_application(
    payload: ApplicationCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    return application_service.create_application(db, current_user, payload)


@router.get("/applications", response_model=PaginatedApplicationsOut)
def list_applications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    return application_service.list_applicant_applications(db, current_user, page, page_size)


@router.get("/applications/{application_id}", response_model=ApplicationDetailOut)
def get_application(
    application_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    return application_service.get_applicant_application_detail(db, current_user, application_id)


@router.post("/applications/{application_id}/submit", response_model=ApplicationDetailOut)
def submit_application(
    application_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    """DRAFT -> SUBMITTED. See app/services/state_machine.py for the
    full transition table and mutability rules."""
    return application_service.submit_application(db, current_user, application_id)


@router.post("/applications/{application_id}/withdraw", response_model=ApplicationDetailOut)
def withdraw_application(
    application_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    """DRAFT/SUBMITTED/NEEDS_DOCS -> WITHDRAWN, applicant-initiated."""
    return application_service.withdraw_application(db, current_user, application_id)


@router.get("/dashboard", response_model=ApplicantDashboardOut)
def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    return application_service.applicant_dashboard(db, current_user)


@router.post("/documents", response_model=DocumentUploadOut, status_code=201)
def upload_document(
    application_id: uuid.UUID = Form(...),
    document_type: DocumentType = Form(...),
    subtype: str | None = Form(default=None),
    replaces_document_id: uuid.UUID | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    raw_bytes = file.file.read()
    return document_service.upload_document(
        db,
        applicant=current_user,
        application_id=application_id,
        document_type=document_type,
        filename=file.filename or "upload",
        raw_bytes=raw_bytes,
        replaces_document_id=replaces_document_id,
        subtype=subtype,
    )


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    document_service.delete_document(db, applicant=current_user, document_id=document_id)


@router.post("/documents/{document_id}/confirm", response_model=DocumentConfirmOut)
def confirm_document(
    document_id: uuid.UUID,
    payload: DocumentConfirmIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    """Evidence review's "Looks correct? Confirm / Edit" step (product
    brief, AI requirement #3). Confirms the AI's extracted reading is
    accurate, optionally after applying corrections in the same call.
    Never a claim about document authenticity -- see
    document_service.confirm_extracted_fields's docstring."""
    document = document_service.confirm_extracted_fields(
        db,
        applicant=current_user,
        document_id=document_id,
        edits=[(e.field_name, e.field_value) for e in payload.edits],
    )
    version = document.versions[-1]
    return DocumentConfirmOut(
        document_id=document.id,
        document_version_id=version.id,
        applicant_confirmed_at=version.applicant_confirmed_at,
        fields_edited=len(payload.edits),
    )


@router.get("/documents/{document_id}/file")
def get_document_file(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    """Evidence Checklist "Preview" action. Streams the raw file back --
    no thumbnailing/transcoding in this session, matching the brief's
    "prioritize usability... over visual effects" and keeping the storage
    layer untouched (app/storage/base.py's StorageBackend interface)."""
    raw_bytes, mime_type, filename = document_service.get_document_file(
        db, applicant=current_user, document_id=document_id
    )
    return Response(content=raw_bytes, media_type=mime_type, headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.get("/documents/queue", response_model=DocumentQueueOut)
def document_queue(
    application_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    items = document_service.list_document_queue(db, applicant=current_user, application_id=application_id)
    return DocumentQueueOut(items=items)


@router.get("/evidence/checklist", response_model=EvidenceChecklistOut)
def evidence_checklist(
    application_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    checklist = evidence_checklist_service.build_checklist(db, applicant=current_user, application_id=application_id)
    return evidence_checklist_service.to_out(db, checklist)


@router.get("/evidence/wallet", response_model=list[EvidenceWalletItemOut])
def evidence_wallet(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    items = evidence_wallet_service.list_wallet(db, user=current_user)
    out = []
    for item in items:
        meta = get_subtype(item.subtype)
        out.append(
            EvidenceWalletItemOut(
                id=item.id,
                subtype=item.subtype,
                label=meta.label if meta else item.subtype,
                category=item.category,
                status=item.status,
                original_filename=item.original_filename,
                latest_document_id=item.latest_document_id,
                latest_document_version_id=item.latest_document_version_id,
                times_reused=item.times_reused,
                applications_using_count=evidence_wallet_service.applications_using_count(
                    db, user_id=current_user.id, subtype=item.subtype
                ),
                updated_at=item.updated_at,
            )
        )
    return out


@router.post("/evidence/wallet/attach", response_model=DocumentUploadOut, status_code=201)
def attach_from_wallet(
    payload: AttachFromWalletIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    return evidence_wallet_service.attach_from_wallet(
        db, user=current_user, application_id=payload.application_id, wallet_item_id=payload.wallet_item_id
    )
