"""
Notification system (Section 9 of the platform brief). Owns:

  - the copy templates that turn a `NotificationEventType` + context into
    a `(title, body, NotificationType)` triple,
  - writing the `Notification` row,
  - fanning it out over the existing WS event bus (`app/ws/events.py`) so
    an already-open tab updates live, exactly the same mechanism
    `document_service`/`background/tasks.py` already use for
    `document.uploaded`/`document.processed`,
  - read/unread queries used by the API layer.

Every `notify_*` helper below is called from inside the same DB
transaction as the domain event it's about (state transition, upload,
etc.) and does its own `db.flush()` but never `db.commit()` -- same
convention as `state_machine.apply_transition`, so a caller can bundle a
notification write into a larger transaction and have it roll back
together with everything else if something later in that transaction
fails.

Failures publishing to the WS bus are swallowed by `publish_event` itself
(see its own docstring) -- a missed live push is recovered by the
frontend's own polling fallback, so it must never fail the request that
triggered it.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.application import Application
from app.db.models.enums import NotificationEventType as Evt
from app.db.models.enums import NotificationType, Role
from app.db.models.notification import Notification
from app.db.models.user import User
from app.ws.events import publish_event

# ------------------------------------------------------------- templates

# event_type -> (severity, title, body-builder). body-builder receives
# **ctx (arbitrary keyword context passed by the caller) and must not
# raise on missing keys it doesn't itself need -- each builder only reads
# the keys its own event actually uses.
_SEVERITY: dict[Evt, NotificationType] = {
    Evt.application_submitted: NotificationType.info,
    Evt.document_uploaded: NotificationType.info,
    Evt.document_verified: NotificationType.info,
    Evt.additional_evidence_requested: NotificationType.action_required,
    Evt.ai_assessment_started: NotificationType.info,
    Evt.ai_assessment_completed: NotificationType.info,
    Evt.application_approved: NotificationType.decision,
    Evt.application_rejected: NotificationType.decision,
    Evt.officer_comment: NotificationType.info,
    Evt.status_changed: NotificationType.info,
    Evt.new_application_submitted: NotificationType.action_required,
    Evt.applicant_uploaded_new_evidence: NotificationType.info,
    Evt.applicant_updated_existing_evidence: NotificationType.info,
    Evt.applicant_replied_to_request: NotificationType.action_required,
    Evt.application_withdrawn: NotificationType.info,
}


def _title_body(event_type: Evt, **ctx) -> tuple[str, str]:
    display_id = ctx.get("display_id", "your application")
    if event_type == Evt.application_submitted:
        return "Application submitted", f"Your application {display_id} was submitted successfully."
    if event_type == Evt.document_uploaded:
        return "Document uploaded", f"{ctx.get('doc_label', 'A document')} was added to {display_id}."
    if event_type == Evt.document_verified:
        return "Document verified", f"{ctx.get('doc_label', 'Your document')} on {display_id} passed verification."
    if event_type == Evt.additional_evidence_requested:
        extra = ctx.get("note")
        base = f"Your loan officer requested more evidence for {display_id}."
        return "Additional evidence requested", f"{base} {extra}".strip() if extra else base
    if event_type == Evt.ai_assessment_started:
        return "AI assessment started", f"Yaqeen is reviewing the evidence on {display_id}."
    if event_type == Evt.ai_assessment_completed:
        return "AI assessment ready", f"The AI assessment for {display_id} is ready to view."
    if event_type == Evt.application_approved:
        return "Application approved", f"Congratulations — {display_id} has been approved."
    if event_type == Evt.application_rejected:
        note = ctx.get("note")
        base = f"{display_id} was not approved this time."
        return "Application rejected", f"{base} {note}".strip() if note else base
    if event_type == Evt.officer_comment:
        return "New comment from your loan officer", ctx.get("note") or f"Your loan officer left a note on {display_id}."
    if event_type == Evt.status_changed:
        return "Status update", ctx.get("detail") or f"{display_id} status changed to {ctx.get('to_status', 'updated')}."
    if event_type == Evt.new_application_submitted:
        return "New application submitted", f"{ctx.get('business_name', 'A new applicant')} submitted {display_id}."
    if event_type == Evt.applicant_uploaded_new_evidence:
        return "New evidence uploaded", f"{ctx.get('applicant_name', 'The applicant')} uploaded {ctx.get('doc_label', 'a document')} on {display_id}."
    if event_type == Evt.applicant_updated_existing_evidence:
        return "Evidence updated", f"{ctx.get('applicant_name', 'The applicant')} replaced {ctx.get('doc_label', 'a document')} on {display_id}."
    if event_type == Evt.applicant_replied_to_request:
        return "Applicant replied to your request", f"{ctx.get('applicant_name', 'The applicant')} re-submitted {display_id} with the requested evidence."
    if event_type == Evt.application_withdrawn:
        return "Application withdrawn", f"{ctx.get('applicant_name', 'The applicant')} withdrew {display_id}."
    return "Notification", display_id


# --------------------------------------------------------------- writing

def create_notification(
    db: Session,
    *,
    user_id: uuid.UUID,
    event_type: Evt,
    application_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    **ctx,
) -> Notification | None:
    # Profile page's "Notification Preferences" toggle -- an extra query
    # per notification, which is fine at this product's scale (small
    # per-org user counts), same tradeoff evidence_wallet_service makes
    # for `applications_using_count` rather than maintaining a cached
    # counter.
    recipient = db.get(User, user_id)
    if recipient is not None and not recipient.notifications_enabled:
        return None

    title, body = _title_body(event_type, **ctx)
    row = Notification(
        user_id=user_id,
        title=title,
        body=body,
        type=_SEVERITY.get(event_type, NotificationType.info),
        event_type=event_type.value,
        application_id=application_id,
        document_id=document_id,
    )
    db.add(row)
    db.flush()
    publish_event(f"user:{user_id}", {"type": "notification.created", "id": str(row.id)})
    return row


def notify_applicant(
    db: Session, *, application: Application, event_type: Evt, document_id: uuid.UUID | None = None, **ctx
) -> Notification | None:
    return create_notification(
        db,
        user_id=application.applicant_id,
        event_type=event_type,
        application_id=application.id,
        document_id=document_id,
        display_id=application.display_id,
        **ctx,
    )


def notify_officers(
    db: Session, *, application: Application, event_type: Evt, document_id: uuid.UUID | None = None, **ctx
) -> list[Notification]:
    """Notifies the assigned officer if one exists, otherwise every
    loan_officer/admin in the application's lender org (bounded by org
    size -- fine at the org scale this product targets; a very large org
    would want a per-org "who's on the queue" subscription list instead,
    but that doesn't exist yet)."""
    recipients: list[uuid.UUID] = []
    if application.officer_id is not None:
        recipients = [application.officer_id]
    elif application.lender_org_id is not None:
        rows = db.scalars(
            select(User.id).where(
                User.org_id == application.lender_org_id,
                User.role.in_([Role.loan_officer, Role.admin]),
            )
        ).all()
        recipients = list(rows)

    results = [
        create_notification(
            db,
            user_id=uid,
            event_type=event_type,
            application_id=application.id,
            document_id=document_id,
            display_id=application.display_id,
            **ctx,
        )
        for uid in recipients
    ]
    return [r for r in results if r is not None]


