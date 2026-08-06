
from celery import Celery

from app.config import settings

celery_app = Celery(
    "yaqeen",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Module 9 (hardening) is where real retry/backoff policy on
    # extraction tasks lands ("3 attempts, exponential backoff, then mark
    # failed and prompt re-upload"). Not implemented here — this session
    # stops at "the plumbing works end-to-end".
)

# Import side effect: registers the task(s) defined in tasks.py with this
# Celery app instance. Needed so `celery -A app.background.celery_app
# worker` finds them.
from app.background import tasks  # noqa: E402,F401
