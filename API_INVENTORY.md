# REFUNDCAL API INVENTORY FOR TEST CASE GENERATION

## 1. AUTHENTICATION ENDPOINTS

### 1.1 POST /api/v1/auth/token - Login

**Auth:** None (public)
**Rate Limit:** 5/minute

**Request:**
- email: EmailStr (valid email format)
- password: str (plain text)

**Response (200):**
- access_token: str (JWT HS256, 15min TTL)
- token_type: str ("bearer")
- Set-Cookie: refresh_token=<JWT>; HttpOnly; Secure; SameSite=Strict; Max-Age=604800

**Business Rules:** Email must be verified (is_email_verified=True), user must be active (is_active=True)

**Side Effects:**
- DB: SELECT users WHERE email=
- Password verified via constant-time bcrypt comparison

**Error Cases:**
- 401 INVALID_CREDENTIALS: Email not found OR password wrong (same message)
- 403 EMAIL_NOT_VERIFIED: User is inactive or email not verified
- 429: Rate limit exceeded

---

### 1.2 POST /api/v1/auth/refresh - Rotate Refresh Token

**Auth:** None (uses cookie)
**Rate Limit:** 60/minute

**Request:**
- Cookie: refresh_token (httpOnly cookie)

**Response (200):**
- access_token: str (new JWT)
- token_type: str ("bearer")
- Set-Cookie: refresh_token=<new_JWT>; HttpOnly; Secure; SameSite=Strict; Max-Age=604800

**Business Rules:** Refresh token rotation - old token blacklisted immediately

**Side Effects:**
- Redis: GET rt_blacklist:{jti} (check if revoked)
- Redis: SET rt_blacklist:{old_jti} "1" ex=<remaining_ttl> (blacklist old)
- DB: SELECT users WHERE id= (fetch current role/email)

**Error Cases:**
- 401 REFRESH_TOKEN_MISSING: No refresh_token cookie
- 401 REFRESH_TOKEN_REVOKED: Token found in Redis blacklist
- 401 REFRESH_TOKEN_EXPIRED: JWT expired or malformed
- 401 USER_NOT_FOUND: User ID from JWT not in DB or inactive

---

### 1.3 POST /api/v1/auth/logout - Logout

**Auth:** Bearer JWT required (CurrentUser)
**Rate Limit:** 60/minute

**Request:**
- Authorization: Bearer <token>
- Cookie: refresh_token (optional)

**Response (200):**
- message: str ("Logged out")
- Set-Cookie: refresh_token=; Max-Age=0 (expires cookie)

**Side Effects:**
- Redis: SET rt_blacklist:{jti} "1" ex=<ttl> (if refresh_token cookie present)

**Error Cases:**
- 401: No Bearer token or token expired/invalid

---

## 2. DOCUMENT ENDPOINTS

### 2.1 POST /api/v1/documents/upload - Upload CBP Form 7501

**Auth:** Optional (creates session_id cookie for guests)
**Rate Limit:** 10/hour

**Request:**
- file: UploadFile (PDF/JPEG/PNG, ≤20MB, magic bytes validated)
- privacy_accepted: str ("true" exact match)
- X-Idempotency-Key: str (UUID recommended)
- Authorization: Bearer <token> (optional for auth users)

**Validation Order:**
1. privacy_accepted == "true" → 400 PRIVACY_NOT_ACCEPTED if not
2. X-Idempotency-Key present → 422 if missing
3. Idempotency key already used → return existing 202
4. Content-Type pre-check (fast-fail)
5. File chunked read, enforce 20MB → 413 FILE_TOO_LARGE
6. Magic bytes validation → 415 UNSUPPORTED_FILE_TYPE

**Response (202 Accepted):**
- job_id: uuid (Document.id)
- status: str ("queued")
- expires_at: ISO 8601 (24 hours from upload)
- Set-Cookie: session_id=<UUID>; HttpOnly; Secure; SameSite=Strict; Max-Age=86400 (guests only)

