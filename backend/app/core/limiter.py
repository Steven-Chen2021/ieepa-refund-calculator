"""
slowapi rate limiter singleton.

Uses Redis as the storage backend (same Redis instance as the rest of the app,
but on database 1 to avoid key-space collisions with Celery and the HTS cache).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Replace /0 → /1 for rate-limit counters
_redis_uri = settings.REDIS_URL.rsplit("/", 1)[0] + "/1"

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_redis_uri,
    default_limits=[],   # limits are declared per-route
)
