
import asyncio
import json
import logging

import redis.asyncio as aredis

from app.config import settings
from app.ws.events import BROADCAST_CHANNEL
from app.ws.manager import manager

logger = logging.getLogger(__name__)


async def run_bridge() -> None:
    """Reconnects with backoff if Redis is briefly unavailable — this task
    is meant to run for the lifetime of the process."""
    backoff = 1
    while True:
        try:
            client = aredis.Redis.from_url(settings.REDIS_URL)
            pubsub = client.pubsub()
            await pubsub.subscribe(BROADCAST_CHANNEL)
            logger.info("ws bridge: subscribed to %s", BROADCAST_CHANNEL)
            backoff = 1
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    payload = json.loads(message["data"])
                    await manager.broadcast(payload["channel"], payload["event"])
                except Exception:
                    logger.exception("ws bridge: failed to process message: %r", message)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ws bridge: connection lost, retrying in %ss", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
