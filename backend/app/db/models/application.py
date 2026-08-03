import uuid

from sqlalchemy import Integer, String, Enum as SAEnum, ForeignKey, Numeric, Sequence
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin
from app.db.models.enums import ApplicationStatus

# Generates the human-facing "YQN-01042" ids the frontend already expects,
# independent of the internal UUID primary key. A Postgres sequence keeps
# this gap-free-ish and safe under concurrent inserts without a
# SELECT MAX(...)+1 race.
#
# Module 2 fix: this Sequence object was declared in Module 1 but never
# actually created in the DB (no `CreateSequence` in the migration) and
# never wired as a column default — dead code, invisible until something
# tried to create an application. The Module 2 migration creates it for
# real and `application_service.py` calls `nextval(...)` explicitly (kept
# explicit rather than a server_default so the service can format it into
# "YQN-01042" in Python).
application_display_id_seq = Sequence("application_display_id_seq", start=1042)


class Application(TimestampMixin, Base):
    """
    Note: `score`, `confidence`, and `documents` count are intentionally NOT
    stored here — they're derived from `risk_scores` (latest row) and
    `documents` (count) respectively, read via a join/subquery in the list
    endpoints. Storing them here would require an UPDATE on every upload or
    rescore and risks silent staleness. See architecture doc, section 2.
    """

    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)

    applicant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lender_org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    officer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    amount_pkr: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    purpose: Mapped[str] = mapped_column(String(255), nullable=False)

    # Added in Module 2 to cover the rest of the "New Application"
    # wizard (business + loan steps) — Module 1 only modeled the fields
    # its own auth-only scope needed. All nullable so existing rows (there
    # shouldn't be any pre-Module-2 application rows, but just in case)
    # don't break.
    business_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    years_operating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tenor_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_repayment: Mapped[str | None] = mapped_column(String(120), nullable=True)

    #  Added this session (CNIC capture feature) ---------------------
    # Lives on `applications`, not `users`, matching the existing
    # `owner_name` field ("Registered owner / CNIC name") which Module 2
    # already put here rather than on the user profile. Rationale: the
    # loan officer underwriting a *specific* application needs the CNIC of
    # the person who owns *that* business/application, and Yaqeen already
    # models identity fields as per-application, not per-user-identity --
    # there's no separate "applicant identity profile" concept anywhere
    # else in the schema to hang this off of instead. Stored as 13 raw
    # digits (no dashes), nullable so existing rows aren't broken; the
    # applicant-facing schema validates/normalizes the format, and masking
    # for non-owner viewers happens in the service layer (see
    # application_service._mask_cnic), never at the DB or transport layer
    # for the applicant's own view.
    cnic_number: Mapped[str | None] = mapped_column(String(13), nullable=True)

    # --- Added this session (Business/Loan page polish) -----------------
    # Business registration status: brief is explicit this product
    # supports "traditional OR alternative financial evidence" and must
    # NOT require registration -- registration_status defaults to
    # "unregistered" (not nullable-and-unset) so every application has an
    # explicit, displayable answer rather than an ambiguous null, while
    # NTN/STRN stay genuinely optional free text regardless of which
    # status is chosen (an unregistered business could still have an NTN
    # from prior tax filings; a registered one might not have entered its
    # STRN yet). Plain `String`, not a native Postgres ENUM -- same
    # "avoid an ALTER TYPE ADD VALUE migration" reasoning as
    # `EvidenceQualityStatus`/`Document.subtype` (see their docstrings) --
    # this is exactly the kind of field a future session might want a
    # third value for (e.g. "registration_pending").
    registration_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unregistered")
    ntn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    strn: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Loan page: optional, because the brief's whole premise is that AI
    # will estimate these later from uploaded evidence (see
    # revenue_estimator.py) -- these are the applicant's OWN estimate,
    # shown to the officer/AI as a self-reported data point to compare
    # the computed estimate against, never a substitute for it. Numeric,
    # not Integer, for the same "PKR amounts are money, not counts"
    # reasoning as `amount_pkr` above.
    monthly_estimated_revenue_pkr: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    monthly_estimated_expenses_pkr: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    status: Mapped[ApplicationStatus] = mapped_column(
        SAEnum(ApplicationStatus, name="application_status"),
        nullable=False,
        default=ApplicationStatus.draft,
    )

    applicant: Mapped["User"] = relationship(foreign_keys=[applicant_id])
    officer: Mapped["User | None"] = relationship(foreign_keys=[officer_id])
    documents: Mapped[list["Document"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    risk_scores: Mapped[list["RiskScore"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    ai_reports: Mapped[list["AIReport"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    timeline: Mapped[list["ActivityTimeline"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    evidence_transactions: Mapped[list["EvidenceTransaction"]] = relationship(
        cascade="all, delete-orphan", overlaps="application"
    )
