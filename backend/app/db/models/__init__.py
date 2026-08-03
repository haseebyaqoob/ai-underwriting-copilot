"""
Import every model module here. Alembic's env.py does
`from app.db import models` purely for this side effect, so every table
is registered on `Base.metadata` before `--autogenerate` diffs the schema.
Forgetting to add a new model here is the #1 cause of "alembic revision
--autogenerate generates an empty migration" bugs, so keep this list
exhaustive.
"""
from app.db.models.organization import Organization
from app.db.models.user import User
from app.db.models.refresh_token import RefreshToken
from app.db.models.application import Application
from app.db.models.document import Document, DocumentVersion
from app.db.models.extracted_field import ExtractedField
from app.db.models.risk import RiskScore, AIReport
from app.db.models.notification import Notification
from app.db.models.audit import AuditLog, ActivityTimeline
from app.db.models.ai_model_usage import AIModelUsage
from app.db.models.evidence_transaction import EvidenceTransaction
from app.db.models.evidence_wallet import EvidenceWalletItem
from app.db.models.officer_review import OfficerNote, DocumentRequest, DocumentReview

__all__ = [
    "Organization",
    "User",
    "RefreshToken",
    "Application",
    "Document",
    "DocumentVersion",
    "ExtractedField",
    "RiskScore",
    "AIReport",
    "Notification",
    "AuditLog",
    "ActivityTimeline",
    "AIModelUsage",
    "EvidenceTransaction",
    "EvidenceWalletItem",
    "OfficerNote",
    "DocumentRequest",
    "DocumentReview",
]
