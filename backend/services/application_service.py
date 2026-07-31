"""
This session's rewrite: replaces Module 2's fabricated evidence/financial-
metrics/score/AI-summary with real computation from `evidence_transactions`
(see app/services/evidence_transactions.py, revenue_estimator.py,
scoring.py, consistency_checks.py), and formalizes the DRAFT-first
application state machine (app/services/state_machine.py). No endpoint's
*shape* changes gratuitously -- `ApplicationDetailOut` still has an
`evidence` list and a `assessment`/`revenue` pair, they're just computed
from real data now instead of a deterministic PRNG seeded off the
display_id.
"""
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationAccessDeniedError, ApplicationNotFoundError, ApplicationStateError
from app.db.models.application import Application, application_display_id_seq
from app.db.models.audit import ActivityTimeline, AuditLog
from app.db.models.document import Document, DocumentVersion
from app.db.models.enums import ActorType, ApplicationStatus, OrgType
from app.db.models.evidence_transaction import EvidenceTransaction
from app.db.models.extracted_field import ExtractedField
from app.db.models.organization import Organization
from app.db.models.user import User
from app.services import consistency_checks, evidence_checklist_service, evidence_wallet_service, officer_review_service, scoring, state_machine, workflow_stage_service
from app.services.revenue_estimator import RevenueEstimate, TransactionRow, estimate_revenue
from app.schemas.application import (
    AdminDashboardOut,
    ApplicantDashboardOut,
    ApplicationCreateIn,
    ApplicationDetailOut,
    ApplicationListItemOut,
    ConsistencyCheckOut,
    DebtExposureOut,
    DecisionIn,
    EvidenceCoverageOut,
    EvidenceSummaryLineOut,
    InsufficientEvidenceOut,
    OfficerDashboardOut,
    OfficerApplicationDetailOut,
    PaginatedApplicationsOut,
    ProcessingStepOut,
    ReopenIn,
    RevenueEstimateOut,
    ScoredAssessmentOut,
    ScoreFactorOut,
    TimelineEntryOut,
)
from app.schemas.document import ReadinessChecklistItemOut

_NAME_FIELD_NAMES = {"account_holder", "name", "full_name", "holder_name", "cardholder_name"}


def _mask_cnic(cnic: str) -> str:
    """`4210112345671` -> `42101-XXXXXXX-1`, matching the CNIC's real 5-7-1
    digit grouping. Used for every viewer except the owning applicant."""
    return f"{cnic[:5]}-XXXXXXX-{cnic[-1]}"


# ------------------------------------------------------------ org helpers
def get_or_create_default_lender_org(db: Session) -> Organization:
    """
    MVP simplification: a single lender org (matches the frontend's demo
    data — everyone is at "Bank Alfa"). Real multi-lender org assignment/
    routing is out of scope until there's an actual need for it.
    """
    org = db.scalar(select(Organization).where(Organization.type == OrgType.lender))
    if org is not None:
        return org
    org = Organization(name="Bank Alfa", type=OrgType.lender)
    db.add(org)
    db.flush()
    return org


# --------------------------------------------------- evidence_transactions
def _load_transaction_rows(db: Session, application_id: uuid.UUID) -> list[TransactionRow]:
    rows = db.scalars(
        select(EvidenceTransaction).where(EvidenceTransaction.application_id == application_id)
    ).all()
    return [
        TransactionRow(
            source_type=r.source_type.value,
            transaction_date=r.transaction_date,
            amount=Decimal(r.amount),
            direction=r.direction.value,
            extraction_confidence=float(r.extraction_confidence),
        )
        for r in rows
    ]


def _evidence_coverage(db: Session, application_id: uuid.UUID) -> list[EvidenceCoverageOut]:
    rows = db.scalars(
        select(EvidenceTransaction).where(EvidenceTransaction.application_id == application_id)
    ).all()
    by_type: dict[str, list[EvidenceTransaction]] = defaultdict(list)
    for r in rows:
        by_type[r.source_type.value].append(r)

    out = []
    for source_type, items in sorted(by_type.items()):
        dated = [i.transaction_date for i in items if i.transaction_date is not None]
        out.append(
            EvidenceCoverageOut(
                source_type=source_type,
                transaction_count=len(items),
                date_range_start=min(dated) if dated else None,
                date_range_end=max(dated) if dated else None,
                avg_confidence=round(sum(float(i.extraction_confidence) for i in items) / len(items), 1),
            )
        )
    return out