# --------------------------------------------------------------- reading

def list_notifications(
    db: Session, *, user_id: uuid.UUID, unread_only: bool = False, page: int = 1, page_size: int = 20
) -> tuple[list[Notification], int, int]:
    """Returns (items, total_count, unread_count)."""
    base = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        base = base.where(Notification.read_at.is_(None))

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    unread = db.scalar(
        select(func.count()).select_from(
            select(Notification.id)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            .subquery()
        )
    ) or 0

    rows = db.scalars(
        base.order_by(Notification.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(rows), total, unread


def unread_count(db: Session, *, user_id: uuid.UUID) -> int:
    return db.scalar(
        select(func.count()).select_from(
            select(Notification.id)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            .subquery()
        )
    ) or 0


def mark_read(db: Session, *, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification | None:
    row = db.get(Notification, notification_id)
    if row is None or row.user_id != user_id:
        return None
    if row.read_at is None:
        row.read_at = datetime.now(timezone.utc)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def mark_all_read(db: Session, *, user_id: uuid.UUID) -> int:
    rows = db.scalars(
        select(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))
    ).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        row.read_at = now
        db.add(row)
    db.commit()
    return len(rows)


# ----------------------------------------------------------- preferences

def get_preferences(db: Session, *, user_id: uuid.UUID) -> bool:
    user = db.get(User, user_id)
    return bool(user.notifications_enabled) if user is not None else True


def set_preferences(db: Session, *, user_id: uuid.UUID, notifications_enabled: bool) -> bool:
    user = db.get(User, user_id)
    if user is None:
        return True
    user.notifications_enabled = notifications_enabled
    db.add(user)
    db.commit()
    return user.notifications_enabled