**Business Rules:** None directly (applied later in OCR)

**Side Effects:**
- DB: INSERT documents (id, user_id, session_id, idempotency_key, status='queued')
- File I/O: Encrypt file with Fernet AES-256, write to /data/uploads/{date}/{job_id}/original.{ext}
- Celery: Enqueue process_ocr_job(job_id)

**Error Cases:**
- 400 PRIVACY_NOT_ACCEPTED: privacy_accepted != "true"
- 413 FILE_TOO_LARGE: File > 20MB
- 415 UNSUPPORTED_FILE_TYPE: Magic bytes not PDF/JPEG/PNG
- 422: Missing X-Idempotency-Key header
- 429: Rate limit (10/hour)

---

### 2.2 GET /api/v1/documents/{job_id}/status - Poll OCR Status

**Auth:** Session cookie OR Bearer JWT (access control: must own document)
**Rate Limit:** 60/minute

**Request:**
- job_id: uuid (path parameter)
- session_id: str (cookie) OR Authorization: Bearer <token>

**Response (200):**
- job_id: uuid (echo)
- status: str ("queued" | "processing" | "completed" | "review_required" | "failed")
- error: str or null (error_code if failed)
- ocr_provider: str or null ("google_docai" | "tesseract")
- ocr_confidence: float or null (0.0-1.0)
- extracted_fields: object or null (only if status in (completed, review_required))

**extracted_fields Schema:**
`json
{
  "entry_number": {"value": "001-2025-12345", "confidence": 0.95, "review_required": false},
  "summary_date": {"value": "2025-03-04", "confidence": 0.92, "review_required": false},
  "country_of_origin": {"value": "CN", "confidence": 0.99, "review_required": false},
  "line_items": [
    {
      "hts_code": {"value": "6204.62.4020", "confidence": 0.97, "review_required": false},
      "entered_value": {"value": "75000", "confidence": 0.94, "review_required": false},
      "duty_rate": {"value": "25.0%", "confidence": 0.88, "review_required": false}
    }
  ],
  "review_required_count": 3
}
`

**Business Rules:** BR-010 - fields < 0.80 confidence marked review_required

**Access Control:**
- Guest: session_id must match
- Authenticated user: user_id must match OR is_admin
- Admin: can see any document

**Side Effects:**
- DB: SELECT documents WHERE id=

**Error Cases:**
- 404 Job not found: No Document with this ID
- 403 Access denied: session_id mismatch, user doesn't own, and not admin

---

### 2.3 PATCH /api/v1/documents/{job_id}/fields - Save User Corrections

**Auth:** Same as GET /status
**Rate Limit:** 60/minute

**Request:**
- job_id: uuid (path)
- Body: JSON object {field_name: value, ...}

**Request Body Example:**
`json
{
  "entry_number": "001-2025-99999",
  "importer_name": "ACME Manufacturing",
  "line_items[0].hts_code": "6204.62.9900"
}
`

**Response (200):**
- job_id: uuid
- corrections_applied: int (count of corrections merged)
- merged_fields: object (flattened view of OCR + corrections)

**Precondition:** status must be "completed" or "review_required" (409 JOB_NOT_READY if not)

**Side Effects:**
- DB: UPDATE documents SET corrections={...} WHERE id=

**Error Cases:**
- 404: Document not found
- 403: Access denied (same as GET /status)
- 409 JOB_NOT_READY: Status not completed/review_required

---

### 2.4 POST /api/v1/documents/{job_id}/calculate - Trigger Calculation

**Auth:** Same as GET /status
**Rate Limit:** 20/minute

**Request:**
- job_id: uuid (path)
- X-Idempotency-Key: str (optional)

**Response (202 Accepted):**
- calculation_id: uuid (Calculation.id for polling results)

**Precondition:** status must be "completed" or "review_required"

**Business Rules Applied:** All BR-001 through BR-011