def _gather_name_consistency(
    db: Session, application: Application
) -> list[consistency_checks.ConsistencyResult]:
    if not application.owner_name:
        return []
    rows = db.execute(
        select(ExtractedField.field_value, Document.type)
        .join(DocumentVersion, DocumentVersion.id == ExtractedField.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(Document.application_id == application.id)
        .where(ExtractedField.field_name.in_(_NAME_FIELD_NAMES))
    ).all()
    results = []
    for field_value, doc_type in rows:
        results.append(
            consistency_checks.check_name_consistency(
                declared_name=application.owner_name,
                other_source_label=doc_type.value,
                other_name=field_value,
            )
        )
    return results


def _compute_consistency(
    db: Session, application: Application, revenue: RevenueEstimate
) -> list[consistency_checks.ConsistencyResult]:
    results = [consistency_checks.check_cnic_format(application.cnic_number)]
    results.extend(_gather_name_consistency(db, application))
    results.append(
        consistency_checks.check_wallet_vs_estimate(
            wallet_inflow_monthly=revenue.verified_floor_monthly,
            blended_estimate_monthly=revenue.blended_estimate_monthly,
        )
    )
    return results


def _to_revenue_out(revenue: RevenueEstimate) -> RevenueEstimateOut:
    def _s(v: Decimal | None) -> str | None:
        return str(v) if v is not None else None

    return RevenueEstimateOut(
        verified_floor_monthly_pkr=_s(revenue.verified_floor_monthly),
        blended_estimate_low_monthly_pkr=_s(revenue.blended_estimate_low_monthly),
        blended_estimate_high_monthly_pkr=_s(revenue.blended_estimate_high_monthly),
        window_start=revenue.window_start,
        window_end=revenue.window_end,
        weeks_of_data=revenue.weeks_of_data,
        months_of_data=revenue.months_of_data,
        source_types_used=revenue.source_types_used,
        plausibility_flag=revenue.plausibility_flag,
        plausibility_note=revenue.plausibility_note,
    )


def _consistency_message(c: consistency_checks.ConsistencyResult, *, viewer_is_applicant: bool) -> str:
    """Applicant-facing copy is always the generic non-accusatory string
    when a check fails, regardless of which check it was -- never the
    officer's specific reason. See consistency_checks.py's module
    docstring for why this split is a hard rule, not a style choice."""
    if not viewer_is_applicant:
        return c.officer_message
    if c.passed:
        return c.officer_message  # passed-check copy is already generic/positive
    return c.applicant_message or c.officer_message


def _compute_assessment(
    db: Session, application: Application, *, viewer_is_applicant: bool,
    checklist: "evidence_checklist_service.EvidenceChecklist | None" = None,
) -> tuple[RevenueEstimateOut | None, ScoredAssessmentOut | InsufficientEvidenceOut | None, list[ConsistencyCheckOut]]:
    """The one place score/revenue/consistency are computed, live, from
    `evidence_transactions` -- never stored/cached, per "extract once,
    compute forever". Returns (revenue_out, assessment_out, consistency_out)."""
    txn_rows = _load_transaction_rows(db, application.id)
    revenue = estimate_revenue(txn_rows)
    document_types_present = {r.source_type for r in txn_rows}

    consistency_results = _compute_consistency(db, application, revenue)
    consistency_out = [
        ConsistencyCheckOut(
            check_id=c.check_id,
            passed=c.passed,
            message=_consistency_message(c, viewer_is_applicant=viewer_is_applicant),
        )
        for c in consistency_results
    ]
    pass_count = sum(1 for c in consistency_results if c.passed)

    score_result = scoring.compute_score(
        revenue=revenue,
        document_types_present=document_types_present,
        cnic_digits=application.cnic_number,
        consistency_pass_count=pass_count,
        consistency_total=len(consistency_results),
        amount_pkr=Decimal(application.amount_pkr),
        tenor_months=application.tenor_months or 0,
        years_operating=application.years_operating,
    )

    revenue_out = _to_revenue_out(revenue) if txn_rows else None

    # Every score computation gets an audit row, per the architecture
    # spec's "every score computation (with full factor breakdown)"
    # requirement. Trade-off flagged in the handoff doc: since this fires
    # on every detail-view read (not just decisions), the audit log grows
    # with view traffic, not just with material changes -- acceptable for
    # this session's scope, worth revisiting (e.g. debounce per
    # application per hour) if audit_logs volume becomes a real concern.
    if isinstance(score_result, scoring.InsufficientEvidence):
        snapshot = {
            "outcome": "insufficient_evidence",
            "reasons": score_result.reasons,
            "document_types_present": score_result.document_types_present,
        }
        state_machine.log_score_computation(db, application_id=application.id, score_snapshot=snapshot)
        db.commit()
        readiness_items: list[ReadinessChecklistItemOut] = []
        if checklist is not None:
            readiness_items = [
                ReadinessChecklistItemOut(key=i.key, label=i.label, met=i.met, detail=i.detail)
                for i in evidence_checklist_service.build_readiness_checklist(
                    checklist,
                    independent_types_count=len(score_result.document_types_present),
                    weeks_of_data=score_result.weeks_of_data,
                )
            ]
        return (
            revenue_out,
            InsufficientEvidenceOut(
                reasons=score_result.reasons,
                missing_document_types=score_result.missing_document_types,
                document_types_present=score_result.document_types_present,
                weeks_of_data=score_result.weeks_of_data,
                readiness_checklist=readiness_items,
            ),
            consistency_out,
        )

    snapshot = {
        "outcome": "scored",
        "score": score_result.score_0_1000,
        "confidence": score_result.confidence_0_100,
        "risk_level": score_result.risk_level,
        "factors": [f.__dict__ for f in score_result.factors],
    }
    state_machine.log_score_computation(db, application_id=application.id, score_snapshot=snapshot)
    db.commit()

    assessment_out = ScoredAssessmentOut(
        score=score_result.score_0_1000,
        confidence=score_result.confidence_0_100,
        risk_level=score_result.risk_level,
        factors=[
            ScoreFactorOut(key=f.key, label=f.label, weight_pct=f.weight_pct, factor_score=f.factor_score_0_100, explanation=f.explanation)
            for f in score_result.factors
        ],
        debt_exposure=DebtExposureOut(status=score_result.debt_exposure.status, note=score_result.debt_exposure.note),
        weeks_of_data=score_result.weeks_of_data,
    )
    return revenue_out, assessment_out, consistency_out


# --------------------------------------------------------------- applicant
def create_application(db: Session, applicant: User, payload: ApplicationCreateIn) -> ApplicationDetailOut:
    seq_val = db.execute(application_display_id_seq)
    display_id = f"YQN-{seq_val:05d}"

    lender_org = get_or_create_default_lender_org(db)

    app_row = Application(
        display_id=display_id,
        applicant_id=applicant.id,
        lender_org_id=lender_org.id,
        business_name=payload.business_name,
        business_type=payload.business_type,
        owner_name=payload.owner_name,
        city=payload.city,
        years_operating=payload.years_operating,
        employee_count=payload.employee_count,
        amount_pkr=payload.amount_pkr,
        tenor_months=payload.tenor_months,
        purpose=payload.purpose,
        preferred_repayment=payload.preferred_repayment,
        cnic_number=payload.cnic_number,
        registration_status=payload.registration_status,
        ntn=payload.ntn,
        strn=payload.strn,
        monthly_estimated_revenue_pkr=payload.monthly_estimated_revenue_pkr,
        monthly_estimated_expenses_pkr=payload.monthly_estimated_expenses_pkr,
        status=ApplicationStatus.draft,
    )
    db.add(app_row)
    db.flush()

    db.add(
        ActivityTimeline(
            application_id=app_row.id,
            label="Application draft created",
            actor_type=ActorType.applicant,
            actor_name=applicant.name,
        )
    )
    db.add(
        AuditLog(
            actor_user_id=applicant.id,
            action="application_created",
            target_type="application",
            target_id=str(app_row.id),
            extra_metadata={"status": ApplicationStatus.draft.value},
        )
    )

    db.commit()
    db.refresh(app_row)
    return _to_detail(db, app_row, mask_cnic=False, viewer_is_applicant=True)


def submit_application(db: Session, applicant: User, application_id: uuid.UUID) -> ApplicationDetailOut:
    app_row = _get_owned_application(db, applicant, application_id)
    state_machine.apply_transition(
        db, application=app_row, to_status=ApplicationStatus.submitted, actor=applicant
    )
    db.commit()
    db.refresh(app_row)
    return _to_detail(db, app_row, mask_cnic=False, viewer_is_applicant=True)


def withdraw_application(db: Session, applicant: User, application_id: uuid.UUID) -> ApplicationDetailOut:
    app_row = _get_owned_application(db, applicant, application_id)
    state_machine.apply_transition(
        db, application=app_row, to_status=ApplicationStatus.withdrawn, actor=applicant
    )
    db.commit()
    db.refresh(app_row)
    return _to_detail(db, app_row, mask_cnic=False, viewer_is_applicant=True)


def _get_owned_application(db: Session, applicant: User, application_id: uuid.UUID) -> Application:
    app_row = db.get(Application, application_id)
    if app_row is None:
        raise ApplicationNotFoundError()
    if app_row.applicant_id != applicant.id:
        raise ApplicationAccessDeniedError()
    return app_row


def list_applicant_applications(
    db: Session, applicant: User, page: int, page_size: int
) -> PaginatedApplicationsOut:
    base_q = select(Application).where(Application.applicant_id == applicant.id)
    total = db.scalar(select(func.count()).select_from(base_q.subquery())) or 0

    rows = db.scalars(
        base_q.order_by(Application.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [_to_list_item(db, r) for r in rows]
    return PaginatedApplicationsOut(items=items, total=total, page=page, page_size=page_size)


def get_applicant_application_detail(db: Session, applicant: User, application_id: uuid.UUID) -> ApplicationDetailOut:
    app_row = _get_owned_application(db, applicant, application_id)
    return _to_detail(db, app_row, mask_cnic=False, viewer_is_applicant=True)


def applicant_dashboard(db: Session, applicant: User) -> ApplicantDashboardOut:
    all_rows = db.scalars(
        select(Application).where(Application.applicant_id == applicant.id).order_by(Application.created_at.desc())
    ).all()

    active_statuses = {
        ApplicationStatus.submitted,
        ApplicationStatus.in_review,
        ApplicationStatus.needs_docs,
    }
    active_count = sum(1 for a in all_rows if a.status in active_statuses)

    recent = [_to_list_item(db, a) for a in all_rows[:5]]

    app_ids = [a.id for a in all_rows]
    timeline_rows: list[ActivityTimeline] = []
    if app_ids:
        timeline_rows = db.scalars(
            select(ActivityTimeline)
            .where(ActivityTimeline.application_id.in_(app_ids))
            .order_by(ActivityTimeline.created_at.desc())
            .limit(10)
        ).all()
    timeline_out = [
        TimelineEntryOut(at=t.created_at, label=t.label, actor_type=t.actor_type.value, actor_name=t.actor_name)
        for t in timeline_rows
    ]
    ai_activity_out = [t for t in timeline_out if t.actor_type == "ai"][:10]

    # "Evidence Completion 78%" / missing-required-evidence panel: pinned
    # to the single most-recently-updated ACTIVE (non-draft, non-terminal)
    # application -- see ApplicantDashboardOut's docstring for why this
    # isn't averaged across applications.
    primary_application_id: uuid.UUID | None = None
    evidence_completion_pct: int | None = None
    missing_required_evidence: list[str] = []
    evidence_summary: list[EvidenceSummaryLineOut] = []
    active_rows = [a for a in all_rows if a.status in active_statuses]
    if active_rows:
        primary = max(active_rows, key=lambda a: a.updated_at)
        primary_application_id = primary.id
        checklist = evidence_checklist_service.build_checklist(db, applicant=applicant, application_id=primary.id)
        evidence_completion_pct = checklist.overall_completion_pct
        missing_required_evidence = [
            item.label
            for cat in checklist.categories
            for item in cat.items
            if item.required and item.status != "verified"
        ]
        # Dashboard redesign: "Evidence Completion 2%" -> a short set of
        # friendly lines ("Identity Verified", "Business Evidence
        # Needed", "Financial Records Missing"). Identity and Financial
        # Records map straight onto existing checklist categories;
        # "Business Evidence" blends photos + proof, matching the same
        # blend `_build_strength`'s "Business Activity" factor uses, so
        # the dashboard and Evidence page tell a consistent story.
        def _cat(key: str):
            return next((c for c in checklist.categories if c.key == key), None)

        identity_cat = _cat("identity")
        financial_cat = _cat("business_financial")
        photos_cat = _cat("business_photos")
        proof_cat = _cat("business_proof")
        business_status = (
            "Needs Documents"
            if (photos_cat and photos_cat.status_label == "Needs Documents")
            or (proof_cat and proof_cat.status_label == "Needs Documents")
            else "Verified"
            if (photos_cat and photos_cat.status_label == "Verified") and (proof_cat is None or proof_cat.status_label in ("Verified", "Strong", "Good"))
            else "Pending"
        )
        evidence_summary = [
            EvidenceSummaryLineOut(key="identity", label="Identity", status=identity_cat.status_label if identity_cat else "Needs Documents"),
            EvidenceSummaryLineOut(key="business_evidence", label="Business Evidence", status=business_status),
            EvidenceSummaryLineOut(key="financial_records", label="Financial Records", status=financial_cat.status_label if financial_cat else "Needs Documents"),
        ]

    wallet_items = evidence_wallet_service.list_wallet(db, user=applicant)
    wallet_reusable_count = len(wallet_items)
    wallet_subtypes = {w.subtype for w in wallet_items}

    # "Next Step" (dashboard redesign): the first still-missing REQUIRED
    # item, in checklist order -- same source (`checklist.categories`,
    # already built above for `missing_required_evidence`) and same
    # ordering the Evidence page itself renders in, so "Upload Shop
    # Interior Photo" here always points at the actual next item the
    # Evidence Wizard would open on, never a stale/re-sorted guess.
    next_step_label: str | None = None
    next_step_wallet_available = False
    if active_rows:
        for cat in checklist.categories:
            for item in cat.items:
                if item.required and item.status != "verified":
                    next_step_label = item.label
                    next_step_wallet_available = item.subtype in wallet_subtypes
                    break
            if next_step_label:
                break

    return ApplicantDashboardOut(
        active_application_count=active_count,
        total_application_count=len(all_rows),
        recent_applications=recent,
        activity_timeline=timeline_out,
        primary_application_id=primary_application_id,
        evidence_completion_pct=evidence_completion_pct,
        missing_required_evidence=missing_required_evidence,
        evidence_summary=evidence_summary,
        next_step_label=next_step_label,
        next_step_wallet_available=next_step_wallet_available,
        wallet_reusable_count=wallet_reusable_count,
        ai_activity=ai_activity_out,
    )


# ----------------------------------------------------------------- officer
def officer_queue(
    db: Session,
    officer: User,
    page: int,
    page_size: int,
    status_filter: ApplicationStatus | None,
    search: str | None,
) -> PaginatedApplicationsOut:
    base_q = select(Application).where(Application.lender_org_id == officer.org_id)
    if status_filter is not None:
        base_q = base_q.where(Application.status == status_filter)
    if search:
        like = f"%{search.strip()}%"
        base_q = base_q.where(
            or_(
                Application.display_id.ilike(like),
                Application.business_name.ilike(like),
                Application.city.ilike(like),
            )
        )

    total = db.scalar(select(func.count()).select_from(base_q.subquery())) or 0
    rows = db.scalars(
        base_q.order_by(Application.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [_to_list_item(db, r) for r in rows]
    return PaginatedApplicationsOut(items=items, total=total, page=page, page_size=page_size)


def _to_officer_detail(db: Session, app_row: Application) -> OfficerApplicationDetailOut:
    base = _to_detail(db, app_row, mask_cnic=True, viewer_is_applicant=False)
    return OfficerApplicationDetailOut(
        **base.model_dump(),
        wallet_usage=officer_review_service.wallet_usage(db, app_row),
        open_document_requests=officer_review_service.open_requests_out(db, app_row.id),
    )


def get_officer_application_detail(db: Session, officer: User, application_id: uuid.UUID) -> OfficerApplicationDetailOut:
    app_row = get_org_scoped_application(db, officer, application_id)
    return _to_officer_detail(db, app_row)


def get_org_scoped_application(db: Session, officer: User, application_id: uuid.UUID) -> Application:
    app_row = db.get(Application, application_id)
    if app_row is None:
        raise ApplicationNotFoundError()
    if app_row.lender_org_id != officer.org_id:
        raise ApplicationAccessDeniedError()
    return app_row


def start_review(db: Session, officer: User, application_id: uuid.UUID) -> OfficerApplicationDetailOut:
    app_row = get_org_scoped_application(db, officer, application_id)
    state_machine.apply_transition(db, application=app_row, to_status=ApplicationStatus.in_review, actor=officer)
    if app_row.officer_id is None:
        app_row.officer_id = officer.id
        db.add(app_row)
    db.commit()
    db.refresh(app_row)
    return _to_officer_detail(db, app_row)


_DECISION_STATUS_MAP = {
    "approve": ApplicationStatus.approved,
    "reject": ApplicationStatus.rejected,
    "request_docs": ApplicationStatus.needs_docs,
}


def decide_application(
    db: Session, officer: User, application_id: uuid.UUID, decision: str, payload: DecisionIn
) -> OfficerApplicationDetailOut:
    if decision not in _DECISION_STATUS_MAP:
        raise ApplicationStateError(f"Unknown decision '{decision}'.")
    app_row = get_org_scoped_application(db, officer, application_id)

    # "Decision screen shows score-at-decision-time explicitly" -- compute
    # it fresh right now and snapshot it onto the transition's audit row,
    # rather than trusting whatever the officer's browser last fetched
    # (which could be stale by the time they click a decision button).
    _, assessment_out, _ = _compute_assessment(db, app_row, viewer_is_applicant=False)
    score_snapshot = (
        assessment_out.model_dump() if assessment_out is not None else {"status": "unknown"}
    )

    to_status = _DECISION_STATUS_MAP[decision]
    state_machine.apply_transition(
        db,
        application=app_row,
        to_status=to_status,
        actor=officer,
        reason_code=payload.reason_code,
        note=payload.note,
        score_snapshot=score_snapshot,
    )
    db.commit()
    db.refresh(app_row)

    if decision == "request_docs":
        # Section 11 (Document Request workflow): the transition above
        # already fires `additional_evidence_requested` (state_machine's
        # `_NOTIFY_RULES`) and records the free-text note in the
        # transition's audit metadata -- this makes the request concrete
        # and trackable rather than just a line in the audit log, so the
        # applicant's Evidence page can render it per-subtype.
        officer_review_service.create_document_requests_from_missing_types(
            db, officer=officer, application=app_row,
            missing_document_types=payload.missing_document_types or [],
            note=payload.note,
        )
        db.commit()

    return _to_officer_detail(db, app_row)


def reopen_application(
    db: Session, officer: User, application_id: uuid.UUID, payload: ReopenIn
) -> OfficerApplicationDetailOut:
    app_row = get_org_scoped_application(db, officer, application_id)
    state_machine.apply_transition(
        db,
        application=app_row,
        to_status=ApplicationStatus.in_review,
        actor=officer,
        reason_code=payload.reason_code,
        note=payload.note,
    )
    db.commit()
    db.refresh(app_row)
    return _to_officer_detail(db, app_row)


def officer_dashboard(db: Session, officer: User) -> OfficerDashboardOut:
    org_q = select(Application).where(Application.lender_org_id == officer.org_id)
    rows = db.scalars(org_q).all()

    queue_statuses = {ApplicationStatus.submitted, ApplicationStatus.in_review, ApplicationStatus.needs_docs}
    queue_count = sum(1 for a in rows if a.status in queue_statuses)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    approvals_30d = sum(1 for a in rows if a.status == ApplicationStatus.approved and a.updated_at >= cutoff)
    rejections_30d = sum(1 for a in rows if a.status == ApplicationStatus.rejected and a.updated_at >= cutoff)

    breakdown: dict[str, int] = {}
    for a in rows:
        breakdown[a.status.value] = breakdown.get(a.status.value, 0) + 1

    return OfficerDashboardOut(
        queue_count=queue_count,
        approvals_last_30d=approvals_30d,
        rejections_last_30d=rejections_30d,
        # No decision-timestamp tracking yet -- would need a dedicated
        # "decided_at" column or a query over audit_logs filtered to
        # decision transitions; left null rather than fabricated.
        avg_time_to_decision_minutes=None,
        status_breakdown=breakdown,
    )


# ------------------------------------------------------------------- admin
def admin_dashboard(db: Session, admin: User) -> AdminDashboardOut:
    """
    Deliberately NOT scoped to `admin.org_id` -- see Module 2's original
    reasoning in the architecture doc (admins are platform operators, not
    lender staff, in this product's current demo-org setup).
    """
    rows = db.scalars(select(Application)).all()

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    submitted_30d = sum(1 for a in rows if a.created_at >= cutoff)

    decided = [a for a in rows if a.status in (ApplicationStatus.approved, ApplicationStatus.rejected)]
    approval_rate = (
        round(sum(1 for a in decided if a.status == ApplicationStatus.approved) / len(decided) * 100, 1)
        if decided
        else None
    )

    breakdown: dict[str, int] = {}
    total_volume = 0
    for a in rows:
        breakdown[a.status.value] = breakdown.get(a.status.value, 0) + 1
        total_volume += a.amount_pkr

    return AdminDashboardOut(
        total_applications=len(rows),
        submitted_last_30d=submitted_30d,
        approval_rate=approval_rate,
        status_breakdown=breakdown,
        total_volume_pkr=total_volume,
    )


# ----------------------------------------------------------- serialization
def _to_list_item(db: Session, app_row: Application) -> ApplicationListItemOut:
    documents_count = db.scalar(
        select(func.count()).select_from(Document).where(Document.application_id == app_row.id)
    ) or 0

    # List views show the live-computed score/risk_level too (not a
    # stored fixture) -- cheap enough at list-page sizes (10-50 rows);
    # flagged in the handoff doc as an N+1-query pattern worth caching if
    # queue pages grow large.
    score = None
    confidence = None
    risk_level = None
    assessment_computed = False
    if app_row.status != ApplicationStatus.draft:
        txn_rows = _load_transaction_rows(db, app_row.id)
        if txn_rows:
            revenue = estimate_revenue(txn_rows)
            document_types_present = {r.source_type for r in txn_rows}
            result = scoring.compute_score(
                revenue=revenue,
                document_types_present=document_types_present,
                cnic_digits=app_row.cnic_number,
                consistency_pass_count=0,
                consistency_total=0,
                amount_pkr=Decimal(app_row.amount_pkr),
                tenor_months=app_row.tenor_months or 0,
                years_operating=app_row.years_operating,
            )
            # `compute_score` always returns either a ScoreResult or an
            # InsufficientEvidence result -- either way, "the assessment
            # engine ran and produced a real determination" is true, which
            # is exactly what workflow_stage_service.derive_stage's
            # `assessment_computed` flag means (see its docstring: the
            # insufficient-evidence state is itself a completed
            # determination, not "not done yet").
            assessment_computed = True
            if isinstance(result, scoring.ScoreResult):
                score, confidence, risk_level = result.score_0_1000, result.confidence_0_100, result.risk_level

    # Dashboard workflow redesign / Evidence Checklist stage badge --
    # reuses the same checklist assembly the Evidence page itself uses
    # (see evidence_checklist_service.py), so the two surfaces can never
    # disagree about e.g. "is identity verified".
    checklist = evidence_checklist_service.build_checklist(db, applicant=app_row.applicant, application_id=app_row.id)
    stage = workflow_stage_service.derive_stage(
        application_status=app_row.status, checklist=checklist, assessment_computed=assessment_computed
    )

    return ApplicationListItemOut(
        id=app_row.id,
        display_id=app_row.display_id,
        business_name=app_row.business_name,
        city=app_row.city,
        amount_pkr=app_row.amount_pkr,
        purpose=app_row.purpose,
        status=app_row.status,
        workflow_stage=stage.key,
        workflow_stage_label=stage.label,
        score=score,
        confidence=confidence,
        risk_level=risk_level,
        documents_count=documents_count,
        officer_name=app_row.officer.name if app_row.officer else None,
        applicant_name=app_row.applicant.name if app_row.applicant else "",
        created_at=app_row.created_at,
        updated_at=app_row.updated_at,
    )


def _to_detail(db: Session, app_row: Application, *, mask_cnic: bool, viewer_is_applicant: bool) -> ApplicationDetailOut:
    list_item = _to_list_item(db, app_row)

    timeline_rows = db.scalars(
        select(ActivityTimeline)
        .where(ActivityTimeline.application_id == app_row.id)
        .order_by(ActivityTimeline.created_at.asc())
    ).all()
    timeline_out = [
        TimelineEntryOut(at=t.created_at, label=t.label, actor_type=t.actor_type.value, actor_name=t.actor_name)
        for t in timeline_rows
    ]

    evidence_out = _evidence_coverage(db, app_row.id)
    checklist = evidence_checklist_service.build_checklist(db, applicant=app_row.applicant, application_id=app_row.id)
    revenue_out, assessment_out, consistency_out = _compute_assessment(
        db, app_row, viewer_is_applicant=viewer_is_applicant, checklist=checklist
    )

    processing_steps = [
        ProcessingStepOut(key=s.key, label=s.label, status=s.status, detail=s.detail)
        for s in workflow_stage_service.build_processing_steps(
            checklist=checklist,
            revenue=revenue_out,
            assessment_computed=assessment_out is not None,
            consistency_checks=consistency_out,
            application_status=app_row.status,
        )
    ]

    # List-item score/confidence/risk_level should agree with the fuller
    # assessment computed here (which includes consistency checks that
    # _to_list_item skips for cheapness) -- overwrite so a single response
    # is internally consistent.
    if isinstance(assessment_out, ScoredAssessmentOut):
        list_item.score = assessment_out.score
        list_item.confidence = assessment_out.confidence
        list_item.risk_level = assessment_out.risk_level
    else:
        list_item.score = None
        list_item.confidence = None
        list_item.risk_level = None

    # _to_list_item's own stage derivation used a cheaper score-only
    # assessment_computed proxy; recompute with the fuller assessment_out
    # here so detail view and list view can't disagree on edge cases
    # where the cheap path under/over-counts.
    stage = workflow_stage_service.derive_stage(
        application_status=app_row.status, checklist=checklist, assessment_computed=assessment_out is not None
    )
    list_item.workflow_stage = stage.key
    list_item.workflow_stage_label = stage.label

    cnic_out: str | None = None
    if app_row.cnic_number:
        cnic_out = _mask_cnic(app_row.cnic_number) if mask_cnic else app_row.cnic_number

    return ApplicationDetailOut(
        **list_item.model_dump(),
        business_type=app_row.business_type,
        owner_name=app_row.owner_name,
        years_operating=app_row.years_operating,
        employee_count=app_row.employee_count,
        tenor_months=app_row.tenor_months,
        preferred_repayment=app_row.preferred_repayment,
        registration_status=app_row.registration_status,
        ntn=app_row.ntn,
        strn=app_row.strn,
        monthly_estimated_revenue_pkr=app_row.monthly_estimated_revenue_pkr,
        monthly_estimated_expenses_pkr=app_row.monthly_estimated_expenses_pkr,
        cnic_number=cnic_out,
        evidence=evidence_out,
        timeline=timeline_out,
        revenue=revenue_out,
        assessment=assessment_out,
        consistency_checks=consistency_out,
        processing_steps=processing_steps,
        evidence_completion_pct=checklist.overall_completion_pct,
    )


# ---------------------------------------------------------------------------
# Section 10 (Loan Officer Review Page): thin org-scope-checked wrappers
# around officer_review_service, so app/api/v1/officer.py never has to
# reach into another service module's internals to enforce
# "this document belongs to an application in my org" -- same shape as
# every other officer.py route, which all go through this module.
# ---------------------------------------------------------------------------


def list_officer_documents(db: Session, officer: User, application_id: uuid.UUID):
    app_row = get_org_scoped_application(db, officer, application_id)
    return officer_review_service.list_officer_documents(db, app_row)


def add_officer_note(db: Session, officer: User, application_id: uuid.UUID, document_id: uuid.UUID | None, body: str):
    app_row = get_org_scoped_application(db, officer, application_id)
    return officer_review_service.create_officer_note(
        db, officer=officer, application=app_row, document_id=document_id, body=body
    )


def review_document(db: Session, officer: User, document_id: uuid.UUID, action: str, note: str | None):
    document = db.get(Document, document_id)
    if document is None:
        from app.core.exceptions import DocumentNotFoundError

        raise DocumentNotFoundError()
    app_row = get_org_scoped_application(db, officer, document.application_id)
    return officer_review_service.review_document(
        db, officer=officer, application=app_row, document_id=document_id, action=action, note=note
    )


def get_officer_evidence_checklist(db: Session, officer: User, application_id: uuid.UUID):
    """Section 10's Evidence Summary -- same per-category tiering/status
    vocabulary as the applicant's own Evidence page (see
    evidence_checklist_service.build_checklist_for_officer), not a
    re-derived raw-percentage view."""
    app_row = get_org_scoped_application(db, officer, application_id)
    checklist = evidence_checklist_service.build_checklist_for_officer(db, app_row)
    return evidence_checklist_service.to_out(db, checklist)
