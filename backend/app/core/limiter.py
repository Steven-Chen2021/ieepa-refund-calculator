"""
slowapi rate limiter singleton.

Uses Redis as the storage backend (same Redis instance as the rest of the app,
but on database 1 to avoid key-space collisions with Celery and the HTS cache).
"""
import logging
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Redis Storage URI ──────────────────────────────────────
# Replace /0 → /1 for rate-limit counters
_redis_uri = settings.REDIS_URL.rsplit("/", 1)[0] + "/1"

# In development, fallback to memory storage if Redis is unavailable
if settings.ENVIRONMENT == "development":
    import socket
    try:
        # Check if Redis is reachable (short timeout)
        host = settings.REDIS_HOST
        port = settings.REDIS_PORT
        with socket.create_connection((host, port), timeout=0.1):
            storage_uri = _redis_uri
    except (ConnectionRefusedError, socket.timeout, socket.gaierror):
        logger.warning("Redis not reachable at %s:%s. Falling back to memory:// for rate limiting.", host, port)
        storage_uri = "memory://"
else:
    storage_uri = _redis_uri

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=storage_uri,
    default_limits=[],   # limits are declared per-route
)
