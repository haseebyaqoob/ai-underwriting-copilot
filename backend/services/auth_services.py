from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import EmailAlreadyRegisteredError, InvalidCredentialsError, InvalidOrExpiredTokenError
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expiry,
)
from app.db.models.enums import Role
from app.db.models.organization import Organization
from app.db.models.enums import OrgType
from app.db.models.refresh_token import RefreshToken
from app.db.models.user import User
from app.schemas.auth import SignupIn, LoginIn, UserOut, AuthResponse


def _to_user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        org=user.organization.name if user.organization else None,
    )


def _issue_tokens(db: Session, user: User, *, device_info: str | None = None) -> tuple[str, str]:
    """Returns (access_token, raw_refresh_token). Caller sets the refresh
    token as an httpOnly cookie; it's never put in a JSON body."""
    access_token = create_access_token(
        user_id=str(user.id), role=user.role.value, org_id=str(user.org_id) if user.org_id else None
    )

    raw_refresh = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=refresh_token_expiry(),
            device_info=device_info,
        )
    )
    db.commit()
    return access_token, raw_refresh


def signup_applicant(db: Session, payload: SignupIn) -> tuple[AuthResponse, str]:
    """New accounts always start as `applicant` — mirrors the frontend's
    `signUpApplicant`, which hardcodes role: 'applicant' today."""
    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing is not None:
        raise EmailAlreadyRegisteredError()

    org = None
    if payload.org:
        org = Organization(name=payload.org, type=OrgType.applicant_business)
        db.add(org)
        db.flush()  # get org.id without a full commit yet

    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        name=payload.name,
        role=Role.applicant,
        org_id=org.id if org else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    access_token, raw_refresh = _issue_tokens(db, user)
    return AuthResponse(access_token=access_token, user=_to_user_out(user)), raw_refresh


def login(db: Session, payload: LoginIn) -> tuple[AuthResponse, str]:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise InvalidCredentialsError()

    access_token, raw_refresh = _issue_tokens(db, user)
    return AuthResponse(access_token=access_token, user=_to_user_out(user)), raw_refresh


def refresh_session(db: Session, raw_refresh_token: str) -> tuple[AuthResponse, str]:
   
    token_hash = hash_refresh_token(raw_refresh_token)
    token_row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))

    if token_row is None or token_row.revoked_at is not None:
        raise InvalidOrExpiredTokenError()

    from datetime import datetime, timezone

    if token_row.expires_at < datetime.now(timezone.utc):
        raise InvalidOrExpiredTokenError()

    user = db.get(User, token_row.user_id)
    if user is None:
        raise InvalidOrExpiredTokenError("Account no longer exists.")

    token_row.revoked_at = datetime.now(timezone.utc)
    db.add(token_row)

    access_token, raw_refresh = _issue_tokens(db, user)
    return AuthResponse(access_token=access_token, user=_to_user_out(user)), raw_refresh


def logout(db: Session, raw_refresh_token: str | None) -> None:
    if not raw_refresh_token:
        return
    token_hash = hash_refresh_token(raw_refresh_token)
    token_row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if token_row is not None and token_row.revoked_at is None:
        from datetime import datetime, timezone

        token_row.revoked_at = datetime.now(timezone.utc)
        db.add(token_row)
        db.commit()


def change_password(db: Session, user: User, *, current_password: str, new_password: str) -> None:
  
    if not verify_password(current_password, user.password_hash):
        raise InvalidCredentialsError()

    user.password_hash = hash_password(new_password)
    db.add(user)

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    other_tokens = db.scalars(
        select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
    ).all()
    for token_row in other_tokens:
        token_row.revoked_at = now
        db.add(token_row)

    db.commit()
