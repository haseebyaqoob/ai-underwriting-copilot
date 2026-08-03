"""
Section 10/11 additions: everything needed for the Loan Officer review page
and the Document Request workflow that the last two sessions deliberately
deferred (see docs/SESSION_10_HANDOFF.md's "Not started this session").

Three new, additive tables:

- `OfficerNote` -- a real note an officer leaves on an application (and,
  optionally, on one specific document within it). This is what finally
  calls `NotificationEventType.officer_comment`, which existed in the enum
  and the notification templates since the notification-system session but
  had no caller (see notification_service.py's `_SEVERITY`/`_title_body`).
  Visible to the applicant on their own timeline the moment it's left --
  enforced by always writing a matching `ActivityTimeline` row alongside
  it, same pattern as every other officer action in this codebase.

- `DocumentRequest` -- makes "officer asked for more evidence" concrete
  and trackable instead of a one-line free-text note buried in a
  transition's audit metadata. Two ways a request gets created:
    1. Whole-application `request-docs` decision (Section 11): one row per
       coarse `DocumentType` in `DecisionIn.missing_document_types`
       (`subtype=None` -- any subtype under that coarse type satisfies it).
    2. A per-document "Request Replacement" / "Request Additional
       Evidence" action from the new per-document review sub-view
       (Section 10): one row with a specific `subtype` set, tied to the
       evidence-catalog slot that document already occupies.
  A request is `fulfilled` the moment the applicant uploads a document
  whose (subtype, or coarse type when subtype is None) matches an open
  request on the same application -- see
  `app/services/officer_review_service.py::fulfill_open_requests`, called
  from `document_service.upload_document`.

- `DocumentReview` -- the officer's per-document decision (approve /
  reject / request-replacement / request-additional-evidence), distinct
  from the whole-application approve/reject/request-docs actions that
  already exist in `application_service.decide_application`. One row per
  action taken (append-only, like `AuditLog`); the *latest* row for a
  document is its "current" review status.

All three use plain `String` columns for action/status fields rather than
native Postgres ENUMs, matching this codebase's own established reasoning
for UI-facing, still-evolving vocabularies (see `EvidenceQualityStatus`'s
and `Document.subtype`'s docstrings for why: avoids an `ALTER TYPE ...
ADD VALUE` migration per new value).
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin
from app.db.models.enums import DocumentType


class OfficerNote(TimestampMixin, Base):
    __tablename__ = "officer_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable: a note can be left on the application as a whole (no
    # document context) or scoped to one specific document -- both render
    # on the applicant's timeline the same way, the document link just
    # lets the officer-side UI group notes under the document they're
    # about.
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    officer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    # Always True in this session (every note an officer leaves here is
    # applicant-visible, per the brief: "visible to the applicant on
    # their timeline once left") -- kept as a real column, not a hardcoded
    # constant, so a future "internal-only note" feature doesn't need a
    # schema migration to add it.
    visible_to_applicant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    application: Mapped["Application"] = relationship()
    document: Mapped["Document | None"] = relationship()
    officer: Mapped["User | None"] = relationship()


class DocumentRequest(TimestampMixin, Base):
    __tablename__ = "document_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Coarse type the request is about -- always set, even when `subtype`
    # is also set (subtype implies its own document_type via the evidence
    # catalog, but denormalizing it here means a fulfillment-matching
    # query never has to look the subtype up first).
    document_type: Mapped[DocumentType] = mapped_column(SAEnum(DocumentType, name="document_type"), nullable=False)
    # Set when the request came from a per-document "Request Replacement"/
    # "Request Additional Evidence" action (Section 10) -- ties it to one
    # exact evidence-catalog slot (see app/services/evidence_catalog.py).
    # Left null when the request came from the whole-application
    # request-docs decision's `missing_document_types` (Section 11) --
    # those are coarse-type-only, so ANY subtype under that document_type
    # fulfills it.
    subtype: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    requested_by_officer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # "open" | "fulfilled" | "cancelled". Plain string, see module
    # docstring.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    fulfilled_by_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    application: Mapped["Application"] = relationship()
    requested_by: Mapped["User | None"] = relationship()
    fulfilled_by_document: Mapped["Document | None"] = relationship()


class DocumentReview(TimestampMixin, Base):
    """One row per officer action taken on a specific document -- append-
    only, like `AuditLog`. The most recent row for a `document_id` is that
    document's "current" review status (see
    `officer_review_service.list_officer_documents`)."""

    __tablename__ = "document_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    officer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # "approved" | "rejected" | "replacement_requested" |
    # "additional_evidence_requested". Plain string, see module docstring.
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    note: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    document: Mapped["Document"] = relationship()
    officer: Mapped["User | None"] = relationship()
