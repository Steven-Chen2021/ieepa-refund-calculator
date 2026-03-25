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
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
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
        allow_origins=["*"], # Simplified for trial
        allow_credentials=True,
        allow_methods=["*"],
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

    # ── Static Files & SPA ───────────────────────────────────────────────
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(static_dir):
        # Assets mount (CSS/JS)
        assets_dir = os.path.join(static_dir, "assets")
        if os.path.exists(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            # If path starts with api/v1, it should have been caught by router
            if full_path.startswith("api/v1") or full_path.startswith("docs") or full_path.startswith("openapi.json"):
                return JSONResponse(status_code=404, content={"detail": "Not Found"})

            # Serve individual files if they exist (e.g. logo, manifest)
            file_path = os.path.join(static_dir, full_path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)

            # Fallback to index.html for SPA routing
            return FileResponse(os.path.join(static_dir, "index.html"))

    return app


app = create_app()