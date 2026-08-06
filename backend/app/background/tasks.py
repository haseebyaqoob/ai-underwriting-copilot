"""
Module 3/4/5 — the actual document-processing pipeline, run as a Celery
task so the upload request returns immediately (Module 3) and the real
work (Module 4's deterministic parse, Module 5's LLM fallback/khata path)
happens off the request path.
"""
import logging
from datetime import datetime, timezone

import magic

from app.background.celery_app import celery_app
from app.db.models.application import Application
from app.db.models.document import Document, DocumentVersion
from app.db.models.enums import DocumentType, NotificationEventType, OcrStatus
from app.db.models.extracted_field import ExtractedField
from app.db.session import SessionLocal
from app.services import evidence_wallet_service, notification_service
from app.services.ai import get_ai_provider
from app.services.ai.provider_base import DocumentTypeCheck
from app.services.document_pipeline import router as pipeline_router
from app.services.evidence_catalog import IDENTITY_SUBTYPES, get_subtype
from app.services.evidence_transactions import RawField, persist_transactions
from app.storage import get_storage
from app.ws.events import publish_event

logger = logging.getLogger(__name__)

_DETERMINISTIC_FIRST_TYPES = (DocumentType.utility_bills, DocumentType.wallet_statements)
_KNOWN_MIME_TYPES = ("application/pdf", "image/jpeg", "image/png", "image/heic", "image/heif")


@celery_app.task(name="process_document", bind=True, max_retries=0)
def process_document_task(self, document_version_id: str) -> None:
    """
    Module 9 (hardening) is where real retry/backoff ("3 attempts,
    exponential backoff, then mark failed and prompt re-upload") lands —
    `max_retries=0` here is deliberate, not an oversight: this session
    stops at "the plumbing works end-to-end", not full production
    resilience.
    """
    db = SessionLocal()
    try:
        version = db.get(DocumentVersion, document_version_id)
        if version is None:
            logger.error("process_document_task: DocumentVersion %s not found", document_version_id)
            return

        document = db.get(Document, version.document_id)
        application = db.get(Application, document.application_id)

        version.ocr_status = OcrStatus.processing
        version.processing_stage = "reading_document"
        if document.subtype:
            version.quality_status = "processing"
        db.commit()
        _notify_stage(application, document, version)

        try:
            raw_bytes = get_storage().read(version.storage_key)
            mime_type = _resolve_mime_type(raw_bytes, version.storage_key)

            # Session 12 (AI requirement #1/#5): before extracting any
            # fields, check that the uploaded file actually looks like the
            # expected document type. Only runs for checklist uploads
            # (document.subtype set) -- those are the ones with a specific,
            # human-meaningful "expected label" to check against; generic
            # DocumentType buckets like "other" don't have one.
            subtype_meta = get_subtype(document.subtype) if document.subtype else None
            if subtype_meta is not None:
                version.processing_stage = "extracting_text"
                db.commit()
                _notify_stage(application, document, version)

                type_check = _run_type_check(document=document, subtype_label=subtype_meta.label, raw_bytes=raw_bytes, mime_type=mime_type)
                if type_check is not None:
                    version.detected_document_type = type_check.detected_label
                    version.type_match = type_check.matches
                    version.type_mismatch_reason = None if type_check.matches else type_check.reason
                    db.commit()

                    if not type_check.matches:
                        # Wrong document: stop here, do NOT continue to
                        # normal extraction (product brief, ai_requirements
                        # #1 and #5). No ExtractedField rows, no
                        # evidence_transactions, no wallet upsert for a
                        # document that isn't what it claims to be.
                        version.ocr_status = OcrStatus.done
                        version.processing_stage = "wrong_document"
                        version.quality_status = "wrong_document"
                        version.quality_guidance = (
                            f"This looks like a {type_check.detected_label}, not a {subtype_meta.label}. "
                            f"Please upload the correct document."
                        )
                        version.confidence = round(type_check.confidence * 100, 2)
                        version.processed_at = datetime.now(timezone.utc)
                        db.commit()
                        logger.info(
                            "process_document_task: %s flagged wrong_document (expected=%s, detected=%s)",
                            document_version_id, subtype_meta.label, type_check.detected_label,
                        )
                        _notify_stage(application, document, version)
                        return

            if document.type not in _DETERMINISTIC_FIRST_TYPES:
                # khata, tax_filing, invoice, other: always LLM-bound, no
                # deterministic attempt to even try first. Flag it visibly
                # rather than leaving it looking like a generic
                # "processing" — see OcrStatus.awaiting_vision's docstring.
                version.ocr_status = OcrStatus.awaiting_vision
                db.commit()

            version.processing_stage = "extracting_fields"
            db.commit()
            _notify_stage(application, document, version)

            result = pipeline_router.process(file_bytes=raw_bytes, mime_type=mime_type, document_type=document.type)

            for f in result.fields:
                db.add(
                    ExtractedField(
                        document_version_id=version.id,
                        field_name=f.field_name,
                        field_value=f.field_value,
                        value_type=f.value_type,
                        confidence=round(f.confidence * 100, 2),  # DB convention: 0-100, see extracted_field.py
                        source_page=f.source_page,
                        bbox=f.bbox,
                        extraction_source=result.source,
                    )
                )

            # Extract-once-compute-forever boundary: normalize this same
            # field list into evidence_transactions rows. Additive to the
            # ExtractedField writes above, not a replacement -- see
            # app/services/evidence_transactions.py's module docstring.
            raw_fields = [
                RawField(
                    field_name=f.field_name,
                    field_value=f.field_value,
                    value_type=f.value_type,
                    confidence=f.confidence,
                )
                for f in result.fields
            ]
            version.processing_stage = "running_validation"
            db.commit()
            _notify_stage(application, document, version)

            txn_count = persist_transactions(
                db,
                application_id=application.id,
                document_id=document.id,
                document_version_id=version.id,
                document_type=document.type,
                fields=raw_fields,
            )
            logger.info(
                "process_document_task: %s normalized into %d evidence_transactions row(s)",
                document_version_id, txn_count,
            )

            overall_pct = (
                round(sum(f.confidence for f in result.fields) / len(result.fields) * 100, 2) if result.fields else 0.0
            )
            version.confidence = overall_pct
            version.ocr_status = OcrStatus.done
            version.processing_stage = "done"
            version.processed_at = datetime.now(timezone.utc)
            db.commit()
            _notify_stage(application, document, version)

            logger.info(
                "process_document_task: %s processed via %s path (provider=%s, %d fields, confidence=%.2f%%)",
                document_version_id, result.source, result.provider, len(result.fields), overall_pct,
            )

            # Evidence Checklist quality pass -- deliberately its own
            # try/except, separate from the extraction try/except above:
            # a photo (shop_front, shop_interior) has nothing for
            # pipeline_router.process to extract but still needs a quality
            # verdict, and a quality-check failure (e.g. GEMINI_API_KEY
            # not configured in this environment) must not undo an
            # otherwise-successful extraction.
            if document.subtype:
                _run_quality_assessment(db, document=document, version=version, raw_bytes=raw_bytes, mime_type=mime_type)
                db.commit()
                subtype_meta = get_subtype(document.subtype)
                if subtype_meta and document.uploaded_by:
                    evidence_wallet_service.upsert_wallet_item(
                        db, user_id=document.uploaded_by, subtype=document.subtype,
                        category=subtype_meta.category, document=document, version=version,
                    )
                    db.commit()
        except Exception:
            logger.exception("process_document_task: extraction failed for %s", document_version_id)
            db.rollback()
            version.ocr_status = OcrStatus.failed
            version.processing_stage = "failed"
            db.commit()
        finally:
            _dispatch_processed_notification(db, application=application, document=document, version=version)
            _notify_processed(application, document, version)
    finally:
        db.close()


