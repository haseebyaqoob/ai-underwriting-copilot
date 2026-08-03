import uuid

from sqlalchemy import String, Enum as SAEnum, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin
from app.db.models.enums import Role, UserStatus


class User(TimestampMixin, Base):
    """
    Maps 1:1 to the frontend's `AuthUser` shape ({id, email, name, role, org}),
    so `schemas.auth.UserOut` can serialize this directly with no shim layer.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(SAEnum(Role, name="user_role"), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status"), nullable=False, default=UserStatus.active
    )
    # Profile page's "Notification Preferences" section (Section 8/9). A
    # single on/off switch, not per-event-type granularity -- there's no
    # email/SMS provider wired up yet (see auth.py's forgot-password
    # docstring), so this only ever controls whether in-app `Notification`
    # rows get written at all; a granular per-category version can layer
    # on top later without a breaking schema change.
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )

    organization: Mapped["Organization"] = relationship(back_populates="users")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
