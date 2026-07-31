"""
Formalizes the application state machine per the architecture spec:

    DRAFT -> SUBMITTED (applicant, explicit action)
    SUBMITTED -> IN_REVIEW (officer opens it / starts review)
    IN_REVIEW -> NEEDS_DOCS | APPROVED | REJECTED (officer, requires reason)
    NEEDS_DOCS -> SUBMITTED (applicant re-submits) | WITHDRAWN
    APPROVED/REJECTED -> terminal (reopen requires explicit logged action back to IN_REVIEW)
    DRAFT/SUBMITTED/NEEDS_DOCS -> WITHDRAWN (applicant)

Every transition writes exactly one `AuditLog` row (append-only, per
architecture spec) and one `ActivityTimeline` row (existing UI-facing
timeline). This module owns *only* the transition/validation logic and
the audit/timeline writes for it -- it does not compute scores or
revenue; `application_service.py` orchestrates calling this plus the
scoring/revenue modules together inside one DB transaction.
"""
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationStateError
from app.db.models.application import Application
from app.db.models.audit import ActivityTimeline, AuditLog
from app.db.models.enums import ActorType, ApplicationStatus, DecisionReasonCode, NotificationEventType, Role
from app.db.models.user import User

S = ApplicationStatus


@dataclass(frozen=True)
class TransitionRule:
    allowed_actor_roles: frozenset[Role]
    requires_reason: bool = False
    is_applicant_initiated: bool = False


# (from_status, to_status) -> rule. Only pairs listed here are legal;
# anything else raises ApplicationStateError.
TRANSITIONS: dict[tuple[ApplicationStatus, ApplicationStatus], TransitionRule] = {
    (S.draft, S.submitted): TransitionRule(frozenset({Role.applicant}), is_applicant_initiated=True),
    (S.draft, S.withdrawn): TransitionRule(frozenset({Role.applicant}), is_applicant_initiated=True),
    (S.submitted, S.in_review): TransitionRule(frozenset({Role.loan_officer, Role.admin})),
    (S.submitted, S.withdrawn): TransitionRule(frozenset({Role.applicant}), is_applicant_initiated=True),
    (S.in_review, S.needs_docs): TransitionRule(frozenset({Role.loan_officer, Role.admin}), requires_reason=True),
    (S.in_review, S.approved): TransitionRule(frozenset({Role.loan_officer, Role.admin}), requires_reason=True),
    (S.in_review, S.rejected): TransitionRule(frozenset({Role.loan_officer, Role.admin}), requires_reason=True),
    (S.needs_docs, S.submitted): TransitionRule(frozenset({Role.applicant}), is_applicant_initiated=True),
    (S.needs_docs, S.withdrawn): TransitionRule(frozenset({Role.applicant}), is_applicant_initiated=True),
    (S.approved, S.in_review): TransitionRule(frozenset({Role.loan_officer, Role.admin}), requires_reason=True),
    (S.rejected, S.in_review): TransitionRule(frozenset({Role.loan_officer, Role.admin}), requires_reason=True),
}

# Statuses in which an applicant may still ADD documents (never edit/
# delete an existing one -- that rule is enforced in document_service.py,
# not here, since it's a per-upload check rather than a status
# transition). APPROVED/REJECTED/WITHDRAWN are fully frozen.
DOCUMENT_UPLOAD_ALLOWED_STATUSES = frozenset({S.draft, S.submitted, S.in_review, S.needs_docs})

# Statuses in which application *metadata* (business/loan fields) could be
# edited by the applicant if an edit endpoint existed. No such endpoint
# exists yet (Module 2 never built one, and it's out of this session's
# scope to add) -- this constant exists so that endpoint, whenever it's
# built, has one obvious place to enforce this rule against rather than
# reinventing it.
METADATA_EDIT_ALLOWED_STATUSES = frozenset({S.draft})


def assert_transition_allowed(
    *, from_status: ApplicationStatus, to_status: ApplicationStatus, actor: User, reason_code: DecisionReasonCode | None
) -> TransitionRule:
    rule = TRANSITIONS.get((from_status, to_status))
    if rule is None:
        raise ApplicationStateError(
            f"Cannot transition application from {from_status.value} to {to_status.value}."
        )
    if actor.role not in rule.allowed_actor_roles:
        raise ApplicationStateError(
            f"Role {actor.role.value} may not perform the {from_status.value} -> {to_status.value} transition."
        )
    if rule.requires_reason and reason_code is None:
        raise ApplicationStateError(
            f"A reason code is required to transition from {from_status.value} to {to_status.value}."
        )
    return rule


def assert_document_upload_allowed(application: Application) -> None:
    if application.status not in DOCUMENT_UPLOAD_ALLOWED_STATUSES:
        raise ApplicationStateError(
            f"Documents cannot be added to an application in status {application.status.value}. "
            f"Reopen it first if this was decided in error."
        )


