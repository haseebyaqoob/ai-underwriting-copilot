"""
Publish side of the WS event bus. Safe to call from ANY process — the
FastAPI app (sync request-handling code) or a Celery worker (a completely
separate OS process with no access to this app's in-memory
`ConnectionManager`). Both just write to Redis; only the FastAPI process's
`bridge.py` subscriber loop actually holds live WebSocket connections and
fans messages out to them.

Event payloads are deliberately minimal (`{type, id}` plus whatever else
is cheap to include) per the architecture decision recorded in
docs/ARCHITECTURE_AND_PROGRESS.md: the frontend invalidates and refetches
rather than trusting a full duplicated payload pushed over the socket, so
there's exactly one serialization path (the REST responses) instead of
two that can drift out of sync.
"""
import json
import logging

import redis

from app.config import settings

logger = logging.getLogger(__name__)

BROADCAST_CHANNEL = "yaqeen:ws:broadcast"

_redis_client: redis.Redis | None = None


def _client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(settings.REDIS_URL)
    return _redis_client


def publish_event(target_channel: str, event: dict) -> None:
    """
    `target_channel` is one of the channel-membership kinds from the
    Module 3 spec: `user:{user_id}`, `application:{application_id}`, or
    `org:{org_id}:officer_queue`. `event` should be the minimal
    `{"type": "document.uploaded", "id": "..."}` shape.

    Failures here are logged, not raised — a WS notification failing to
    fire must never fail the upload/extraction request that triggered it;
    the REST response is the source of truth and a missed WS push is
    recovered by the frontend's next poll/refetch regardless.
    """
    try:
        _client().publish(BROADCAST_CHANNEL, json.dumps({"channel": target_channel, "event": event}))
    except Exception:
        logger.exception("publish_event: failed to publish to Redis (channel=%s, event=%s)", target_channel, event)
