import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1 import auth as auth_routes
from app.api.v1 import applicant as applicant_routes
from app.api.v1 import officer as officer_routes
from app.api.v1 import admin as admin_routes
from app.api.v1 import ws_token as ws_token_routes
from app.api.v1 import notifications as notifications_routes
from app.api import ws_endpoint
from app.ws.bridge import run_bridge

logger = logging.getLogger(__name__)

app = FastAPI(title="Yaqeen API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.FRONTEND_ORIGINS,
    allow_credentials=True,  # required so the httpOnly refresh cookie is sent
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router, prefix="/api/v1")
app.include_router(applicant_routes.router, prefix="/api/v1")
app.include_router(officer_routes.router, prefix="/api/v1")
app.include_router(admin_routes.router, prefix="/api/v1")
app.include_router(ws_token_routes.router, prefix="/api/v1")
app.include_router(notifications_routes.router, prefix="/api/v1")

# Deliberately NOT under /api/v1 - the Module 3 spec's socket path is the
# literal `/ws?token=...`, not `/api/v1/ws`.
app.include_router(ws_endpoint.router)

_bridge_task: asyncio.Task | None = None


@app.on_event("startup")
async def _start_ws_bridge() -> None:
    global _bridge_task
    _bridge_task = asyncio.create_task(run_bridge())
    logger.info("main: WS Redis bridge task started")


@app.on_event("shutdown")
async def _stop_ws_bridge() -> None:
    if _bridge_task is not None:
        _bridge_task.cancel()


@app.get("/health")
def health():
    return {"status": "ok", "env": settings.ENV}
