"""
Module 3 — upload orchestration: validate -> store -> DB rows -> WS notify
-> enqueue background extraction. No extraction logic lives here (that's
Module 4's document_pipeline + Module 5's ai provider, invoked from the
Celery task in app/background/tasks.py) — this module's job stops at
getting a file safely onto disk and a `documents`/`document_versions` row
into a `pending` state.
"""
import logging
import uuid
from datetime import datetime, timezone

import magic
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    DocumentAccessDeniedError,
    DocumentNotFoundError,
    DocumentNotReadyError,
    DuplicateSingleSlotDocumentError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.db.models.application import Application
from app.db.models.audit import ActivityTimeline
from app.db.models.document import Document, DocumentVersion
from app.db.models.enums import ActorType, DocumentType, NotificationEventType, OcrStatus
from app.db.models.user import User
from app.services import state_machine, evidence_wallet_service, notification_service, officer_review_service
from app.services.evidence_catalog import get_subtype
from app.storage import get_storage
from app.ws.events import publish_event

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB, matches the admin config page (admin.config.tsx)

# Sniffed via python-magic against the actual file bytes, never the
# client-supplied `Content-Type` header or filename extension alone (both
# are trivially spoofable). HEIC/HEIF is an ISO-BMFF container and some
# libmagic builds report it under a generic "ISO Media" description rather
# than a clean `image/heic` mime string, so it's matched more loosely below
# in `_sniff_and_validate` rather than via this exact-match set alone.
ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/heic", "image/heif"}


