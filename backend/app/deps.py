import uuid

from fastapi import Depends, Header
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidOrExpiredTokenError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.db.models.user import User

__all__ = ["get_db", "get_current_user"]


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """
    Reads the access token from `Authorization: Bearer <token>`. The access
    token is kept in memory on the frontend (not localStorage) precisely so
    it never has to be read synchronously from a router guard — only from
    an actual fetch, which is what happens here.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise InvalidOrExpiredTokenError("Missing or malformed Authorization header.")

    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise InvalidOrExpiredTokenError()

    user_id = payload.get("sub")
    try:
        user_uuid = uuid.UUID(user_id)
    except (TypeError, ValueError):
        raise InvalidOrExpiredTokenError()

    user = db.get(User, user_uuid)
    if user is None:
        raise InvalidOrExpiredTokenError("Account no longer exists.")
    return user
