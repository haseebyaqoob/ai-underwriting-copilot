import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models.enums import NotificationType


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    body: str
    type: NotificationType
    event_type: str | None
    application_id: uuid.UUID | None
    document_id: uuid.UUID | None
    read: bool
    created_at: datetime

    @classmethod
    def from_row(cls, row) -> "NotificationOut":
        return cls(
            id=row.id,
            title=row.title,
            body=row.body,
            type=row.type,
            event_type=row.event_type,
            application_id=row.application_id,
            document_id=row.document_id,
            read=row.read_at is not None,
            created_at=row.created_at,
        )


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    total: int
    unread_count: int
    page: int
    page_size: int


class UnreadCountOut(BaseModel):
    unread_count: int


class MarkAllReadOut(BaseModel):
    marked_read: int


class NotificationPreferencesOut(BaseModel):
    notifications_enabled: bool
