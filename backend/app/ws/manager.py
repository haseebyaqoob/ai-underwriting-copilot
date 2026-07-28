"""
In-process WebSocket connection registry — Module 3.

Deliberately dumb: it only knows about sockets connected to *this* FastAPI
process. In a multi-process deployment (this app + Celery workers, or
multiple uvicorn workers), the thing that actually fans an event out to
every relevant socket regardless of which process raised it is the Redis
pub/sub bridge in `app/ws/bridge.py` + `app/ws/events.py`. Nothing outside
`app/ws/` should import this module directly — always go through
`publish_event()` in `events.py`, even from code running in the same
process as this manager, so there's exactly one code path for "emit a WS
event" regardless of where it's called from.
"""
import logging
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._channels: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, channel: str, websocket: WebSocket) -> None:
        self._channels[channel].add(websocket)

    def disconnect(self, channel: str, websocket: WebSocket) -> None:
        self._channels[channel].discard(websocket)
        if not self._channels[channel]:
            self._channels.pop(channel, None)

    async def broadcast(self, channel: str, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._channels.get(channel, ())):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(channel, ws)

    def channel_sizes(self) -> dict[str, int]:
        """Debug/health helper — not used by any endpoint yet."""
        return {ch: len(sockets) for ch, sockets in self._channels.items()}


manager = ConnectionManager()
