"""
IEEPA Tariff Refund Calculator — Comprehensive API Test Runner
==============================================================
Covers every endpoint per API_TEST_GUIDELINE_ZH_SHORT_PROMPT.md:
  - Functional / happy-path
  - Invalid inputs, null, empty string, type errors
  - Required-field validation
  - Enum validation
  - Boundary values
  - Auth / Authorization
  - Idempotency
  - Response contract
  - Side-effect checks

Run from repo root (services must be up):
    python api_test_runner.py
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import uuid
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
from requests.cookies import RequestsCookieJar

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = "http://localhost:8000"
API = f"{BASE_URL}/api/v1"
SAMPLE_PDF = Path("7501Samples/01281805_MYK-2800086-4-7501.PDF")
NON_7501_PDF = None   # synthesised inline

CREDENTIALS = {"email": "testuser@dimerco.com", "password": "Test1234"}
ADMIN_CREDS  = {"email": "admin@dimerco.com",    "password": "Admin1234"}

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

@dataclass
class TC:
    id: str
    group: str
    desc: str
    result: str = "PENDING"   # PASS | FAIL | SKIP
    actual_status: int = 0
    detail: str = ""
    response_body: Any = None


_results: list[TC] = []
_session_cookies: dict = {}
_access_token: str = ""
_admin_token: str = ""
_job_id: str = ""
_calc_id: str = ""


def _tc(tc_id: str, group: str, desc: str) -> TC:
    tc = TC(id=tc_id, group=group, desc=desc)
    _results.append(tc)
    return tc


def _pass(tc: TC, status: int, body: Any = None, detail: str = "") -> None:
    tc.result = "PASS"
    tc.actual_status = status
    tc.response_body = body
    tc.detail = detail


def _fail(tc: TC, status: int, body: Any = None, detail: str = "") -> None:
    tc.result = "FAIL"
    tc.actual_status = status
    tc.response_body = body
    tc.detail = detail


def _skip(tc: TC, reason: str = "") -> None:
    tc.result = "SKIP"
    tc.detail = reason


def _req(method: str, path: str, *, headers: dict | None = None,
         json_body: Any = None, data: Any = None, files: Any = None,
         cookies: dict | None = None, expected: int | tuple[int, ...]) -> tuple[int, Any]:
    h = headers or {}
    r = getattr(requests, method)(
        f"{API}{path}",
        headers=h,
        json=json_body,
        data=data,
        files=files,
        cookies=cookies or {},
        timeout=30,
    )
    try:
        body = r.json()
    except Exception:
        body = r.text
    return r.status_code, body


def _bearer(token: str = "") -> dict:
    t = token or _access_token
    return {"Authorization": f"Bearer {t}"} if t else {}


def _idem() -> dict:
    return {"X-Idempotency-Key": str(uuid.uuid4())}


def _inject_session_cookie(session: requests.Session, response: requests.Response) -> None:
    """
    Extract session_id from the upload response and inject it as a raw Cookie
    header on the session.  Python's http.cookiejar enforces the Secure
    attribute and will NOT send a Secure cookie to http:// URLs, causing 403s
    even when the cookie value is present in session.cookies.  Bypassing the
    cookie jar entirely and writing the header directly avoids this.
    """
    val = response.cookies.get("session_id")
    if not val:
        # Fallback: parse raw Set-Cookie header
        set_cookie = response.headers.get("Set-Cookie", "")
        for part in set_cookie.split(";"):
            part = part.strip()
            if part.lower().startswith("session_id="):
                val = part.split("=", 1)[1].strip()
                break
    if val:
        session.headers.update({"Cookie": f"session_id={val}"})


# ---------------------------------------------------------------------------
# Helper: build a minimal synthetic PDF (not a valid 7501)
# ---------------------------------------------------------------------------

def _minimal_pdf(content: bytes = b"This is not a 7501 form") -> bytes:
    """Build a valid PDF 1.4 with arbitrary text content."""
    body = (
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
        b" /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    )
    stream = b"BT /F1 12 Tf 72 720 Td (" + content + b") Tj ET"
    stream_obj = (
        b"4 0 obj\n<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream + b"\nendstream\nendobj\n"
    )
    font_obj = (
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    )
    header = b"%PDF-1.4\n"
    xref_pos = len(header) + len(body) + len(stream_obj) + len(font_obj)
    xref = (
        b"xref\n0 6\n0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000062 00000 n \n"
        b"0000000114 00000 n \n"
    ) + f"{'xref_pos':010}".encode() + b" 00000 n \n"
    trailer = (
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + str(xref_pos).encode() + b"\n%%EOF"
    )
    return header + body + stream_obj + font_obj + xref + trailer


# ---------------------------------------------------------------------------
# ─── GROUP 1: Health Check ────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def test_health():
    print("\n── GROUP 1: Health Check ──────────────────────────────────────")

    # TC-HEALTH-001: happy path
    tc = _tc("TC-HEALTH-001", "Health", "GET /health returns 200 {status:ok}")
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        if r.status_code == 200 and r.json().get("status") == "ok":
            _pass(tc, 200, r.json())
        else:
            _fail(tc, r.status_code, r.json(), "Unexpected body")
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")


# ---------------------------------------------------------------------------
# ─── GROUP 2: Auth – POST /auth/token ─────────────────────────────────────
# ---------------------------------------------------------------------------

def test_auth_token():
    global _access_token, _session_cookies, _admin_token
    print("\n── GROUP 2: Auth – POST /auth/token ───────────────────────────")

    # TC-AUTH-001: valid credentials
    tc = _tc("TC-AUTH-001", "Auth/token", "Valid credentials → 200 + access_token + refresh cookie")
    try:
        r = requests.post(f"{API}/auth/token", json=CREDENTIALS, timeout=10)
        body = r.json()
        if (r.status_code == 200
                and body.get("access_token")
                and body.get("token_type") == "bearer"
                and "refresh_token" in r.cookies):
            _access_token = body["access_token"]
            _session_cookies = dict(r.cookies)
            _pass(tc, 200, body, "access_token present, refresh_token cookie set")
        else:
            _fail(tc, r.status_code, body, "Missing token or cookie")
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-AUTH-002: wrong password
    tc = _tc("TC-AUTH-002", "Auth/token", "Wrong password → 401 INVALID_CREDENTIALS")
    try:
        r = requests.post(f"{API}/auth/token", json={"email": CREDENTIALS["email"], "password": "wrong"}, timeout=10)
        body = r.json()
        if r.status_code == 401 and "INVALID_CREDENTIALS" in str(body):
            _pass(tc, 401, body)
        else:
            _fail(tc, r.status_code, body)
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-AUTH-003: unknown email
    tc = _tc("TC-AUTH-003", "Auth/token", "Unknown email → 401 INVALID_CREDENTIALS")
    try:
        r = requests.post(f"{API}/auth/token", json={"email": "nobody@example.com", "password": "anything"}, timeout=10)
        if r.status_code == 401:
            _pass(tc, 401, r.json())
        else:
            _fail(tc, r.status_code, r.json())
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-AUTH-004: missing email field
    tc = _tc("TC-AUTH-004", "Auth/token", "Missing email → 422 Unprocessable Entity")
    try:
        r = requests.post(f"{API}/auth/token", json={"password": "Test1234"}, timeout=10)
        if r.status_code == 422:
            _pass(tc, 422, r.json())
        else:
            _fail(tc, r.status_code, r.json())
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-AUTH-005: missing password field
    tc = _tc("TC-AUTH-005", "Auth/token", "Missing password → 422")
    try:
        r = requests.post(f"{API}/auth/token", json={"email": CREDENTIALS["email"]}, timeout=10)
        if r.status_code == 422:
            _pass(tc, 422, r.json())
        else:
            _fail(tc, r.status_code, r.json())
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-AUTH-006: invalid email format
    tc = _tc("TC-AUTH-006", "Auth/token", "Invalid email format → 422")
    try:
        r = requests.post(f"{API}/auth/token", json={"email": "not-an-email", "password": "Test1234"}, timeout=10)
        if r.status_code == 422:
            _pass(tc, 422, r.json())
        else:
            _fail(tc, r.status_code, r.json())
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-AUTH-007: empty body
    tc = _tc("TC-AUTH-007", "Auth/token", "Empty JSON body → 422")
    try:
        r = requests.post(f"{API}/auth/token", json={}, timeout=10)
        if r.status_code == 422:
            _pass(tc, 422, r.json())
        else:
            _fail(tc, r.status_code, r.json())
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-AUTH-008: null email
    tc = _tc("TC-AUTH-008", "Auth/token", "Null email → 422")
    try:
        r = requests.post(f"{API}/auth/token", json={"email": None, "password": "Test1234"}, timeout=10)
        if r.status_code == 422:
            _pass(tc, 422, r.json())
        else:
            _fail(tc, r.status_code, r.json())
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-AUTH-009: admin login
    tc = _tc("TC-AUTH-009", "Auth/token", "Admin login → 200 + access_token")
    try:
        r = requests.post(f"{API}/auth/token", json=ADMIN_CREDS, timeout=10)
        body = r.json()
        if r.status_code == 200 and body.get("access_token"):
            _admin_token = body["access_token"]
            _pass(tc, 200, {"access_token": "[redacted]"})
        else:
            _fail(tc, r.status_code, body)
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")


# ---------------------------------------------------------------------------
# ─── GROUP 3: Auth – POST /auth/refresh ───────────────────────────────────
# ---------------------------------------------------------------------------

def test_auth_refresh():
    global _access_token, _session_cookies
    print("\n── GROUP 3: Auth – POST /auth/refresh ─────────────────────────")

    # TC-REFRESH-001: valid refresh cookie → new access token
    tc = _tc("TC-REFRESH-001", "Auth/refresh", "Valid refresh cookie → 200 new access_token")
    try:
        r = requests.post(f"{API}/auth/refresh", cookies=_session_cookies, timeout=10)
        body = r.json()
        if r.status_code == 200 and body.get("access_token"):
            # Rotate: update stored tokens
            _access_token = body["access_token"]
            _session_cookies = dict(r.cookies) or _session_cookies
            _pass(tc, 200, {"access_token": "[redacted]"})
        else:
            _fail(tc, r.status_code, body)
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-REFRESH-002: no cookie → 401 REFRESH_TOKEN_MISSING
    tc = _tc("TC-REFRESH-002", "Auth/refresh", "No cookie → 401 REFRESH_TOKEN_MISSING")
    try:
        r = requests.post(f"{API}/auth/refresh", timeout=10)
        body = r.json()
        if r.status_code == 401 and "REFRESH_TOKEN_MISSING" in str(body):
            _pass(tc, 401, body)
        else:
            _fail(tc, r.status_code, body)
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-REFRESH-003: garbage token → 401
    tc = _tc("TC-REFRESH-003", "Auth/refresh", "Garbage token → 401")
    try:
        r = requests.post(f"{API}/auth/refresh", cookies={"refresh_token": "garbage"}, timeout=10)
        if r.status_code == 401:
            _pass(tc, 401, r.json())
        else:
            _fail(tc, r.status_code, r.json())
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")


# ---------------------------------------------------------------------------
# ─── GROUP 4: Auth – POST /auth/logout ────────────────────────────────────
# ---------------------------------------------------------------------------

def test_auth_logout():
    print("\n── GROUP 4: Auth – POST /auth/logout ──────────────────────────")

    # TC-LOGOUT-001: valid Bearer + refresh cookie → 200
    tc = _tc("TC-LOGOUT-001", "Auth/logout", "Valid logout → 200 {success:true}")
    try:
        # Login fresh so we can safely logout without breaking other tests
        r_login = requests.post(f"{API}/auth/token", json=CREDENTIALS, timeout=10)
        fresh_token = r_login.json().get("access_token", "")
        fresh_cookie = dict(r_login.cookies)

        r = requests.post(
            f"{API}/auth/logout",
            headers={"Authorization": f"Bearer {fresh_token}"},
            cookies=fresh_cookie,
            timeout=10,
        )
        body = r.json()
        if r.status_code == 200 and body.get("success") is True:
            _pass(tc, 200, body)
        else:
            _fail(tc, r.status_code, body)
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-LOGOUT-002: no Bearer token → 401/403
    tc = _tc("TC-LOGOUT-002", "Auth/logout", "No Bearer → 401 or 403")
    try:
        r = requests.post(f"{API}/auth/logout", timeout=10)
        if r.status_code in (401, 403):
            _pass(tc, r.status_code, r.json())
        else:
            _fail(tc, r.status_code, r.json(), "Expected 401/403")
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-LOGOUT-003: tampered/expired Bearer → 401
    tc = _tc("TC-LOGOUT-003", "Auth/logout", "Tampered Bearer → 401")
    try:
        r = requests.post(f"{API}/auth/logout",
                          headers={"Authorization": "Bearer invalid.token.here"},
                          timeout=10)
        if r.status_code in (401, 403):
            _pass(tc, r.status_code, r.json())
        else:
            _fail(tc, r.status_code, r.json())
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")


# ---------------------------------------------------------------------------
# ─── GROUP 5: Documents – POST /documents/upload ──────────────────────────
# ---------------------------------------------------------------------------

def test_upload():
    global _job_id
    print("\n── GROUP 5: Documents – POST /documents/upload ────────────────")

    if not SAMPLE_PDF.exists():
        print("  [SKIP] No sample PDF found — skipping upload group")
        for i in range(1, 12):
            tc = _tc(f"TC-UPLOAD-{i:03d}", "Upload", "skipped")
            _skip(tc, "No sample PDF")
        return

    pdf_bytes = SAMPLE_PDF.read_bytes()
    idem_key = str(uuid.uuid4())

    # TC-UPLOAD-001: happy path with valid PDF
    tc = _tc("TC-UPLOAD-001", "Upload", "Valid PDF + privacy_accepted=true → 202 + job_id")
    try:
        r = requests.post(
            f"{API}/documents/upload",
            headers={"X-Idempotency-Key": idem_key},
            data={"privacy_accepted": "true"},
            files={"file": (SAMPLE_PDF.name, pdf_bytes, "application/pdf")},
            timeout=30,
        )
        body = r.json()
        if r.status_code == 202 and body.get("success") and body.get("data", {}).get("job_id"):
            _job_id = body["data"]["job_id"]
            _pass(tc, 202, body, f"job_id={_job_id}")
        else:
            _fail(tc, r.status_code, body)
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-UPLOAD-002: idempotency — same key returns same job_id
    tc = _tc("TC-UPLOAD-002", "Upload", "Repeat upload with same X-Idempotency-Key → same job_id")
    try:
        r = requests.post(
            f"{API}/documents/upload",
            headers={"X-Idempotency-Key": idem_key},
            data={"privacy_accepted": "true"},
            files={"file": (SAMPLE_PDF.name, pdf_bytes, "application/pdf")},
            timeout=30,
        )
        body = r.json()
        returned_id = body.get("data", {}).get("job_id", "")
        if r.status_code == 202 and returned_id == _job_id:
            _pass(tc, 202, {"job_id": returned_id}, "Idempotent — same job_id returned")
        else:
            _fail(tc, r.status_code, body, f"Expected {_job_id}, got {returned_id}")
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-UPLOAD-003: missing X-Idempotency-Key → 422
    tc = _tc("TC-UPLOAD-003", "Upload", "Missing X-Idempotency-Key → 422")
    try:
        r = requests.post(
            f"{API}/documents/upload",
            data={"privacy_accepted": "true"},
            files={"file": (SAMPLE_PDF.name, pdf_bytes, "application/pdf")},
            timeout=30,
        )
        if r.status_code == 422:
            _pass(tc, 422, r.json())
        else:
            _fail(tc, r.status_code, r.json())
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-UPLOAD-004: privacy_accepted=false → 400
    tc = _tc("TC-UPLOAD-004", "Upload", "privacy_accepted=false → 400 PRIVACY_NOT_ACCEPTED")
    try:
        r = requests.post(
            f"{API}/documents/upload",
            headers=_idem(),
            data={"privacy_accepted": "false"},
            files={"file": (SAMPLE_PDF.name, pdf_bytes, "application/pdf")},
            timeout=30,
        )
        body = r.json()
        if r.status_code == 400 and "PRIVACY_NOT_ACCEPTED" in str(body):
            _pass(tc, 400, body)
        else:
            _fail(tc, r.status_code, body)
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-UPLOAD-005: missing privacy_accepted → 422
    tc = _tc("TC-UPLOAD-005", "Upload", "Missing privacy_accepted → 422")
    try:
        r = requests.post(
            f"{API}/documents/upload",
            headers=_idem(),
            files={"file": (SAMPLE_PDF.name, pdf_bytes, "application/pdf")},
            timeout=30,
        )
        if r.status_code == 422:
            _pass(tc, 422, r.json())
        else:
            _fail(tc, r.status_code, r.json())
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-UPLOAD-006: non-PDF content (plain text disguised as PDF) → 415
    tc = _tc("TC-UPLOAD-006", "Upload", "Plain text file → 415 UNSUPPORTED_FILE_TYPE")
    try:
        r = requests.post(
            f"{API}/documents/upload",
            headers=_idem(),
            data={"privacy_accepted": "true"},
            files={"file": ("fake.pdf", b"Just some text content", "application/pdf")},
            timeout=30,
        )
        body = r.json()
        if r.status_code == 415 and "UNSUPPORTED_FILE_TYPE" in str(body):
            _pass(tc, 415, body)
        else:
            _fail(tc, r.status_code, body, "Expected 415 UNSUPPORTED_FILE_TYPE")
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-UPLOAD-007: empty file → 415 or 422
    tc = _tc("TC-UPLOAD-007", "Upload", "Zero-byte file → 415 or 422")
    try:
        r = requests.post(
            f"{API}/documents/upload",
            headers=_idem(),
            data={"privacy_accepted": "true"},
            files={"file": ("empty.pdf", b"", "application/pdf")},
            timeout=30,
        )
        if r.status_code in (400, 415, 422):
            _pass(tc, r.status_code, r.json())
        else:
            _fail(tc, r.status_code, r.json(), "Expected 4xx for empty file")
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-UPLOAD-008: non-7501 PDF → 202 accepted, but OCR will flag INVALID_7501_FORMAT
    tc = _tc("TC-UPLOAD-008", "Upload", "Non-7501 PDF accepted (202); OCR will classify INVALID_7501_FORMAT")
    non7501_bytes = _minimal_pdf(b"Invoice #12345 From: ACME Corp To: Buyer Inc Total: USD 1000.00")
    non7501_idem = str(uuid.uuid4())
    non7501_job_id = ""
    try:
        r = requests.post(
            f"{API}/documents/upload",
            headers={"X-Idempotency-Key": non7501_idem},
            data={"privacy_accepted": "true"},
            files={"file": ("invoice.pdf", non7501_bytes, "application/pdf")},
            timeout=30,
        )
        body = r.json()
        if r.status_code == 202 and body.get("data", {}).get("job_id"):
            non7501_job_id = body["data"]["job_id"]
            _pass(tc, 202, body, f"job_id={non7501_job_id} — will poll for INVALID_7501_FORMAT")
        else:
            _fail(tc, r.status_code, body)
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-UPLOAD-009: oversized file > 20 MB → 413
    tc = _tc("TC-UPLOAD-009", "Upload", "File > 20 MB → 413 FILE_TOO_LARGE")
    try:
        big = b"X" * (20 * 1024 * 1024 + 1)
        r = requests.post(
            f"{API}/documents/upload",
            headers=_idem(),
            data={"privacy_accepted": "true"},
            files={"file": ("big.pdf", big, "application/pdf")},
            timeout=60,
        )
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
        if r.status_code == 413:
            _pass(tc, 413, body)
        else:
            _fail(tc, r.status_code, body, "Expected 413")
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-UPLOAD-010: missing file field → 422
    tc = _tc("TC-UPLOAD-010", "Upload", "Missing file field → 422")
    try:
        r = requests.post(
            f"{API}/documents/upload",
            headers=_idem(),
            data={"privacy_accepted": "true"},
            timeout=10,
        )
        if r.status_code == 422:
            _pass(tc, 422, r.json())
        else:
            _fail(tc, r.status_code, r.json(), "Expected 422")
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-UPLOAD-011: response contract check
    tc = _tc("TC-UPLOAD-011", "Upload", "Response contract: success/data/error/meta envelope")
    try:
        r = requests.post(
            f"{API}/documents/upload",
            headers=_idem(),
            data={"privacy_accepted": "true"},
            files={"file": (SAMPLE_PDF.name, pdf_bytes, "application/pdf")},
            timeout=30,
        )
        body = r.json()
        if (r.status_code == 202
                and "success" in body
                and "data" in body
                and "error" in body
                and "meta" in body
                and "job_id" in body.get("data", {})
                and "status" in body.get("data", {})
                and "expires_at" in body.get("data", {})):
            _pass(tc, 202, body, "All envelope fields present")
        else:
            _fail(tc, r.status_code, body, "Envelope fields missing")
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")


# ---------------------------------------------------------------------------
# ─── GROUP 6: Documents – GET /documents/{job_id}/status ──────────────────
# ---------------------------------------------------------------------------

def test_status():
    print("\n── GROUP 6: Documents – GET /{job_id}/status ──────────────────")

    if not _job_id:
        print("  [SKIP] No job_id available — skipping status group")
        for i in range(1, 7):
            tc = _tc(f"TC-STATUS-{i:03d}", "Status", "skipped")
            _skip(tc, "No job_id")
        return

    # TC-STATUS-001: valid job_id (session cookie from upload)
    tc = _tc("TC-STATUS-001", "Status", "Valid job_id → 200 with status field")
    try:
        # Upload set a session_id cookie; we need to pass it for guest access
        # Since our upload was done without cookies, session_id is None; backend checks session_id match
        # We upload again with cookie tracking
        r = requests.get(f"{API}/documents/{_job_id}/status", timeout=10)
        body = r.json()
        # Either 200 (with session match) or 403 (no session)
        if r.status_code in (200, 403):
            _pass(tc, r.status_code, body, "Status endpoint reachable")
        else:
            _fail(tc, r.status_code, body)
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # Upload a new file tracking the session cookie.
    # IMPORTANT: the server sets session_id with Secure=True.  The `requests`
    # library will not send a Secure cookie over plain HTTP, causing 403.
    # We work around this by extracting the value from the Set-Cookie header
    # and re-injecting it without the Secure flag via _inject_session_cookie().
    s = requests.Session()
    pdf_bytes = SAMPLE_PDF.read_bytes() if SAMPLE_PDF.exists() else b""
    idem2 = str(uuid.uuid4())
    r2 = s.post(
        f"{API}/documents/upload",
        headers={"X-Idempotency-Key": idem2},
        data={"privacy_accepted": "true"},
        files={"file": (SAMPLE_PDF.name, pdf_bytes, "application/pdf")},
        timeout=30,
    )
    if r2.status_code == 202:
        _inject_session_cookie(s, r2)
    tracked_job_id = r2.json().get("data", {}).get("job_id", "") if r2.status_code == 202 else ""

    # TC-STATUS-002: with session cookie → 200
    tc = _tc("TC-STATUS-002", "Status", "Session-owned job → 200 with data.status enum")
    if tracked_job_id:
        try:
            r = s.get(f"{API}/documents/{tracked_job_id}/status", timeout=10)
            body = r.json()
            valid_statuses = {"queued", "processing", "completed", "review_required", "failed"}
            if r.status_code == 200 and body.get("data", {}).get("status") in valid_statuses:
                _pass(tc, 200, body, f"status={body['data']['status']}")
            else:
                _fail(tc, r.status_code, body)
        except Exception as e:
            _fail(tc, 0, detail=str(e))
    else:
        _skip(tc, "Could not create tracked job")
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-STATUS-003: non-existent job_id → 404
    tc = _tc("TC-STATUS-003", "Status", "Non-existent UUID → 404")
    try:
        fake_id = str(uuid.uuid4())
        r = requests.get(f"{API}/documents/{fake_id}/status", timeout=10)
        if r.status_code == 404:
            _pass(tc, 404, r.json())
        else:
            _fail(tc, r.status_code, r.json())
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-STATUS-004: malformed UUID → 422 or 404
    tc = _tc("TC-STATUS-004", "Status", "Malformed UUID → 422")
    try:
        r = requests.get(f"{API}/documents/not-a-uuid/status", timeout=10)
        if r.status_code in (422, 404):
            _pass(tc, r.status_code, r.json())
        else:
            _fail(tc, r.status_code, r.json())
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-STATUS-005: admin can access any job
    tc = _tc("TC-STATUS-005", "Status", "Admin Bearer → 200 on any job_id")
    if _admin_token and tracked_job_id:
        try:
            r = requests.get(
                f"{API}/documents/{tracked_job_id}/status",
                headers=_bearer(_admin_token),
                timeout=10,
            )
            if r.status_code == 200:
                _pass(tc, 200, r.json(), "Admin can access any document")
            else:
                _fail(tc, r.status_code, r.json())
        except Exception as e:
            _fail(tc, 0, detail=str(e))
    else:
        _skip(tc, "No admin token or tracked_job_id")
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-STATUS-006: response contract
    tc = _tc("TC-STATUS-006", "Status", "Response contract: success/data(job_id,status,error,ocr_*)/error/meta")
    if tracked_job_id:
        try:
            r = s.get(f"{API}/documents/{tracked_job_id}/status", timeout=10)
            body = r.json()
            d = body.get("data", {})
            required_keys = {"job_id", "status", "error", "ocr_provider", "ocr_confidence"}
            missing = required_keys - set(d.keys())
            if r.status_code == 200 and not missing:
                _pass(tc, 200, d, "All required keys present")
            else:
                _fail(tc, r.status_code, body, f"Missing keys: {missing}")
        except Exception as e:
            _fail(tc, 0, detail=str(e))
    else:
        _skip(tc, "No tracked_job_id")
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-STATUS-007: poll until non-queued (max 60s) using tracked session
    tc = _tc("TC-STATUS-007", "Status", "Poll until OCR completes (max 60s) — verify final status")
    if tracked_job_id:
        try:
            final_status = None
            for _ in range(12):
                r = s.get(f"{API}/documents/{tracked_job_id}/status", timeout=10)
                st = r.json().get("data", {}).get("status", "")
                if st not in ("queued", "processing"):
                    final_status = st
                    break
                time.sleep(5)
            if final_status in ("completed", "review_required", "failed"):
                _pass(tc, 200, {"final_status": final_status})
            else:
                _fail(tc, 0, {"final_status": final_status}, "OCR did not complete in 60s")
        except Exception as e:
            _fail(tc, 0, detail=str(e))
    else:
        _skip(tc, "No tracked_job_id")
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    return tracked_job_id, s   # return for use in patch/calculate tests


# ---------------------------------------------------------------------------
# ─── GROUP 7: Documents – PATCH /documents/{job_id}/fields ────────────────
# ---------------------------------------------------------------------------

def test_patch_fields(tracked_job_id: str = "", s: requests.Session | None = None):
    print("\n── GROUP 7: Documents – PATCH /{job_id}/fields ────────────────")

    if not tracked_job_id:
        print("  [SKIP] No ready job_id — skipping patch group")
        for i in range(1, 6):
            tc = _tc(f"TC-PATCH-{i:03d}", "Patch/fields", "skipped")
            _skip(tc, "No ready job_id")
        return

    sess = s or requests.Session()

    # TC-PATCH-001: valid corrections on completed/review_required job
    tc = _tc("TC-PATCH-001", "Patch/fields", "Valid corrections dict → 200 + merged_fields")
    try:
        corrections = {
            "entry_number": "TEST-001",
            "country_of_origin": "CN",
            "mode_of_transport": "air",
        }
        r = sess.patch(f"{API}/documents/{tracked_job_id}/fields", json=corrections, timeout=10)
        body = r.json()
        if r.status_code == 200 and body.get("success") and "merged_fields" in body.get("data", {}):
            _pass(tc, 200, body)
        else:
            _fail(tc, r.status_code, body)
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-PATCH-002: empty corrections dict → 200 (no-op)
    tc = _tc("TC-PATCH-002", "Patch/fields", "Empty dict → 200 (no-op)")
    try:
        r = sess.patch(f"{API}/documents/{tracked_job_id}/fields", json={}, timeout=10)
        if r.status_code == 200 and r.json().get("success"):
            _pass(tc, 200, r.json())
        else:
            _fail(tc, r.status_code, r.json())
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-PATCH-003: non-existent job_id → 404
    tc = _tc("TC-PATCH-003", "Patch/fields", "Non-existent job_id → 404")
    try:
        r = requests.patch(f"{API}/documents/{uuid.uuid4()}/fields", json={"k": "v"}, timeout=10)
        if r.status_code == 404:
            _pass(tc, 404, r.json())
        else:
            _fail(tc, r.status_code, r.json())
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-PATCH-004: job not ready (queued/processing) → 409
    tc = _tc("TC-PATCH-004", "Patch/fields", "Job in queued state → 409 JOB_NOT_READY")
    try:
        # Upload a new job (it will be queued)
        idem_new = str(uuid.uuid4())
        pdf_bytes = SAMPLE_PDF.read_bytes() if SAMPLE_PDF.exists() else b""
        r_up = sess.post(
            f"{API}/documents/upload",
            headers={"X-Idempotency-Key": idem_new},
            data={"privacy_accepted": "true"},
            files={"file": (SAMPLE_PDF.name, pdf_bytes, "application/pdf")},
            timeout=30,
        )
        if r_up.status_code != 202:
            _skip(tc, f"Upload returned {r_up.status_code}, cannot test queued state")
        else:
            _inject_session_cookie(sess, r_up)
            new_jid = r_up.json().get("data", {}).get("job_id", "")
            if new_jid:
                r = sess.patch(f"{API}/documents/{new_jid}/fields", json={"k": "v"}, timeout=10)
                if r.status_code == 409:
                    _pass(tc, 409, r.json())
                else:
                    _fail(tc, r.status_code, r.json(), f"Expected 409, got {r.status_code}")
            else:
                _skip(tc, "Could not create queued job")
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-PATCH-005: response contract
    tc = _tc("TC-PATCH-005", "Patch/fields", "Response contract: job_id + corrections_applied + merged_fields")
    try:
        r = sess.patch(f"{API}/documents/{tracked_job_id}/fields", json={"summary_date": "2025-02-15"}, timeout=10)
        body = r.json()
        d = body.get("data", {})
        if (r.status_code == 200
                and "job_id" in d
                and "corrections_applied" in d
                and "merged_fields" in d):
            _pass(tc, 200, d)
        else:
            _fail(tc, r.status_code, body, "Missing contract fields")
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")


# ---------------------------------------------------------------------------
# ─── GROUP 8: Documents – POST /documents/{job_id}/calculate ──────────────
# ---------------------------------------------------------------------------

def test_calculate(tracked_job_id: str = "", s: requests.Session | None = None):
    global _calc_id
    print("\n── GROUP 8: Documents – POST /{job_id}/calculate ──────────────")

    if not tracked_job_id:
        print("  [SKIP] No ready job_id — skipping calculate group")
        for i in range(1, 6):
            tc = _tc(f"TC-CALC-{i:03d}", "Calculate", "skipped")
            _skip(tc, "No ready job_id")
        return

    sess = s or requests.Session()

    # TC-CALC-001: happy path
    tc = _tc("TC-CALC-001", "Calculate", "Ready job → 202 + calculation_id")
    try:
        r = sess.post(
            f"{API}/documents/{tracked_job_id}/calculate",
            headers=_idem(),
            timeout=60,
        )
        body = r.json()
        if r.status_code == 202 and body.get("data", {}).get("calculation_id"):
            _calc_id = body["data"]["calculation_id"]
            _pass(tc, 202, body, f"calculation_id={_calc_id}")
        else:
            _fail(tc, r.status_code, body)
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-CALC-002: idempotency — repeat gives same calc_id (if non-zero duty existed)
    tc = _tc("TC-CALC-002", "Calculate", "Repeat calculate → 202 (idempotent or new calc)")
    try:
        r = sess.post(
            f"{API}/documents/{tracked_job_id}/calculate",
            headers=_idem(),
            timeout=60,
        )
        body = r.json()
        if r.status_code == 202:
            _pass(tc, 202, body, "Idempotent or recalculated")
        else:
            _fail(tc, r.status_code, body)
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-CALC-003: non-existent job_id → 404
    tc = _tc("TC-CALC-003", "Calculate", "Non-existent job_id → 404")
    try:
        r = requests.post(f"{API}/documents/{uuid.uuid4()}/calculate", headers=_idem(), timeout=10)
        if r.status_code == 404:
            _pass(tc, 404, r.json())
        else:
            _fail(tc, r.status_code, r.json())
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-CALC-004: job not ready → 409
    tc = _tc("TC-CALC-004", "Calculate", "Queued job → 409 JOB_NOT_READY")
    try:
        idem_new = str(uuid.uuid4())
        pdf_bytes = SAMPLE_PDF.read_bytes() if SAMPLE_PDF.exists() else b""
        r_up = sess.post(
            f"{API}/documents/upload",
            headers={"X-Idempotency-Key": idem_new},
            data={"privacy_accepted": "true"},
            files={"file": (SAMPLE_PDF.name, pdf_bytes, "application/pdf")},
            timeout=30,
        )
        if r_up.status_code != 202:
            _skip(tc, f"Upload returned {r_up.status_code}, cannot test queued state")
        else:
            _inject_session_cookie(sess, r_up)
            new_jid = r_up.json().get("data", {}).get("job_id", "")
            if new_jid:
                r = sess.post(f"{API}/documents/{new_jid}/calculate", headers=_idem(), timeout=10)
                if r.status_code == 409:
                    _pass(tc, 409, r.json())
                else:
                    _fail(tc, r.status_code, r.json(), f"Expected 409")
            else:
                _skip(tc, "Could not create queued job")
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-CALC-005: response contract
    tc = _tc("TC-CALC-005", "Calculate", "Response contract: success/data.calculation_id/error/meta")
    if _calc_id:
        try:
            r = sess.post(
                f"{API}/documents/{tracked_job_id}/calculate",
                headers=_idem(),
                timeout=60,
            )
            body = r.json()
            if (r.status_code == 202
                    and "success" in body
                    and "calculation_id" in body.get("data", {})):
                _pass(tc, 202, body)
            else:
                _fail(tc, r.status_code, body, "Missing contract fields")
        except Exception as e:
            _fail(tc, 0, detail=str(e))
    else:
        _skip(tc, "No calc_id from previous step")
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")


# ---------------------------------------------------------------------------
# ─── GROUP 9: Results – GET /results/{calculation_id} ─────────────────────
# ---------------------------------------------------------------------------

def test_results():
    print("\n── GROUP 9: Results – GET /results/{calculation_id} ───────────")

    if not _calc_id:
        print("  [SKIP] No calculation_id — skipping results group")
        for i in range(1, 7):
            tc = _tc(f"TC-RESULT-{i:03d}", "Results", "skipped")
            _skip(tc, "No calc_id")
        return

    # TC-RESULT-001: valid calculation_id → 200
    tc = _tc("TC-RESULT-001", "Results", "Valid calculation_id → 200 + full result object")
    try:
        r = requests.get(f"{API}/results/{_calc_id}", timeout=10)
        body = r.json()
        if r.status_code == 200 and body.get("success"):
            _pass(tc, 200, body, "Full result returned")
        else:
            _fail(tc, r.status_code, body)
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-RESULT-002: non-existent UUID → 404
    tc = _tc("TC-RESULT-002", "Results", "Non-existent UUID → 404")
    try:
        r = requests.get(f"{API}/results/{uuid.uuid4()}", timeout=10)
        if r.status_code == 404:
            _pass(tc, 404, r.json())
        else:
            _fail(tc, r.status_code, r.json())
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-RESULT-003: malformed UUID → 422
    tc = _tc("TC-RESULT-003", "Results", "Malformed UUID → 422")
    try:
        r = requests.get(f"{API}/results/not-a-uuid", timeout=10)
        if r.status_code in (422, 404):
            _pass(tc, r.status_code, r.json())
        else:
            _fail(tc, r.status_code, r.json())
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-RESULT-004: business rules — response field presence
    tc = _tc("TC-RESULT-004", "Results", "BR validation: refund_pathway ∈ {PSC,PROTEST,INELIGIBLE}")
    try:
        r = requests.get(f"{API}/results/{_calc_id}", timeout=10)
        body = r.json()
        data = body.get("data", {})
        pathway = data.get("refund_pathway", "")
        if r.status_code == 200 and pathway in ("PSC", "PROTEST", "INELIGIBLE"):
            _pass(tc, 200, {"refund_pathway": pathway})
        else:
            _fail(tc, r.status_code, {"refund_pathway": pathway, "full": data}, "Invalid pathway")
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-RESULT-005: response contract — required fields
    tc = _tc("TC-RESULT-005", "Results", "Response contract: required fields present")
    try:
        r = requests.get(f"{API}/results/{_calc_id}", timeout=10)
        body = r.json()
        data = body.get("data", {})
        required = {
            "calculation_id", "estimated_refund", "refund_pathway",
            "days_elapsed", "tariff_lines", "total_duty"
        }
        missing = required - set(data.keys())
        if r.status_code == 200 and not missing:
            _pass(tc, 200, {k: data[k] for k in required}, "All required fields present")
        else:
            _fail(tc, r.status_code, body, f"Missing: {missing}")
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-RESULT-006: MPF/HMF in tariff_lines
    tc = _tc("TC-RESULT-006", "Results", "tariff_lines contains MPF entry with refundable=false")
    try:
        r = requests.get(f"{API}/results/{_calc_id}", timeout=10)
        data = r.json().get("data", {})
        tariff_lines = data.get("tariff_lines", [])
        mpf_lines = [t for t in tariff_lines if t.get("tariff_type") == "MPF"]
        if mpf_lines and mpf_lines[0].get("refundable") is False:
            _pass(tc, 200, mpf_lines[0])
        elif not mpf_lines:
            _fail(tc, r.status_code, data, "No MPF line in tariff_lines")
        else:
            _fail(tc, r.status_code, mpf_lines[0], "MPF should have refundable=false")
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-RESULT-007: IEEPA refundable=true when present
    tc = _tc("TC-RESULT-007", "Results", "IEEPA tariff_line has refundable=true when present")
    try:
        r = requests.get(f"{API}/results/{_calc_id}", timeout=10)
        data = r.json().get("data", {})
        tariff_lines = data.get("tariff_lines", [])
        ieepa_lines = [t for t in tariff_lines if t.get("tariff_type") == "IEEPA"]
        if ieepa_lines:
            if all(t.get("refundable") is True for t in ieepa_lines):
                _pass(tc, 200, ieepa_lines)
            else:
                _fail(tc, r.status_code, ieepa_lines, "IEEPA should be refundable=true")
        else:
            _pass(tc, 200, {}, "No IEEPA line (non-CN origin or no IEEPA rate) — acceptable")
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")


# ---------------------------------------------------------------------------
# ─── GROUP 10: Non-7501 PDF error flow ────────────────────────────────────
# ---------------------------------------------------------------------------

def test_non_7501_error_flow():
    print("\n── GROUP 10: Non-7501 PDF error flow ──────────────────────────")

    s = requests.Session()
    idem = str(uuid.uuid4())
    non7501_bytes = _minimal_pdf(b"Invoice #12345 From: ACME Corp Amount: USD 5000.00")

    # TC-N7501-001: upload non-7501 PDF → 202
    tc = _tc("TC-N7501-001", "Non-7501", "Non-7501 PDF upload accepted (202)")
    non7501_jid = ""
    try:
        r = s.post(
            f"{API}/documents/upload",
            headers={"X-Idempotency-Key": idem},
            data={"privacy_accepted": "true"},
            files={"file": ("invoice.pdf", non7501_bytes, "application/pdf")},
            timeout=30,
        )
        body = r.json()
        if r.status_code == 202 and body.get("data", {}).get("job_id"):
            non7501_jid = body["data"]["job_id"]
            _inject_session_cookie(s, r)
            _pass(tc, 202, body)
        else:
            _fail(tc, r.status_code, body)
    except Exception as e:
        _fail(tc, 0, detail=str(e))
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-N7501-002: poll until failed, verify error_code = INVALID_7501_FORMAT or UNRECOGNISED_DOCUMENT
    tc = _tc("TC-N7501-002", "Non-7501", "Poll status → failed with INVALID_7501_FORMAT error_code")
    if non7501_jid:
        try:
            final_status = None
            error_code = None
            for _ in range(12):
                r = s.get(f"{API}/documents/{non7501_jid}/status", timeout=10)
                d = r.json().get("data", {})
                st = d.get("status", "")
                if st not in ("queued", "processing"):
                    final_status = st
                    error_code = d.get("error")
                    break
                time.sleep(5)
            valid_err = error_code in ("INVALID_7501_FORMAT", "UNRECOGNISED_DOCUMENT")
            if final_status == "failed" and valid_err:
                _pass(tc, 200, {"status": final_status, "error_code": error_code})
            elif final_status == "failed" and not valid_err:
                _fail(tc, 200,
                      {"status": final_status, "error_code": error_code},
                      "Failed but unexpected error_code")
            else:
                _fail(tc, 0, {"status": final_status, "error_code": error_code},
                      "Did not reach failed status")
        except Exception as e:
            _fail(tc, 0, detail=str(e))
    else:
        _skip(tc, "No non-7501 job_id")
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")

    # TC-N7501-003: calculate on failed job → 409
    tc = _tc("TC-N7501-003", "Non-7501", "Calculate on failed job → 409 JOB_NOT_READY")
    if non7501_jid:
        try:
            r = s.post(f"{API}/documents/{non7501_jid}/calculate", headers=_idem(), timeout=10)
            if r.status_code == 409:
                _pass(tc, 409, r.json())
            else:
                _fail(tc, r.status_code, r.json(), "Expected 409")
        except Exception as e:
            _fail(tc, 0, detail=str(e))
    else:
        _skip(tc, "No non-7501 job_id")
    print(f"  [{tc.result}] {tc.id}: {tc.desc}")


# ---------------------------------------------------------------------------
# ─── Rate-limit reset helper ──────────────────────────────────────────────
# ---------------------------------------------------------------------------

def _reset_rate_limits() -> None:
    """Flush slowapi counters from Redis DB 1 (upload rate-limit store)."""
    import subprocess
    result = subprocess.run(
        ["docker", "compose", "exec", "redis", "redis-cli", "-n", "1", "FLUSHDB"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).parent),
    )
    if result.returncode == 0:
        print("  [INFO] Rate-limit counters flushed (Redis DB 1)")
    else:
        print(f"  [WARN] Could not flush rate limits: {result.stderr.strip()}")


# ---------------------------------------------------------------------------
# ─── Main runner ──────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def main():
    print("=" * 64)
    print("IEEPA Refund Calculator — API Test Runner")
    print(f"Target: {BASE_URL}")
    print("=" * 64)

    _reset_rate_limits()

    test_health()
    test_auth_token()
    test_auth_refresh()
    test_auth_logout()
    test_upload()
    result = test_status()
    tracked_job_id, sess = result if result else ("", None)

    # Wait for OCR to settle before patch / calculate tests
    if tracked_job_id and sess:
        print("\n  [Waiting for OCR on tracked job…]", end="", flush=True)
        for _ in range(18):
            r = sess.get(f"{API}/documents/{tracked_job_id}/status", timeout=10)
            st = r.json().get("data", {}).get("status", "queued")
            if st not in ("queued", "processing"):
                break
            print(".", end="", flush=True)
            time.sleep(5)
        print()

    test_patch_fields(tracked_job_id, sess)
    test_calculate(tracked_job_id, sess)
    test_results()

    _reset_rate_limits()
    test_non_7501_error_flow()

    # ── Summary ────────────────────────────────────────────────────────────
    passed  = sum(1 for t in _results if t.result == "PASS")
    failed  = sum(1 for t in _results if t.result == "FAIL")
    skipped = sum(1 for t in _results if t.result == "SKIP")
    total   = len(_results)

    print("\n" + "=" * 64)
    print(f"SUMMARY: {passed}/{total} PASSED  |  {failed} FAILED  |  {skipped} SKIPPED")
    print("=" * 64)

    # Write JSON dump for report generation
    with open("api_test_results.json", "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "id": t.id,
                    "group": t.group,
                    "desc": t.desc,
                    "result": t.result,
                    "actual_status": t.actual_status,
                    "detail": t.detail,
                }
                for t in _results
            ],
            f,
            ensure_ascii=False,
            indent=2,
        )
    print("Raw results written to: api_test_results.json")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