def _sniff_and_validate(data: bytes, *, declared_filename: str) -> str:
    """Returns the sniffed mime type, or raises UnsupportedFileTypeError /
    FileTooLargeError."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise FileTooLargeError(max_mb=25)
    if len(data) == 0:
        raise UnsupportedFileTypeError("empty file")

    sniffed = magic.from_buffer(data, mime=True)

    if sniffed in ALLOWED_MIME_TYPES:
        return sniffed

    # HEIC/HEIF fallback: libmagic on some systems reports these as
    # "application/octet-stream" or a generic ISO-BMFF description instead
    # of a clean image/heic mime string. If the sniffed type is generic AND
    # the filename extension claims HEIC/HEIF AND the bytes actually start
    # with an ISO-BMFF "ftyp" box, accept it as image/heic — this is still
    # content-based (checking the real magic-byte structure), not just
    # trusting the extension on its own.
    lower_name = declared_filename.lower()
    if sniffed in ("application/octet-stream", "application/mp4") and (
        lower_name.endswith(".heic") or lower_name.endswith(".heif")
    ):
        if len(data) >= 12 and data[4:8] == b"ftyp" and b"hei" in data[8:16].lower():
            return "image/heic"

    raise UnsupportedFileTypeError(sniffed)


def _build_storage_key(*, application_id: uuid.UUID, document_id: uuid.UUID, version_no: int, filename: str) -> str:
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._-") or "file"
    return f"applications/{application_id}/{document_id}/v{version_no}_{safe_name}"


def upload_document(
    db: Session,
    *,
    applicant: User,
    application_id: uuid.UUID,
    document_type: DocumentType,
    filename: str,
    raw_bytes: bytes,
    replaces_document_id: uuid.UUID | None,
    subtype: str | None = None,
) -> "DocumentUploadOut":
    from app.schemas.document import DocumentUploadOut  # local import: avoids a schemas<->service import cycle

    application = db.get(Application, application_id)
    if application is None:
        raise DocumentNotFoundError()  # application doesn't exist -> nothing to attach to
    if application.applicant_id != applicant.id:
        raise DocumentAccessDeniedError()
    # State-machine mutability rule: documents can only be ADDED while the
    # application is in draft/submitted/in_review/needs_docs -- an
    # approved/rejected/withdrawn application is frozen except via an
    # explicit reopen. See app/services/state_machine.py.
    state_machine.assert_document_upload_allowed(application)

    mime_type = _sniff_and_validate(raw_bytes, declared_filename=filename)

    if replaces_document_id is not None:
        # Re-upload / re-shoot of an existing logical document — the
        # "please re-shoot, image is blurry" flow in applicant.upload.tsx.
        # New DocumentVersion, not a new Document, so history isn't lost.
        document = db.get(Document, replaces_document_id)
        if document is None or document.application_id != application.id:
            raise DocumentNotFoundError()
        next_version_no = max((v.version_no for v in document.versions), default=0) + 1
    else:
        subtype_meta = get_subtype(subtype)

        # Server-side enforcement of the catalog's `allow_multiple=False`
        # rule (e.g. cnic_front, cnic_back, shop_front, shop_interior):
        # an application may only ever have ONE logical Document for
        # such a subtype. The frontend already hides the "Upload"
        # control once one exists (`canAddMore` in evidence.tsx's
        # ChecklistItemRow), but that's a client-side courtesy, not
        # enforcement -- a stale frontend build, a double-click race
        # before the UI re-renders, two tabs open, or a direct API call
        # can all still reach this path. Without this check, each such
        # call would create its own Document + DocumentVersion, each
        # independently queued for OCR -- the "4 files, all Processing"
        # bug for a single-slot subtype. This mirrors the fraud-
        # prevention lesson: don't let the client be the only thing
        # enforcing a business rule the server owns.
        if subtype_meta and not subtype_meta.allow_multiple:
            existing = db.scalars(
                select(Document).where(
                    Document.application_id == application.id,
                    Document.subtype == subtype,
                )
            ).first()
            if existing is not None:
                raise DuplicateSingleSlotDocumentError(subtype_meta.label)

        # Evidence Checklist uploads pass a granular `subtype` (e.g.
        # "electricity_bill"); the catalog is authoritative for which
        # coarse DocumentType that maps to, so a mismatched/stale
        # `document_type` from an older client can't silently disagree
        # with the checklist item it was uploaded against. Uploads with
        # no subtype (e.g. the legacy flat upload path, if anything still
        # calls it) keep using the given `document_type` as-is.
        effective_type = subtype_meta.document_type if subtype_meta else document_type
        document = Document(
            application_id=application.id,
            uploaded_by=applicant.id,
            type=effective_type,
            original_filename=filename,
            subtype=subtype if subtype_meta else None,
        )
        db.add(document)
        db.flush()
        next_version_no = 1

    storage_key = _build_storage_key(
        application_id=application.id, document_id=document.id, version_no=next_version_no, filename=filename
    )
    get_storage().save(storage_key, raw_bytes, mime_type)

    version = DocumentVersion(
        document_id=document.id,
        version_no=next_version_no,
        storage_key=storage_key,
        size_bytes=len(raw_bytes),
        ocr_status=OcrStatus.pending,
        # Session 12: the file is physically saved by this point (see
        # get_storage().save above) — "uploading" covers the client-side
        # transfer the frontend already shows before this response even
        # returns; the Celery task advances this to "reading_document" the
        # moment it picks the job up (app/background/tasks.py).
        processing_stage="uploading",
    )
    db.add(version)
    db.flush()

    db.add(
        ActivityTimeline(
            application_id=application.id,
            label=(
                f"Re-uploaded {document.type.value.replace('_', ' ')} "
                f"(v{next_version_no}: {filename})"
                if replaces_document_id is not None
                else f"Uploaded {document.type.value.replace('_', ' ')} ({filename})"
            ),
            actor_type=ActorType.applicant,
            actor_name=applicant.name,
        )
    )

    db.commit()
    db.refresh(version)

    if document.subtype:
        subtype_meta = get_subtype(document.subtype)
        if subtype_meta:
            evidence_wallet_service.upsert_wallet_item(
                db, user_id=applicant.id, subtype=document.subtype, category=subtype_meta.category,
                document=document, version=version,
            )
            db.commit()

    # Section 11 (Document Request workflow): if this upload matches an
    # OPEN DocumentRequest, mark it fulfilled. Best-effort, same failure
    # posture as the notification dispatch right below it -- the upload
    # itself must never fail because of this.
    try:
        officer_review_service.fulfill_open_requests(db, application=application, document=document)
        db.commit()
    except Exception:
        logger.exception(
            "document_service: failed to reconcile document requests for document %s", document.id
        )
        db.rollback()

    _dispatch_upload_notifications(
        db, application=application, document=document, version=version,
        is_replacement=replaces_document_id is not None, actor=applicant,
    )
    _notify_uploaded(application, version)
    _enqueue_processing(version.id)

    return DocumentUploadOut(
        document_id=document.id,
        document_version_id=version.id,
        version_no=version.version_no,
        type=document.type,
        original_filename=document.original_filename,
        size_bytes=version.size_bytes,
        ocr_status=version.ocr_status,
    )


def _dispatch_upload_notifications(
    db: Session, *, application: Application, document: Document, version: DocumentVersion,
    is_replacement: bool, actor: User,
) -> None:
    """Best-effort, same failure posture as state_machine's dispatcher —
    a notification-write failure must never fail the upload itself, since
    the file is already safely on disk and the DB rows already
    committed by the time this runs."""
    doc_label = document.type.value.replace("_", " ")
    try:
        notification_service.notify_applicant(
            db, application=application, event_type=NotificationEventType.document_uploaded,
            document_id=document.id, doc_label=doc_label,
        )
        notification_service.notify_officers(
            db, application=application,
            event_type=(
                NotificationEventType.applicant_updated_existing_evidence
                if is_replacement else NotificationEventType.applicant_uploaded_new_evidence
            ),
            document_id=document.id, doc_label=doc_label, applicant_name=actor.name,
        )
        db.commit()
    except Exception:
        logger.exception(
            "document_service: failed to dispatch upload notifications for document %s", document.id
        )
        db.rollback()


def _notify_uploaded(application: Application, version: DocumentVersion) -> None:
    event = {"type": "document.uploaded", "id": str(version.id)}
    # applicant's own upload queue
    publish_event(f"user:{application.applicant_id}", event)
    # officer queue for the lender org this application belongs to
    if application.lender_org_id:
        publish_event(f"org:{application.lender_org_id}:officer_queue", event)
    # anyone watching this specific application (e.g. an officer with the
    # review workspace open)
    publish_event(f"application:{application.id}", event)


def _enqueue_processing(document_version_id: uuid.UUID) -> None:
    # Imported lazily to avoid a hard import-time dependency between the
    # sync web-request path and the Celery app configuration (keeps
    # `document_service` importable/testable without Celery configured).
    from app.background.tasks import process_document_task

    process_document_task.delay(str(document_version_id))


def delete_document(db: Session, *, applicant: User, document_id: uuid.UUID) -> None:
    """Evidence Checklist "Delete" action. Only allowed while the parent
    application is still mutable (same rule as uploads -- see
    state_machine.assert_document_upload_allowed) so an applicant can't
    remove evidence an officer has already reviewed against. Deliberately
    does NOT touch the Evidence Wallet item -- the wallet's "most recent
    upload" pointer stays put even if this particular application-scoped
    copy is deleted, since the same file may still be attached to other
    applications."""
    document = db.get(Document, document_id)
    if document is None:
        raise DocumentNotFoundError()
    application = db.get(Application, document.application_id)
    if application is None or application.applicant_id != applicant.id:
        raise DocumentAccessDeniedError()
    state_machine.assert_document_upload_allowed(application)

    db.add(
        ActivityTimeline(
            application_id=application.id,
            label=f"Removed {document.original_filename}",
            actor_type=ActorType.applicant,
            actor_name=applicant.name,
        )
    )
    db.delete(document)
    db.commit()


def confirm_extracted_fields(
    db: Session, *, applicant: User, document_id: uuid.UUID, edits: list[tuple[str, str]]
) -> Document:
    """Session 12 (product brief's "Confirm / Edit" step + AI requirement
    #3). Applies any field corrections the applicant made, then stamps
    the LATEST version as applicant-confirmed. `edits` is a list of
    (field_name, field_value) pairs; an empty list means "confirm as-is".

    IMPORTANT: this is a statement that the extracted values match the
    document -- it is explicitly NOT a claim that the document itself is
    authentic (see DocumentVersion.applicant_confirmed_at's docstring and
    QualityAssessment's docstring, which carry the same distinction for
    the AI's own quality pass). Nothing downstream should read this as a
    verification signal.
    """
    document = db.get(Document, document_id)
    if document is None:
        raise DocumentNotFoundError()
    application = db.get(Application, document.application_id)
    if application is None or application.applicant_id != applicant.id:
        raise DocumentAccessDeniedError()

    version = document.versions[-1] if document.versions else None
    if version is None or version.ocr_status != OcrStatus.done:
        raise DocumentNotReadyError()

    if edits:
        by_name = {ef.field_name: ef for ef in version.extracted_fields}
        for field_name, field_value in edits:
            ef = by_name.get(field_name)
            if ef is None:
                continue
            ef.field_value = field_value
            # Provenance stays visible rather than silently overwriting
            # what the AI actually read -- see DocumentConfirmIn's
            # schema docstring for why this distinction matters.
            ef.extraction_source = "applicant_corrected"
            ef.confidence = 100.0

    version.applicant_confirmed_at = datetime.now(timezone.utc)
    version.applicant_confirmed_by = applicant.id

    db.add(
        ActivityTimeline(
            application_id=application.id,
            label=(
                f"Confirmed extracted details for {document.original_filename}"
                if not edits
                else f"Corrected and confirmed extracted details for {document.original_filename}"
            ),
            actor_type=ActorType.applicant,
            actor_name=applicant.name,
        )
    )
    db.commit()
    db.refresh(document)
    return document


def get_document_file(db: Session, *, applicant: User, document_id: uuid.UUID) -> tuple[bytes, str, str]:
    """Evidence Checklist "Preview" action. Returns (raw_bytes, mime_type,
    filename). No caching/CDN layer -- reads straight from the storage
    backend, matching upload_document's own directness."""
    document = db.get(Document, document_id)
    if document is None:
        raise DocumentNotFoundError()
    application = db.get(Application, document.application_id)
    if application is None or application.applicant_id != applicant.id:
        raise DocumentAccessDeniedError()
    return _read_document_file(document)


def get_document_file_for_officer(db: Session, *, org_id, document_id: uuid.UUID) -> tuple[bytes, str, str]:
    """Officer review page's per-document "Preview" action (Section 10).
    Same file, org-scoped instead of applicant-owned -- an officer never
    owns the document, they just need to be in the lender org the
    document's application belongs to (same scoping rule as every other
    officer.py route, see application_service.get_org_scoped_application)."""
    document = db.get(Document, document_id)
    if document is None:
        raise DocumentNotFoundError()
    application = db.get(Application, document.application_id)
    if application is None or application.lender_org_id != org_id:
        raise DocumentAccessDeniedError()
    return _read_document_file(document)


def _read_document_file(document: Document) -> tuple[bytes, str, str]:
    version = document.versions[-1] if document.versions else None
    if version is None:
        raise DocumentNotFoundError()

    raw_bytes = get_storage().read(version.storage_key)
    mime_type = magic.from_buffer(raw_bytes, mime=True)
    return raw_bytes, mime_type, document.original_filename


def list_document_queue(
    db: Session, *, applicant: User, application_id: uuid.UUID | None
) -> list["DocumentQueueItemOut"]:
    """Recent uploads across all of the applicant's applications (or just
    one, if `application_id` is given), newest first — matches the "Recent
    uploads" panel scope in applicant.upload.tsx, which isn't scoped to a
    single application in the current frontend."""
    from app.schemas.document import DocumentQueueItemOut  # local import: avoids a schemas<->service import cycle

    q = (
        select(DocumentVersion)
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(Application, Application.id == Document.application_id)
        .where(Application.applicant_id == applicant.id)
    )
    if application_id is not None:
        q = q.where(Application.id == application_id)
    q = q.order_by(DocumentVersion.created_at.desc()).limit(50)
    rows = db.scalars(q).all()

    items = []
    for version in rows:
        document = version.document
        items.append(
            DocumentQueueItemOut(
                document_id=document.id,
                document_version_id=version.id,
                version_no=version.version_no,
                type=document.type,
                original_filename=document.original_filename,
                size_bytes=version.size_bytes,
                ocr_status=version.ocr_status,
                confidence=float(version.confidence) if version.confidence is not None else None,
                note=_status_note(version),
                created_at=version.created_at,
            )
        )
    return items


def _status_note(version: DocumentVersion) -> str:
    if version.ocr_status == OcrStatus.pending:
        return "Queued for processing"
    if version.ocr_status == OcrStatus.processing:
        return "Processing…"
    if version.ocr_status == OcrStatus.awaiting_vision:
        return "Awaiting AI review (handwritten/unstructured document)"
    if version.ocr_status == OcrStatus.failed:
        return "Processing failed — please try re-uploading"
    if version.ocr_status == OcrStatus.done:
        if version.confidence is not None and version.confidence < 70:
            return "Low confidence — consider re-shooting for a clearer copy"
        return "OCR complete"
    return ""
