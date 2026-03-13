"""
conftest.py for unit tests.

Stubs out modules that have side effects at import time (asyncpg, DB engine
creation) so the pure calculation and OCR helpers can be imported and tested
without a running database or Redis.
"""
import sys
import types
from unittest.mock import MagicMock, AsyncMock


def _stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# ── asyncpg (requires a live Postgres driver) ────────────────────────────────
_stub("asyncpg")

# ── python-magic (requires libmagic C library) ───────────────────────────────
magic_stub = _stub("magic")
magic_stub.from_buffer = MagicMock(return_value="application/pdf")

# ── google-cloud-documentai (requires GCP credentials) ───────────────────────
_stub("google")
_stub("google.cloud")
_stub("google.cloud.documentai_v1")

# ── pdf2image / pytesseract / pdfplumber / weasyprint ────────────────────────
_stub("pdf2image")
_stub("pytesseract")
_stub("pdfplumber")
_stub("weasyprint")

# ── cryptography (Fernet) — provide a minimal shim ───────────────────────────
try:
    import cryptography  # noqa: F401 — use real lib if available
except ImportError:
    _stub("cryptography")
    _stub("cryptography.fernet")

# ── Stub app.db.session so SQLAlchemy never dials out ────────────────────────
# Must be done BEFORE any app module imports app.db.session.
db_session_stub = _stub("app.db.session")
db_session_stub.AsyncSessionLocal = MagicMock()
db_session_stub.engine = MagicMock()

async def _fake_get_db():
    yield MagicMock()

db_session_stub.get_db = _fake_get_db
