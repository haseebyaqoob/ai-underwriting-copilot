"""
Route-level RBAC. This is the *real* enforcement layer — the frontend's
`requireRole` (reading localStorage in `beforeLoad`) is advisory/UX-only,
so every state-changing or data-scoped route must go through one of these
dependencies regardless of what the client believes the user's role is.
"""
from fastapi import Depends

from app.core.exceptions import ForbiddenRoleError
from app.db.models.enums import Role
from app.db.models.user import User
from app.deps import get_current_user


def require_role(*allowed_roles: Role):
    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise ForbiddenRoleError()
        return current_user

    return _dependency


require_applicant = require_role(Role.applicant)
require_officer = require_role(Role.loan_officer)
require_admin = require_role(Role.admin)
require_officer_or_admin = require_role(Role.loan_officer, Role.admin)
