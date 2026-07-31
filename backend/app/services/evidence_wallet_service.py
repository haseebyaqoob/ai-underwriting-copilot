"""
Evidence Wallet -- "every uploaded document becomes reusable" (product
brief). Design choice, stated up front: `Document`/`DocumentVersion` stay
application-scoped (unchanged from the existing architecture -- every
document still belongs to exactly one application, which is what
document_service.py, the state machine, and evidence_transactions.py all
assume). `EvidenceWalletItem` is a separate, USER-scoped index of "the most
recent good upload for each checklist subtype", used two ways:

1. Read: `GET /applicant/evidence/wallet` lists it directly (the "CNIC --
   Verified -- Uploaded 3 days ago" panel).
2. Write, via `attach_from_wallet`: creates a NEW `Document` + one
   `DocumentVersion` on the TARGET application, pointing at the SAME
   `storage_key` as the wallet's source version (so the file's bytes are
   never re-uploaded or duplicated on disk), copies over the already-known
   quality/extraction metadata, and marks `Document.reused_from_wallet =
   True`. The new version still gets queued through the normal
   `_enqueue_processing` path so a wallet-sourced document appears in
   `evidence_transactions` for the NEW application too (its revenue/score
   should reflect all its own evidence, wallet-sourced or not) --
   deliberately not treated as a special case there.

This means "reuse from wallet" costs one row-copy + one (cheap, idempotent)
re-run of the existing pipeline, not a schema change to
`evidence_transactions`, `scoring.py`, or `revenue_estimator.py`.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import DocumentAccessDeniedError, DocumentNotFoundError
from app.db.models.application import Application
from app.db.models.audit import ActivityTimeline
from app.db.models.document import Document, DocumentVersion
from app.db.models.enums import ActorType, OcrStatus
from app.db.models.evidence_wallet import EvidenceWalletItem
from app.db.models.user import User
from app.services import state_machine
from app.services.evidence_catalog import get_subtype
from app.ws.events import publish_event


def upsert_wallet_item(
    db: Session, *, user_id: uuid.UUID, subtype: str, category: str, document: Document, version: DocumentVersion
) -> None:
    """Called right after a fresh upload (document_service.upload_document)
    and again after processing completes (background/tasks.py), so the
    wallet always reflects the latest known status without the applicant
    doing anything extra. Idempotent: one row per (user, subtype)."""
    existing = db.scalar(
        select(EvidenceWalletItem).where(EvidenceWalletItem.user_id == user_id, EvidenceWalletItem.subtype == subtype)
    )
    if existing is None:
        existing = EvidenceWalletItem(
            user_id=user_id,
            subtype=subtype,
            category=category,
            original_filename=document.original_filename,
            status=version.quality_status,
        )
        db.add(existing)
    existing.latest_document_id = document.id
    existing.latest_document_version_id = version.id
    existing.original_filename = document.original_filename
    existing.status = version.quality_status
    db.flush()


def list_wallet(db: Session, *, user: User) -> list[EvidenceWalletItem]:
    return list(
        db.scalars(
            select(EvidenceWalletItem)
            .where(EvidenceWalletItem.user_id == user.id)
            .order_by(EvidenceWalletItem.updated_at.desc())
        )
    )


def applications_using_count(db: Session, *, user_id: uuid.UUID, subtype: str) -> int:
    """
    Evidence Wallet redesign: "number of applications using it" (product
    brief). Counts DISTINCT applications, owned by this user, that have
    at least one `Document` of this subtype -- covers both a document
    that originated on that application AND one attached via
    `attach_from_wallet` (both are ordinary `Document` rows, see
    `attach_from_wallet`'s docstring), so a wallet item's reuse count on
    screen always matches what officers would see across applications.
    Not stored on `EvidenceWalletItem` itself (would need a write on
    every application's document set change, for a number that's cheap
    to compute at read time on a small per-user table).
    """
    count = db.scalar(
        select(func.count(func.distinct(Document.application_id)))
        .select_from(Document)
        .join(Application, Application.id == Document.application_id)
        .where(Application.applicant_id == user_id, Document.subtype == subtype)
    )
    return int(count or 0)


def attach_from_wallet(
    db: Session, *, user: User, application_id: uuid.UUID, wallet_item_id: uuid.UUID
) -> "DocumentUploadOut":
    from app.schemas.document import DocumentUploadOut  # local import: avoids a schemas<->service import cycle

    application = db.get(Application, application_id)
    if application is None:
        raise DocumentNotFoundError()
    if application.applicant_id != user.id:
        raise DocumentAccessDeniedError()
    state_machine.assert_document_upload_allowed(application)

    wallet_item = db.get(EvidenceWalletItem, wallet_item_id)
    if wallet_item is None or wallet_item.user_id != user.id:
        raise DocumentNotFoundError()
    if wallet_item.latest_document_version_id is None:
        raise DocumentNotFoundError()

    source_version = db.get(DocumentVersion, wallet_item.latest_document_version_id)
    source_document = db.get(Document, wallet_item.latest_document_id) if source_version else None
    if source_version is None or source_document is None:
        raise DocumentNotFoundError()

    subtype_meta = get_subtype(wallet_item.subtype)
    document_type = subtype_meta.document_type if subtype_meta else source_document.type

    new_document = Document(
        application_id=application.id,
        uploaded_by=user.id,
        type=document_type,
        original_filename=source_document.original_filename,
        subtype=wallet_item.subtype,
        reused_from_wallet=True,
    )
    db.add(new_document)
    db.flush()

    # Shares the SAME storage_key -- no bytes are copied or re-uploaded.
    # Quality/extraction metadata is copied forward too, since re-running
    # the AI quality pass on a file that was already verified would be
    # wasted cost for no new information.
    new_version = DocumentVersion(
        document_id=new_document.id,
        version_no=1,
        storage_key=source_version.storage_key,
        size_bytes=source_version.size_bytes,
        page_count=source_version.page_count,
        ocr_status=source_version.ocr_status,
        confidence=source_version.confidence,
        quality_status=source_version.quality_status,
        quality_issues=source_version.quality_issues,
        quality_guidance=source_version.quality_guidance,
        extracted_name=source_version.extracted_name,
        extracted_id_number=source_version.extracted_id_number,
        extracted_expiry_date=source_version.extracted_expiry_date,
        name_match=source_version.name_match,
        id_number_match=source_version.id_number_match,
    )
    db.add(new_version)
    db.flush()

    wallet_item.times_reused += 1
    wallet_item.last_used_at = new_version.created_at

    db.add(
        ActivityTimeline(
            application_id=application.id,
            label=f"Reused {wallet_item.original_filename} from Evidence Wallet ({subtype_meta.label if subtype_meta else wallet_item.subtype})",
            actor_type=ActorType.applicant,
            actor_name=user.name,
        )
    )

    db.commit()
    db.refresh(new_version)

    _reextract_for_new_application(new_version.id)

    return DocumentUploadOut(
        document_id=new_document.id,
        document_version_id=new_version.id,
        version_no=new_version.version_no,
        type=new_document.type,
        original_filename=new_document.original_filename,
        size_bytes=new_version.size_bytes,
        ocr_status=new_version.ocr_status,
    )


def _reextract_for_new_application(document_version_id: uuid.UUID) -> None:
    """A wallet-sourced document still needs its own `evidence_transactions`
    rows written for the NEW application (extraction is per-application,
    per evidence_transactions.py's "one document version -> one
    application's worth of normalized rows" model) -- so this re-runs the
    same Celery pipeline rather than trying to copy transaction rows
    across applications directly. Cheap: the deterministic parsers are
    fast, and the LLM step only re-runs for LLM-bound document types."""
    from app.background.tasks import process_document_task

    process_document_task.delay(str(document_version_id))
