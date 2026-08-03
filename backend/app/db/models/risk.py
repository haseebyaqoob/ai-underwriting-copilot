import uuid
from datetime import datetime

from sqlalchemy import Integer, String, Enum as SAEnum, ForeignKey, DateTime, Numeric, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin, utcnow
from app.db.models.enums import RiskLevel


class RiskScore(TimestampMixin, Base):
    """
    `risk_level` is computed server-side by the risk engine (Module 3+),
    not inferred client-side from raw score thresholds — see architecture
    doc challenge #2. Thresholds live in `admin_config`, not in code.
    """

    __tablename__ = "risk_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(SAEnum(RiskLevel, name="risk_level"), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    application: Mapped["Application"] = relationship(back_populates="risk_scores")
    ai_reports: Mapped[list["AIReport"]] = relationship(back_populates="risk_score")


class AIReport(TimestampMixin, Base):
    """
    `contributions` is JSONB (e.g. {"cashflow": 86, "evidence": 92,
    "ledger_match": 94, "filing": 64}) so new contribution factors can be
    added/removed without a migration.
    """

    __tablename__ = "ai_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    risk_score_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("risk_scores.id", ondelete="SET NULL"), nullable=True
    )
    summary_text: Mapped[str] = mapped_column(String(4000), nullable=False)
    contributions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    application: Mapped["Application"] = relationship(back_populates="ai_reports")
    risk_score: Mapped["RiskScore | None"] = relationship(back_populates="ai_reports")
