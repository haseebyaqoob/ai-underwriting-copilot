from fastapi import APIRouter, Depends, Response, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.core.exceptions import InvalidOrExpiredTokenError
from app.db.session import get_db
from app.deps import get_current_user
from app.db.models.user import User
from app.schemas.auth import ChangePasswordIn, SignupIn, LoginIn, AuthResponse, UserOut, ForgotPasswordIn, OtpVerifyIn
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_KWARGS = dict(
    httponly=True,
    secure=settings.ENV != "development",  # allow http on localhost during dev
    samesite="lax",
    path="/api/v1/auth",  # refresh cookie only ever needs to be sent to auth routes
)


def _set_refresh_cookie(response: Response, raw_refresh_token: str) -> None:
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=raw_refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        **_COOKIE_KWARGS,
    )


@router.post("/signup", response_model=AuthResponse, status_code=201)
def signup(payload: SignupIn, response: Response, db: Session = Depends(get_db)):
    auth_response, raw_refresh = auth_service.signup_applicant(db, payload)
    _set_refresh_cookie(response, raw_refresh)
    return auth_response


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    auth_response, raw_refresh = auth_service.login(db, payload)
    _set_refresh_cookie(response, raw_refresh)
    return auth_response


@router.post("/refresh", response_model=AuthResponse)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    raw_refresh = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not raw_refresh:
        raise InvalidOrExpiredTokenError("No active session.")
    auth_response, new_raw_refresh = auth_service.refresh_session(db, raw_refresh)
    _set_refresh_cookie(response, new_raw_refresh)
    return auth_response


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw_refresh = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    auth_service.logout(db, raw_refresh)
    response.delete_cookie(key=settings.REFRESH_COOKIE_NAME, path=_COOKIE_KWARGS["path"])
    return None


@router.post("/forgot-password", status_code=202)
def forgot_password(payload: ForgotPasswordIn, db: Session = Depends(get_db)):
    """
    Stub for Module 1: always returns 202 regardless of whether the email
    exists, to avoid leaking which emails are registered. Real email
    delivery (token generation + SMTP/SES send) lands in a later module
    alongside the notification service.
    """
    return {"detail": "If that email is registered, a recovery link has been sent."}


@router.post("/otp/verify", status_code=200)
def verify_otp(payload: OtpVerifyIn, db: Session = Depends(get_db)):
    """Stub for Module 1 — OTP issuance/verification wiring comes with the
    real notification/SMS provider in a later module."""
    raise InvalidOrExpiredTokenError("OTP verification isn't wired up yet.")


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    org_name = current_user.organization.name if current_user.organization else None
    return UserOut(
        id=current_user.id, email=current_user.email, name=current_user.name,
        role=current_user.role, org=org_name,
    )


@router.post("/change-password", status_code=204)
def change_password(
    payload: ChangePasswordIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Profile page's "Change Password" section (Section 8 merge)."""
    auth_service.change_password(
        db, current_user, current_password=payload.current_password, new_password=payload.new_password
    )
    return None
