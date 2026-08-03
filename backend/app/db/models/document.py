import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Enum as SAEnum, ForeignKey, DateTime, Numeric, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin
from app.db.models.enums import DocumentType, OcrStatus


class Document(TimestampMixin, Base):
    """One row per uploaded file (logical document, e.g. 'the March khata')."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[DocumentType] = mapped_column(SAEnum(DocumentType, name="document_type"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)

    # Evidence Checklist addition: which granular checklist slot this
    # document fills (e.g. "electricity_bill", "shop_front") -- see
    # app/services/evidence_catalog.py for the full catalog and why this
    # is a plain string, not a native Postgres ENUM. Nullable so existing
    # rows (uploaded before the checklist existed) don't break; they just
    # render under a generic "Other" bucket until re-categorized.
    subtype: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)

    # Set when this Document was created by "attach from wallet" rather
    # than a fresh upload -- the bytes are shared with an earlier
    # application's document (same storage_key), not re-uploaded. Purely
    # informational (shown as "Reused from Evidence Wallet" in the UI);
    # nothing in the extraction/scoring pipeline treats it differently.
    reused_from_wallet: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    application: Mapped["Application"] = relationship(back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.version_no"
    )


class DocumentVersion(TimestampMixin, Base):
    """
    Supports re-upload without losing history (e.g. "page 7 is blurry,
    please re-shoot" -> a new version, not an overwrite of the old file).
    """

    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ocr_status: Mapped[OcrStatus] = mapped_column(
        SAEnum(OcrStatus, name="ocr_status"), nullable=False, default=OcrStatus.pending
    )
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Session 12: granular sub-stage within `ocr_status`, updated live by
    # the Celery task (app/background/tasks.py). Plain string, not a
    # native enum -- same "avoid ALTER TYPE ADD VALUE friction" reasoning
    # as `quality_status` below. One of: uploading, reading_document,
    # extracting_text, extracting_fields, running_validation, done,
    # failed, wrong_document. Nullable so pre-existing rows just render
    # nothing extra.
    processing_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Session 12 (AI requirement #1/#5 -- "does the uploaded file even
    # look like the expected document type"). Runs BEFORE field
    # extraction; when `type_match` is False the pipeline skips extraction
    # entirely rather than hallucinating fields onto the wrong document.
    # `type_match=None` means "not yet checked".
    detected_document_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    type_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    type_mismatch_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Session 12 (AI requirement #3 -- applicant confirmation is NOT an
    # authenticity claim, just "this reflects my document"). Distinct
    # from ocr_status == done.
    applicant_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applicant_confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # --- Evidence Checklist addition: AI quality pass (see
    # app/services/ai/provider_base.py's QualityAssessment and
    # app/background/tasks.py's post-extraction quality step). Deliberately
    # separate from `ocr_status`/`confidence` above -- see
    # EvidenceQualityStatus's docstring for why these are different axes.
    # `quality_status` is a plain string, not `SAEnum(EvidenceQualityStatus)`,
    # for the same "avoid ALTER TYPE ADD VALUE friction" reason as
    # `Document.subtype`.
    quality_status: Mapped[str] = mapped_column(String(30), nullable=False, default="uploaded")
    quality_issues: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    quality_guidance: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Identity cross-check (CNIC front/back only -- see
    # app/services/evidence_catalog.py's IDENTITY_SUBTYPES). Never claims
    # government/NADRA verification -- only "does the OCR'd name/number
    # match what the applicant typed on the Business page", per the
    # product brief's explicit "do not claim authenticity" constraint.
    extracted_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extracted_id_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    extracted_expiry_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    name_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    id_number_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="versions")
    extracted_fields: Mapped[list["ExtractedField"]] = relationship(
        back_populates="document_version", cascade="all, delete-orphan"
    )