- BR-001: IEEPA rate lookup (CN-only, non-CN → )
- BR-002: MFN base tariff = entered_value × mfn_rate
- BR-003: S301 tariff = entered_value × s301_rate
- BR-004: S232 tariff (steel/aluminium only) = entered_value × s232_rate
- BR-005: MPF = total_entered_value × 0.003464%, floor=.71, cap=.62
- BR-006: HMF = total_entered_value × 0.00125% (vessel only, air=)
- BR-007: Refund pathway based on days_elapsed:
  - ≤15 days → "PSC"
  - 16-180 days → "PROTEST"
  - >180 days → "INELIGIBLE"
- BR-008: Estimated refund = Σ IEEPA amounts (no MFN/S301/S232/MPF/HMF)
- BR-009: Tariff rate lookup: WHERE hts= AND country IN (, '*') AND tariff_type= AND effective_from≤ AND (effective_to IS NULL OR effective_to≥)
- BR-011: CalculationAudit row created (immutable append-only)

**Side Effects:**
- DB: INSERT Calculation (status='calculating')
- DB: Multiple SELECT tariff_rates (one per line/tariff_type combo)
- DB: INSERT CalculationAudit (immutable snapshot)
- DB: UPDATE Calculation (status='completed', duty_components, total_duty, estimated_refund, refund_pathway)
- Redis: GET/SET tariff:{hts}:{cc}:{type}:{date} (cache lookup/store)

**Idempotency:** If Calculation exists for this document with status='completed' and non-zero duties, return existing calculation_id

**Error Cases:**
- 404: Document not found
- 403: Access denied
- 409 JOB_NOT_READY: Status not completed/review_required
- 422: Cannot parse document fields
- 500: Calculation engine error

---

## 3. RESULTS ENDPOINT

### 3.1 GET /api/v1/results/{calculation_id} - Get Calculation Result

**Auth:** None (public)
**Rate Limit:** 60/minute

**Request:**
- calculation_id: uuid (path)

**Response (200):**
`json
{
  "success": true,
  "data": {
    "calculation_id": "uuid",
    "entry_number": "001-2025-12345",
    "filer_code": "123456789",
    "summary_date": "2025-02-28",
    "import_date": "2025-02-28",
    "bl_number": "CONT-2025-001",
    "country_of_origin": "CN",
    "port_of_entry": "2704",
    "importer_name": "ACME Corp",
    "mode_of_transport": "vessel",
    "total_duty": 82187.50,
    "estimated_refund": 37500.00,
    "refund_pathway": "PSC",
    "days_elapsed": 5,
    "calculated_at": "2025-03-04T10:30:00Z",
    "tariff_lines": [
      {
        "tariff_type": "MFN",
        "rate": 0.2,
        "amount": 30000.00,
        "refundable": false
      },
      {
        "tariff_type": "IEEPA",
        "rate": 0.25,
        "amount": 37500.00,
        "refundable": true
      },
      {
        "tariff_type": "S301",
        "rate": 0.0,
        "amount": 0.00,
        "refundable": false
      },
      {
        "tariff_type": "S232",
        "rate": 0.0,
        "amount": 0.00,
        "refundable": false
      },
      {
        "tariff_type": "MPF",
        "rate": 0.003464,
        "amount": 520.00,
        "refundable": false
      },
      {
        "tariff_type": "HMF",
        "rate": 0.00125,
        "amount": 187.50,
        "refundable": false
      }
    ],
    "line_duty_components": [
      {
        "hts_code": "6204.62.4020",
        "tariff_type": "MFN",
        "rate": 0.2,
        "amount": 15000.00,
        "refundable": false
      },
      {
        "hts_code": "6204.62.4020",
        "tariff_type": "IEEPA",
        "rate": 0.25,
        "amount": 18750.00,
        "refundable": true
      }
    ]
  },
  "error": null,
  "meta": null
}
`

**Business Rules:** Only IEEPA is refundable (marked refundable=true)

**Side Effects:**
- DB: SELECT calculations WHERE id=
- DB: SELECT documents WHERE id=.document_id (for supplementary fields)

