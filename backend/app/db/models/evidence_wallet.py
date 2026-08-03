"""
Evidence Wallet -- "every uploaded document becomes reusable" (product
brief). One row per (user, subtype) that has ever been successfully
uploaded, always pointing at the MOST RECENT document/version for that
subtype regardless of which application it was originally uploaded
against. This is deliberately separate from `Document`/`DocumentVersion`
(which stay application-scoped, per the existing architecture) rather than
making documents application-less -- see
app/services/evidence_wallet_service.py's module docstring for the full
reasoning and the "attach from wallet" flow this enables.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, ForeignKey, DateTime, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import TimestampMixin


class EvidenceWalletItem(TimestampMixin, Base):
    __tablename__ = "evidence_wallet_items"
    __table_args__ = (UniqueConstraint("user_id", "subtype", name="uq_evidence_wallet_items_user_subtype"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # See app/services/evidence_catalog.py -- same catalog the checklist
    # uses, so a wallet item and a checklist slot always speak the same
    # vocabulary.
    subtype: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False)

    # Always points at the latest successful upload for this subtype.
    # Nullable FKs with SET NULL: if the underlying document/version is
    # ever hard-deleted, the wallet item degrades to "needs re-upload"
    # rather than cascading away silently (a wallet entry disappearing
    # without explanation would be a confusing UX regression).
    latest_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    latest_document_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True
    )

    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    # Mirrors DocumentVersion.quality_status at the time of the last sync
    # (see evidence_wallet_service._sync_status) -- duplicated rather than
    # joined at read time so the wallet list endpoint is a single cheap
    # query, not N+1 into document_versions.
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="uploaded")

    times_reused: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
