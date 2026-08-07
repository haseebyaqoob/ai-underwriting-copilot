from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.rbac import require_admin
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.application import AdminDashboardOut
from app.services import application_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard", response_model=AdminDashboardOut)
def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return application_service.admin_dashboard(db, current_user)