**Error Cases:**
- 404 Result not found: No Calculation with this ID
- 202 Calculation in progress: Status in (pending, calculating)
- 500 Calculation failed: Status = failed

---

## 4. HEALTH ENDPOINT

### GET /health

**Auth:** None
**Response (200):** {"status": "ok"}

---

## ERROR RESPONSE ENVELOPE

All endpoints follow this format:
`json
{
  "success": boolean,
  "data": null | object,
  "error": null | {"code": "ERROR_CODE", "message": "description"},
  "meta": null
}
`

HTTP Status Codes:
- 200: OK
- 202: Accepted (async queued)
- 400: Bad request
- 401: Unauthorized
- 403: Forbidden
- 404: Not found
- 409: Conflict
- 413: Request entity too large
- 415: Unsupported media type
- 422: Unprocessable entity
- 429: Too many requests
- 500: Internal server error

---

## RATE LIMITS

| Endpoint | Limit |
|----------|-------|
| POST /auth/token | 5/minute |
| POST /auth/refresh | 60/minute |
| POST /auth/logout | 60/minute |
| POST /documents/upload | 10/hour |
| GET /documents/{job_id}/status | 60/minute |
| PATCH /documents/{job_id}/fields | 60/minute |
| POST /documents/{job_id}/calculate | 20/minute |
| GET /results/{calculation_id} | 60/minute |

Rate limit hit → 429 Too Many Requests

---

## KEY CALCULATIONS

### MPF (BR-005)
`
raw = total_entered_value × 0.003464
mpf = max(.71, min(.62, raw))
`

### HMF (BR-006)
`
if mode_of_transport == 'vessel':
  hmf = total_entered_value × 0.00125
else:
  hmf = .00
`

### Refund Pathway (BR-007)
`
days = today - summary_date
if days ≤ 15: "PSC"
elif days ≤ 180: "PROTEST"
else: "INELIGIBLE"
`

### Estimated Refund (BR-008)
`
= sum(ieepa_duty_amount for all line items)
`

### Total Duty
`
= sum(mfn + ieepa + s301 + s232 for all lines) + mpf + hmf
`

---

## AUTHENTICATION FLOWS

### Guest Flow (No Login)
1. POST /upload (no auth) → session_id cookie + job_id
2. GET /status (session_id cookie) → polling OCR
3. PATCH /fields (session_id cookie) → corrections
4. POST /calculate (session_id cookie) → trigger calc
5. GET /results/{id} (no auth) → public results

### Registered User Flow
1. POST /auth/token (email + password) → access_token + refresh_token cookie
2. POST /upload (Bearer {token}) → user_id associated
3. GET /status (Bearer {token}) → polling
4. PATCH /fields (Bearer {token}) → corrections
5. POST /calculate (Bearer {token}) → calculate
6. POST /auth/refresh (refresh_token cookie) → rotate tokens
7. GET /results/{id} (no auth) → public
8. POST /auth/logout (Bearer {token}) → revoke refresh_token

---

## DETAILED REQUEST/RESPONSE EXAMPLES

### POST /auth/token
**Request:**
`json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
`

**Response (200):**
`json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer"
  },
  "error": null,
  "meta": null
}
`
Headers: Set-Cookie: refresh_token=<JWT>; HttpOnly; Secure; SameSite=Strict; Max-Age=604800

### POST /documents/upload
**Request (multipart/form-data):**
`
file: [binary PDF content]
privacy_accepted: true
X-Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
`

**Response (202):**
`json
{
  "success": true,
  "data": {
    "job_id": "123e4567-e89b-12d3-a456-426614174000",
    "status": "queued",
    "expires_at": "2025-03-05T14:30:00Z"
  },
  "error": null,
  "meta": null
}
`
Headers: Set-Cookie: session_id=550e8400...; HttpOnly; Secure; SameSite=Strict; Max-Age=86400

### POST /documents/{job_id}/calculate
**Request:**
`
job_id: 123e4567-e89b-12d3-a456-426614174000
`

