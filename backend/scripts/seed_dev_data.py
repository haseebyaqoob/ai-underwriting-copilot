
from sqlalchemy import select

from app.core.security import hash_password
from app.db.models.enums import OrgType, Role
from app.db.models.organization import Organization
from app.db.models.user import User
from app.db.session import SessionLocal

DEMO_PASSWORD = "demo1234"


def _get_or_create_org(db, name: str, org_type: OrgType) -> Organization:
    org = db.scalar(select(Organization).where(Organization.name == name, Organization.type == org_type))
    if org:
        return org
    org = Organization(name=name, type=org_type)
    db.add(org)
    db.flush()
    return org


def _get_or_create_user(db, *, email: str, name: str, role: Role, org: Organization) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user:
        return user
    user = User(email=email, password_hash=hash_password(DEMO_PASSWORD), name=name, role=role, org_id=org.id)
    db.add(user)
    db.flush()
    return user


def main() -> None:
    db = SessionLocal()
    try:
        # Same org that application_service.get_or_create_default_lender_org
        # will find/use — matching by type=lender, MVP single-lender
        # assumption. Name matches the frontend's Bank Alfa demo org.
        lender_org = _get_or_create_org(db, "Bank Alfa", OrgType.lender)
        ops_org = _get_or_create_org(db, "Yaqeen Platform Ops", OrgType.lender)

        officer = _get_or_create_user(
            db, email="fatima.officer@bankalfa.pk", name="Fatima Sheikh", role=Role.loan_officer, org=lender_org
        )
        admin = _get_or_create_user(
            db, email="admin@yaqeen.pk", name="Yusuf Malik", role=Role.admin, org=ops_org
        )

        db.commit()
        print(f"Seeded lender org: {lender_org.id} ({lender_org.name})")
        print(f"Seeded officer: {officer.email} / password: {DEMO_PASSWORD} (org={lender_org.name})")
        print(f"Seeded admin:   {admin.email} / password: {DEMO_PASSWORD} (org={ops_org.name})")
        print(
            "\nNote: admin is seeded under a separate org from the lender so "
            "admin_dashboard's org-scoping is exercised distinctly from "
            "officer_dashboard's. If you want the admin looking at the same "
            "portfolio the officer works, re-seed with org=lender_org instead."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
