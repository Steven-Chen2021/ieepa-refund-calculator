"""
API v1 router
==============
Mounts all endpoint sub-routers under /api/v1.
"""
from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.documents import router as documents_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(documents_router)

__all__ = ["api_router"]
