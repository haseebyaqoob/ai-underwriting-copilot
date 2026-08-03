import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin
from app.db.models.enums import DocumentType, TransactionDirection


class EvidenceTransaction(TimestampMixin, Base):
    """
    Core engineering principle this session exists to enforce:
    **extract once, compute forever.** Gemini/deterministic extraction
    happens exactly once per document version, into this normalized shape.
    Every downstream computation (revenue estimation, scoring, consistency
    checks) reads this table with ordinary SQL/Python and NEVER calls
    Gemini at view time.

    One row per money-movement line item (or, for `direction=scale_proxy`
    rows, one row per business-scale signal like a utility bill's total).
    Populated by `app/services/evidence_transactions.py::normalize_and_persist`,
    called from the Celery task (`app/background/tasks.py`) right after
    the existing `ExtractedField` rows are written for a document version
    -- this is additive to that pipeline, not a replacement of it.

    Adding a new document (or a new version of an existing one) only ever
    appends rows here; nothing here is ever updated in place, and nothing
    is deleted except via the application's own cascade delete. Re-running
    extraction for one document does not touch another document's rows.
    """

    __tablename__ = "evidence_transactions"
    __table_args__ = (
        Index("ix_evidence_transactions_app_date", "application_id", "transaction_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Denormalized onto the row (not just reachable via document_id) so the
    # revenue estimator and scoring queries can filter by application_id
    # directly without a join through documents -- this table is read far
    # more often than written, and it's read per-application every time an
    # applicant or officer opens a detail page.
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    source_type: Mapped[DocumentType] = mapped_column(SAEnum(DocumentType, name="document_type"), nullable=False)

    # Nullable: some extractions (e.g. a khata line the model could read
    # the amount of but not the date) legitimately produce a transaction
    # with no usable date. A null-dated row still counts toward evidence
    # coverage but is excluded from date-windowed revenue sums.
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    direction: Mapped[TransactionDirection] = mapped_column(
        SAEnum(TransactionDirection, name="transaction_direction"), nullable=False
    )
    counterparty_label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 0-100 scale, matching the existing `extracted_fields.confidence`
    # convention (see app/db/models/extracted_field.py) rather than 0-1,
    # so a developer reading both tables doesn't have to remember two
    # different scales for "confidence".
    extraction_confidence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)

    application: Mapped["Application"] = relationship()
    document: Mapped["Document"] = relationship()
    document_version: Mapped["DocumentVersion"] = relationship()