def _run_quality_assessment(
    db, *, document: Document, version: DocumentVersion, raw_bytes: bytes, mime_type: str
) -> None:
    """Runs the AI quality pass for one Evidence Checklist upload and
    writes the result onto `version`. Never claims document authenticity
    or government verification -- only image quality and, for CNIC
    front/back, whether the OCR'd name/CNIC number matches the
    application (see app/services/ai/provider_base.py's QualityAssessment
    docstring). Swallows its own exceptions (logs + falls back to
    "uploaded" with no issues) so a missing/misconfigured AI provider
    degrades gracefully instead of leaving the checklist item stuck on
    "processing" forever."""
    is_identity = document.subtype in IDENTITY_SUBTYPES
    try:
        provider = get_ai_provider()
        assessment = provider.assess_quality(
            file_bytes=raw_bytes, mime_type=mime_type, document_type=document.type.value,
            is_identity_document=is_identity,
        )
    except Exception:
        logger.exception(
            "process_document_task: quality assessment unavailable for %s (subtype=%s) — leaving as 'uploaded'",
            version.id, document.subtype,
        )
        version.quality_status = "uploaded"
        version.quality_issues = None
        version.quality_guidance = None
        return

    version.quality_status = assessment.status
    version.quality_issues = assessment.issues or None
    version.quality_guidance = assessment.guidance

    if is_identity:
        version.extracted_name = assessment.extracted_name
        version.extracted_id_number = assessment.extracted_id_number
        version.extracted_expiry_date = assessment.extracted_expiry_date
        version.name_match, version.id_number_match = _cross_check_identity(db, document=document, assessment=assessment)
        # Bug fixed this pass: a name/CNIC mismatch used to overload
        # `quality_status = "needs_better_image"`, which told applicants
        # to "retake the photo" for a problem no re-photographing could
        # ever fix (the photo was fine; the typed Business-page fields
        # didn't match it). Distinct status so the checklist UI can show
        # an accurate label + guidance instead of a misleading one.
        if version.name_match is False or version.id_number_match is False:
            version.quality_status = "mismatch"
            version.quality_guidance = (
                "The name or CNIC number on this document doesn't match what you entered on the Business page. "
                "Double-check for typos there, or make sure this is your own CNIC."
            )


