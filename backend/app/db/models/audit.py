import uuid

from sqlalchemy import String, ForeignKey, JSON, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin
from app.db.models.enums import ActorType


class AuditLog(TimestampMixin, Base):
    """
    Insert-only. `actor_user_id` is nullable — null means "System". No
    application-level update/delete path exists for this model, and the
    plan (see architecture doc, section 9) is to also revoke UPDATE/DELETE
    grants on this table at the DB role level so even a compromised app
    credential can't rewrite history.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str] = mapped_column(String(100), nullable=False)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    actor: Mapped["User | None"] = relationship()


class ActivityTimeline(TimestampMixin, Base):
    """Backs the applicant/officer 'timeline' UI directly, one row per event."""

    __tablename__ = "activity_timeline"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    actor_type: Mapped[ActorType] = mapped_column(SAEnum(ActorType, name="actor_type"), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(255), nullable=False)

    application: Mapped["Application"] = relationship(back_populates="timeline")
