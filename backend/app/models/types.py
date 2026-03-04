"""
Custom SQLAlchemy TypeDecorators for the IEEPA Refund Calculator.

EncryptedString — transparently encrypts/decrypts string values using
Fernet (AES-256-GCM) before writing to / reading from the database.
The ciphertext is stored as TEXT (base64url encoded by Fernet).

Key is loaded once at import time from FERNET_KEY_PATH.
If the key file does not exist (fresh dev environment before init_keys.py
is run), the type will store plaintext and emit a warning — do NOT use
this fallback in production.
"""
from __future__ import annotations

import logging
import warnings
from typing import Any

from sqlalchemy import String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

logger = logging.getLogger(__name__)

# ── Lazy-load Fernet key ─────────────────────────────────────────────────────
_fernet: Any = None  # cryptography.fernet.Fernet instance or None


def _get_fernet() -> Any:
    global _fernet
    if _fernet is not None:
        return _fernet

    try:
        from cryptography.fernet import Fernet

        from app.core.config import settings

        key_path = settings.FERNET_KEY_PATH
        with open(key_path, "rb") as fh:
            key = fh.read().strip()
        _fernet = Fernet(key)
        logger.debug("Fernet key loaded from %s", key_path)
    except FileNotFoundError:
        warnings.warn(
            "Fernet key file not found — PII fields will be stored as PLAINTEXT. "
            "Run `python init_keys.py` before handling real data.",
            stacklevel=2,
        )
        _fernet = None
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to load Fernet key: %s", exc)
        _fernet = None

    return _fernet


# ── TypeDecorator ────────────────────────────────────────────────────────────


class EncryptedString(TypeDecorator):
    """
    Stores a Python str as an AES-256-GCM (Fernet) encrypted TEXT column.

    Example usage in a model::

        from app.models.types import EncryptedString

        email_encrypted: Mapped[str] = mapped_column(EncryptedString, nullable=False)

    The application always reads/writes plain Python strings; encryption and
    decryption happen automatically at the SQLAlchemy bind / result level.
    """

    impl = String
    cache_ok = True  # safe to cache — no per-instance state

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        """Encrypt on write (Python → DB)."""
        if value is None:
            return None
        fernet = _get_fernet()
        if fernet is None:
            return value  # plaintext fallback (dev only, key not yet generated)
        return fernet.encrypt(value.encode()).decode()

    def process_result_value(self, value: str | None, dialect: Dialect) -> str | None:
        """Decrypt on read (DB → Python)."""
        if value is None:
            return None
        fernet = _get_fernet()
        if fernet is None:
            return value  # plaintext fallback
        try:
            return fernet.decrypt(value.encode()).decode()
        except Exception:
            # Token is not encrypted (e.g., legacy plaintext row) — return as-is
            logger.warning("EncryptedString: failed to decrypt value, returning raw.")
            return value
