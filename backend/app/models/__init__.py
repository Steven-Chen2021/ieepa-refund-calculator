"""
ORM models package.

Import all models here so that Alembic's env.py can discover them via
`Base.metadata` by simply importing this module.
"""
from app.models.audit_log import AuditLog
from app.models.calculation import Calculation, CalculationAudit, CalculationStatus, RefundPathway
from app.models.document import Document, DocumentStatus
from app.models.lead import CrmSyncStatus, Lead
from app.models.tariff_rate import TariffRate, TariffType
from app.models.types import EncryptedString
from app.models.user import User, UserRole

__all__ = [
    # Users
    "User",
    "UserRole",
    # Documents / OCR
    "Document",
    "DocumentStatus",
    # Calculations
    "Calculation",
    "CalculationAudit",
    "CalculationStatus",
    "RefundPathway",
    # Leads (PII encrypted)
    "Lead",
    "CrmSyncStatus",
    # Tariff Rates
    "TariffRate",
    "TariffType",
    # Audit
    "AuditLog",
    # Custom Types
    "EncryptedString",
]
