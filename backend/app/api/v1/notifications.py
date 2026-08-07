"""
Notification inbox -- deliberately one router shared by every role
(applicant, loan_officer, admin) rather than duplicated under
/applicant and /officer, since "list my own notifications" /
"mark mine read" needs nothing role-specific: every query below is
scoped to `current_user.id`, never to a role or org, so there's no
cross-role data-leak risk in sharing the router.
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models.user import User
from app.db.session import get_db
from app.deps import get_current_user
from app.schemas.notification import (
    MarkAllReadOut,
    NotificationListOut,
    NotificationOut,
    NotificationPreferencesOut,
    UnreadCountOut,
)
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListOut)
def list_notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    unread_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total, unread = notification_service.list_notifications(
        db, user_id=current_user.id, unread_only=unread_only, page=page, page_size=page_size
    )
    return NotificationListOut(
        items=[NotificationOut.from_row(row) for row in items],
        total=total,
        unread_count=unread,
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count", response_model=UnreadCountOut)
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return UnreadCountOut(unread_count=notification_service.unread_count(db, user_id=current_user.id))


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = notification_service.mark_read(db, user_id=current_user.id, notification_id=notification_id)
    if row is None:
        raise NotFoundError("Notification not found.")
    return NotificationOut.from_row(row)


@router.post("/read-all", response_model=MarkAllReadOut)
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = notification_service.mark_all_read(db, user_id=current_user.id)
    return MarkAllReadOut(marked_read=count)


@router.get("/preferences", response_model=NotificationPreferencesOut)
def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return NotificationPreferencesOut(
        notifications_enabled=notification_service.get_preferences(db, user_id=current_user.id)
    )


@router.patch("/preferences", response_model=NotificationPreferencesOut)
def update_preferences(
    payload: NotificationPreferencesOut,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enabled = notification_service.set_preferences(
        db, user_id=current_user.id, notifications_enabled=payload.notifications_enabled
    )
    return NotificationPreferencesOut(notifications_enabled=enabled)
