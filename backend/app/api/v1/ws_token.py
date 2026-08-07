from fastapi import APIRouter, Depends

from app.core.security import create_ws_token
from app.db.models.user import User
from app.deps import get_current_user
from app.schemas.ws import WsTokenOut

router = APIRouter(prefix="/ws", tags=["ws"])


@router.get("/token", response_model=WsTokenOut)
def issue_ws_token(current_user: User = Depends(get_current_user)):
    """
    Short-lived (60s), single-purpose token for opening `/ws?token=...`.
    Authenticated the normal way (Bearer access token) so this endpoint
    itself gets all the usual auth guarantees; what it hands back is
    deliberately narrow-scoped and short-lived — see the docstring in
    app/core/security.py::create_ws_token for why.
    """
    return WsTokenOut(ws_token=create_ws_token(user_id=str(current_user.id)), expires_in_seconds=60)
