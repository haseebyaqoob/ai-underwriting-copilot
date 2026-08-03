import uuid

from sqlalchemy import String, Integer, ForeignKey, Numeric, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin


class ExtractedField(TimestampMixin, Base):
    """
    Generic key-value so utility bill fields (amount_payable, due_date, ...),
    wallet transactions (credit/debit lines), and future khata line-items
    all fit one table without a schema migration per document type. `bbox`
    (nullable JSON: [x, y, w, h, page]) lets the officer review UI highlight
    exactly where on the page a value came from.
    """

    __tablename__ = "extracted_fields"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    field_value: Mapped[str] = mapped_column(String(2000), nullable=False)
    value_type: Mapped[str] = mapped_column(String(30), nullable=False, default="string")  # string|number|date
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Module 4/5 addition: which extraction path produced this value.
    # "deterministic" = regex/fuzzy-match over PDF text or Tesseract OCR
    # (Module 4); "llm" = Gemini vision (Module 5, used for khata and for
    # deterministic low-confidence fallback). Officer review UI can use
    # this to show provenance instead of presenting every value as
    # equally mechanical.
    extraction_source: Mapped[str] = mapped_column(String(20), nullable=False, default="deterministic")

    document_version: Mapped["DocumentVersion"] = relationship(back_populates="extracted_fields")