**Response (202):**
`json
{
  "success": true,
  "data": {
    "calculation_id": "987e6543-a89b-76d3-c456-123456789abc"
  },
  "error": null,
  "meta": null
}
`

### GET /results/{calculation_id}
**Response (200):**
`json
{
  "success": true,
  "data": {
    "calculation_id": "987e6543-a89b-76d3-c456-123456789abc",
    "entry_number": "001-2025-12345",
    "country_of_origin": "CN",
    "total_duty": 82187.50,
    "estimated_refund": 37500.00,
    "refund_pathway": "PSC",
    "days_elapsed": 5,
    "tariff_lines": [...]
  },
  "error": null,
  "meta": null
}
`

---

## SECURITY FEATURES SUMMARY

- JWT HS256 (15-min access, 7-day refresh)
- Refresh token rotation (old token blacklisted in Redis)
- HttpOnly, Secure, SameSite=Strict cookies
- Bcrypt password hashing (work factor ≥ 12)
- Magic bytes file validation (not extension-based)
- Fernet AES-256 file encryption at rest
- Session-based access for guests
- Role-based access (user | admin)
- Rate limiting (slowapi, Redis backend)
- CORS support with configurable origins
- Security headers (CSP, HSTS, X-Frame-Options, etc.)

---

## TEST CASE GENERATION GUIDE

### Auth Tests
✓ Login: valid credentials → 200
✓ Login: invalid email → 401 INVALID_CREDENTIALS
✓ Login: wrong password → 401 INVALID_CREDENTIALS
✓ Login: email not verified → 403 EMAIL_NOT_VERIFIED
✓ Refresh: valid token → 200 new tokens
✓ Refresh: expired token → 401 REFRESH_TOKEN_EXPIRED
✓ Refresh: revoked token → 401 REFRESH_TOKEN_REVOKED
✓ Logout: valid JWT → 200, cookie expires

### Upload Tests
✓ Upload: valid PDF → 202, job_id
✓ Upload: valid JPEG → 202
✓ Upload: valid PNG → 202
✓ Upload: file too large → 413
✓ Upload: invalid MIME (magic bytes) → 415
✓ Upload: no privacy_accepted → 400
✓ Upload: idempotent (repeat X-Idempotency-Key) → 202 same job_id
✓ Upload: guest → 202, session_id cookie
✓ Upload: authenticated → 202, user_id associated

### Document Tests
✓ Status: while processing → 200, status='processing'
✓ Status: after completion → 200, extracted_fields present
✓ Status: guest with correct session_id → 200
✓ Status: guest with wrong session_id → 403
✓ Status: user owns document → 200
✓ Status: user doesn't own → 403
✓ Status: admin can see any → 200
✓ Patch: valid corrections → 200, merged_fields
✓ Patch: before OCR complete → 409 JOB_NOT_READY

### Calculation Tests
✓ Calculate: BR-001 (IEEPA, CN-only) → verified in result
✓ Calculate: BR-002 (MFN) → verified in result
✓ Calculate: BR-005 (MPF boundaries):
  - entry_value < floor → .71
  - entry_value > cap → .62
  - entry_value in range → normal
✓ Calculate: BR-006 (HMF vessel-only):
  - vessel → HMF calculated
  - air → HMF = 
✓ Calculate: BR-007 (pathway boundaries):
  - days=15 → "PSC"
  - days=16 → "PROTEST"
  - days=180 → "PROTEST"
  - days=181 → "INELIGIBLE"
✓ Calculate: BR-008 (estimated_refund = IEEPA only)
✓ Calculate: BR-009 (tariff rate lookup with date range)
✓ Calculate: BR-011 (audit trail created)

### Results Tests
✓ Results: calculation completed → 200, full data
✓ Results: calculation pending → 202
✓ Results: calculation failed → 500
✓ Results: not found → 404
✓ Results: refundable=true only for IEEPA
✓ Results: public (no auth required)

---