def _cross_check_identity(db, *, document: Document, assessment) -> tuple[bool | None, bool | None]:
    """Fuzzy name-match (reusing the same threshold/library as
    app/services/consistency_checks.py, so "does this match" means the
    same thing everywhere in the product) + exact digit-match on CNIC
    number against the owning application's own fields."""
    from rapidfuzz import fuzz

    application = db.get(Application, document.application_id)
    if application is None:
        return None, None

    name_match: bool | None = None
    if assessment.extracted_name and application.owner_name:
        name_match = fuzz.token_sort_ratio(assessment.extracted_name.lower(), application.owner_name.lower()) >= 72.0

    id_match: bool | None = None
    if assessment.extracted_id_number and application.cnic_number:
        extracted_digits = "".join(c for c in assessment.extracted_id_number if c.isdigit())
        id_match = extracted_digits == application.cnic_number

    return name_match, id_match


def _run_type_check(*, document: Document, subtype_label: str, raw_bytes: bytes, mime_type: str) -> "DocumentTypeCheck | None":
    """Session 12: wraps provider.check_document_type in its own
    try/except, same defensive posture as `_run_quality_assessment` below
    -- an AI-provider outage must degrade to "skip the check, extract
    normally" rather than blocking every upload on Gemini being up."""
    try:
        provider = get_ai_provider()
        return provider.check_document_type(file_bytes=raw_bytes, mime_type=mime_type, expected_label=subtype_label)
    except Exception:
        logger.exception(
            "process_document_task: document-type check unavailable for subtype=%s — skipping straight to extraction",
            document.subtype,
        )
        return None


def _notify_stage(application: Application | None, document: Document, version: DocumentVersion) -> None:
    """Session 12: fired after every `processing_stage` change so the
    frontend's OCR progress line ('Uploading -> Reading document ->
    Extracting text -> Extracting fields -> Running validation ->
    Finished') updates live over the websocket instead of only at
    upload-start and fully-done. Same best-effort posture as
    `_notify_processed` -- a publish failure here must never break the
    pipeline."""
    event = {"type": "document.stage", "id": str(version.id), "stage": version.processing_stage}
    try:
        if document.uploaded_by:
            publish_event(f"user:{document.uploaded_by}", event)
        if application is not None:
            publish_event(f"application:{application.id}", event)
    except Exception:
        logger.exception("process_document_task: failed to publish stage event for %s", version.id)


def _resolve_mime_type(raw_bytes: bytes, storage_key: str) -> str:
    sniffed = magic.from_buffer(raw_bytes, mime=True)
    if sniffed in _KNOWN_MIME_TYPES:
        return sniffed
    # Same HEIC fallback reasoning as document_service._sniff_and_validate —
    # by this point the upload was already validated once, so trusting the
    # storage key's extension here is a fallback on already-vetted data,
    # not a first line of defense against a malicious upload.
    lower_key = storage_key.lower()
    if lower_key.endswith((".heic", ".heif")):
        return "image/heic"
    if lower_key.endswith(".png"):
        return "image/png"
    if lower_key.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower_key.endswith(".pdf"):
        return "application/pdf"
    return sniffed


def _dispatch_processed_notification(
    db, *, application: Application | None, document: Document, version: DocumentVersion
) -> None:
    """Only fires "Document Verified" on a genuinely clean result --
    `pending`/`processing`/`awaiting_vision` are mid-flight states no
    applicant needs a notification for, `failed` isn't a verification at
    all, and a bad `quality_status` (needs_better_image/mismatch) means
    the document isn't actually verified even though OCR technically
    finished, so none of those fire this notification. Best-effort, same
    posture as every other notification dispatch point -- must never
    break document processing itself."""
    if application is None or version.ocr_status != OcrStatus.done:
        return
    if document.subtype and version.quality_status in ("needs_better_image", "mismatch", "wrong_document"):
        return
    try:
        notification_service.notify_applicant(
            db, application=application, event_type=NotificationEventType.document_verified,
            document_id=document.id, doc_label=document.type.value.replace("_", " "),
        )
        db.commit()
    except Exception:
        logger.exception(
            "process_document_task: failed to dispatch document_verified notification for %s", version.id
        )
        db.rollback()


def _notify_processed(application: Application | None, document: Document, version: DocumentVersion) -> None:
    event = {"type": "document.processed", "id": str(version.id)}
    if document.uploaded_by:
        publish_event(f"user:{document.uploaded_by}", event)
    if application is not None:
        publish_event(f"application:{application.id}", event)
        if application.lender_org_id:
            publish_event(f"org:{application.lender_org_id}:officer_queue", event)
