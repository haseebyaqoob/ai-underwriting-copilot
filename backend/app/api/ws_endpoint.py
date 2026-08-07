
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError

from app.core.security import decode_ws_token
from app.db.models.application import Application
from app.db.models.enums import Role
from app.db.models.user import User
from app.db.session import SessionLocal
from app.ws.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, token: str, application_id: uuid.UUID | None = None):
    try:
        payload = decode_ws_token(token)
    except JWTError:
        await websocket.close(code=4401)  # custom close code range, mirrors 401
        return

    user_id = payload.get("sub")
    db = SessionLocal()
    try:
        user = db.get(User, uuid.UUID(user_id)) if user_id else None
        if user is None:
            await websocket.close(code=4401)
            return

        channels = [f"user:{user.id}"]

        if user.role in (Role.loan_officer, Role.admin) and user.org_id:
            channels.append(f"org:{user.org_id}:officer_queue")

        if application_id is not None:
            application = db.get(Application, application_id)
            entitled = application is not None and (
                application.applicant_id == user.id
                or (user.role in (Role.loan_officer, Role.admin) and application.lender_org_id == user.org_id)
            )
            if entitled:
                channels.append(f"application:{application_id}")
            else:
                logger.info("ws_endpoint: user %s not entitled to application %s channel, skipping", user.id, application_id)
    finally:
        db.close()

    await websocket.accept()
    for channel in channels:
        await manager.connect(channel, websocket)

    try:
        while True:
            # This socket is push-only from the server's side (events flow
            # server -> client per the Module 3 design); we still need to
            # await something to detect disconnect. Any inbound message is
            # just discarded.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        for channel in channels:
            manager.disconnect(channel, websocket)
