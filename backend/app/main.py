"""
FastAPI Application Factory
============================
Creates and configures the FastAPI application with:

- CORS middleware (settings.CORS_ORIGINS)
- Security headers middleware (CSP, HSTS, X-Frame-Options, …)
- slowapi rate-limit integration (state + exception handler)
- Lifespan context manager (startup / shutdown hooks)
- All API v1 routers
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.limiter import limiter
from app.middleware.security_headers import SecurityHeadersMiddleware

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan: startup & shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle hooks."""
    logger.info("Starting IEEPA Refund Calculator API (env=%s)", settings.ENVIRONMENT)
    yield
    logger.info("Shutting down IEEPA Refund Calculator API")


# ---------------------------------------------------------------------------
# Rate-limit error handler
# ---------------------------------------------------------------------------

async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": str(exc),
            },
            "meta": None,
        },
    )


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="IEEPA Tariff Refund Calculator API",
        description="Internal tool for Dimerco Express Group.",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # ── Middleware (registered in LIFO order — outermost first) ──────────

    # 1. Security headers — outermost so headers appear even on error responses
    app.add_middleware(SecurityHeadersMiddleware)

    # 2. CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # ── slowapi ───────────────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

    # ── Routers ───────────────────────────────────────────────────────────
    app.include_router(api_router)

    # ── Health check ─────────────────────────────────────────────────────
    @app.get("/health", include_in_schema=False)
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()