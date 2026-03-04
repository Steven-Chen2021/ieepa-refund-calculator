"""
Security Headers Middleware
============================
Injects all required HTTP security headers on every response
(Security_Spec.md §7.3.2, SEC-009).

Headers injected
----------------
Content-Security-Policy   — XSS / clickjacking prevention
X-Frame-Options           — clickjacking prevention (legacy)
X-Content-Type-Options    — MIME-sniffing prevention
Referrer-Policy           — information leakage prevention
Permissions-Policy        — browser API restriction
Strict-Transport-Security — HTTPS downgrade prevention (HSTS)
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Content-Security-Policy value (Security_Spec.md §7.3.2)
_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "frame-ancestors 'none'"
)

# Relaxed CSP for Swagger / ReDoc docs pages (CDN resources needed)
_CSP_DOCS = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "frame-ancestors 'none'"
)

_DOCS_PATHS = {"/api/docs", "/api/redoc", "/api/openapi.json"}

_HEADERS: dict[str, str] = {
    "Content-Security-Policy": _CSP,
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    # HSTS: 1 year, include subdomains
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Append security headers to every HTTP response.

    Applied as the outermost middleware so headers are present even on
    error responses produced by other middleware layers.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        csp = _CSP_DOCS if request.url.path in _DOCS_PATHS else _CSP
        for header, value in _HEADERS.items():
            response.headers[header] = value
        response.headers["Content-Security-Policy"] = csp
        return response
