import uuid

from sqlalchemy import String, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin
from app.db.models.enums import OrgType


class Organization(TimestampMixin, Base):
    """
    Tenant boundary. An applicant's business (e.g. Al-Madina Kiryana) and a
    lender (e.g. Bank Alfa) are both organizations, distinguished by `type`.
    Loan officers and admins belong to a `lender` org; an application's
    `org_id` on the lender side scopes what officers/admins can see.
    """

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[OrgType] = mapped_column(SAEnum(OrgType, name="org_type"), nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="organization")