# (from_status, to_status) -> ("applicant" | "officers", NotificationEventType).
# Drives Section 9's "Status Changes" + the specific applicant/officer
# event types from the brief. Deliberately keyed off the same transition
# pairs as _TIMELINE_LABELS (one source of truth for "what happened" copy)
# rather than a parallel status-watching mechanism -- a transition not
# listed here simply sends no notification (e.g. none needed beyond the
# timeline entry itself).
_NOTIFY_RULES: dict[tuple[ApplicationStatus, ApplicationStatus], list[tuple[str, "NotificationEventType"]]] = {
    (S.draft, S.submitted): [
        ("applicant", NotificationEventType.application_submitted),
        ("officers", NotificationEventType.new_application_submitted),
    ],
    (S.draft, S.withdrawn): [("officers", NotificationEventType.application_withdrawn)],
    (S.submitted, S.in_review): [("applicant", NotificationEventType.status_changed)],
    (S.submitted, S.withdrawn): [("officers", NotificationEventType.application_withdrawn)],
    (S.in_review, S.needs_docs): [("applicant", NotificationEventType.additional_evidence_requested)],
    (S.in_review, S.approved): [("applicant", NotificationEventType.application_approved)],
    (S.in_review, S.rejected): [("applicant", NotificationEventType.application_rejected)],
    (S.needs_docs, S.submitted): [
        ("applicant", NotificationEventType.application_submitted),
        ("officers", NotificationEventType.applicant_replied_to_request),
    ],
    (S.needs_docs, S.withdrawn): [("officers", NotificationEventType.application_withdrawn)],
    (S.approved, S.in_review): [("applicant", NotificationEventType.status_changed)],
    (S.rejected, S.in_review): [("applicant", NotificationEventType.status_changed)],
}


def _dispatch_transition_notifications(
    db: Session,
    *,
    application: Application,
    from_status: ApplicationStatus,
    to_status: ApplicationStatus,
    actor: User,
    note: str | None,
    label: str,
) -> None:
    """Best-effort -- a notification failing to write must never break the
    state transition itself (same failure posture as the WS event bus:
    the transition/audit/timeline rows are the source of truth)."""
    rules = _NOTIFY_RULES.get((from_status, to_status))
    if not rules:
        return
    from app.services import notification_service  # local import: avoids any future import-cycle risk

    ctx = {
        "note": note,
        "detail": label,
        "to_status": to_status.value,
        "applicant_name": actor.name if actor.role == Role.applicant else None,
        "business_name": application.business_name,
    }
    for target, event_type in rules:
        try:
            if target == "applicant":
                notification_service.notify_applicant(db, application=application, event_type=event_type, **ctx)
            else:
                notification_service.notify_officers(db, application=application, event_type=event_type, **ctx)
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "state_machine: failed to dispatch %s notification for %s -> %s on application %s",
                target, from_status.value, to_status.value, application.id,
            )


_TIMELINE_LABELS: dict[tuple[ApplicationStatus, ApplicationStatus], str] = {
    (S.draft, S.submitted): "Application submitted",
    (S.draft, S.withdrawn): "Application withdrawn",
    (S.submitted, S.in_review): "Officer started review",
    (S.submitted, S.withdrawn): "Application withdrawn",
    (S.in_review, S.needs_docs): "Officer requested more documents",
    (S.in_review, S.approved): "Application approved",
    (S.in_review, S.rejected): "Application rejected",
    (S.needs_docs, S.submitted): "Applicant re-submitted application",
    (S.needs_docs, S.withdrawn): "Application withdrawn",
    (S.approved, S.in_review): "Decision reopened for review",
    (S.rejected, S.in_review): "Decision reopened for review",
}


def apply_transition(
    db: Session,
    *,
    application: Application,
    to_status: ApplicationStatus,
    actor: User,
    reason_code: DecisionReasonCode | None = None,
    note: str | None = None,
    score_snapshot: dict | None = None,
) -> Application:
    """Validates, applies, and logs one state transition. Caller is
    responsible for `db.commit()` (kept out of this function so
    application_service can bundle e.g. a decision's score recomputation
    into the same transaction)."""
    from_status = application.status
    assert_transition_allowed(from_status=from_status, to_status=to_status, actor=actor, reason_code=reason_code)

    application.status = to_status
    db.add(application)

    label = _TIMELINE_LABELS.get((from_status, to_status), f"Status changed to {to_status.value}")
    actor_type = ActorType.applicant if actor.role == Role.applicant else ActorType.officer
    db.add(
        ActivityTimeline(
            application_id=application.id,
            label=label,
            actor_type=actor_type,
            actor_name=actor.name,
        )
    )

    metadata: dict = {
        "from_status": from_status.value,
        "to_status": to_status.value,
        "reason_code": reason_code.value if reason_code else None,
        "note": note,
    }
    if score_snapshot is not None:
        metadata["score_snapshot"] = score_snapshot

    db.add(
        AuditLog(
            actor_user_id=actor.id,
            action=f"application_transition:{from_status.value}->{to_status.value}",
            target_type="application",
            target_id=str(application.id),
            extra_metadata=metadata,
        )
    )
    db.flush()

    _dispatch_transition_notifications(
        db, application=application, from_status=from_status, to_status=to_status, actor=actor, note=note, label=label,
    )

    return application


def log_score_computation(db: Session, *, application_id: uuid.UUID, score_snapshot: dict) -> None:
    """Every score computation gets its own audit row (not just decision
    transitions), per the architecture spec's "every score computation
    (with full factor breakdown)" requirement -- this fires on every
    application-detail read where a score/insufficient-evidence result is
    computed, not just at decision time."""
    db.add(
        AuditLog(
            actor_user_id=None,  # system-computed, not tied to whoever happened to be viewing
            action="score_computed",
            target_type="application",
            target_id=str(application_id),
            extra_metadata=score_snapshot,
        )
    )
    db.flush()
