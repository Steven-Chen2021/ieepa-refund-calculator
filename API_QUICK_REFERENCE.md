# API QUICK REFERENCE TABLE

## Endpoint Matrix

| # | Method | Path | Purpose | Auth | Rate Limit | 200? | 202? | Errors |
|----|--------|------|---------|------|------------|------|------|--------|
| 1 | POST | /api/v1/auth/token | Login | None | 5/min | ✓ | | 401, 403, 429 |
| 2 | POST | /api/v1/auth/refresh | Rotate token | Cookie | 60/min | ✓ | | 401, 429 |
| 3 | POST | /api/v1/auth/logout | Logout | JWT | 60/min | ✓ | | 401, 429 |
| 4 | POST | /api/v1/documents/upload | Upload file | Opt | 10/hr | | ✓ | 400, 413, 415, 422, 429 |
| 5 | GET | /api/v1/documents/{id}/status | Poll OCR | Ses/JWT | 60/min | ✓ | | 403, 404 |
| 6 | PATCH | /api/v1/documents/{id}/fields | Save corrections | Ses/JWT | 60/min | ✓ | | 403, 404, 409 |
| 7 | POST | /api/v1/documents/{id}/calculate | Trigger calc | Ses/JWT | 20/min | | ✓ | 403, 404, 409, 422, 500 |
| 8 | GET | /api/v1/results/{id} | Get results | None | 60/min | ✓ | | 202, 404, 500 |

Legend: Ses=session_id cookie, JWT=Bearer token, Opt=Optional

---

## Request/Response Summary

| Endpoint | Request Type | Request Body | Response Status | Response Body |
|----------|--------------|--------------|-----------------|-----------------|
| POST /auth/token | JSON | {email, password} | 200 | {access_token, token_type} |
| POST /auth/refresh | Cookie | (refresh_token) | 200 | {access_token, token_type} |
| POST /auth/logout | JWT Header | (Authorization) | 200 | {success, data: {message}} |
| POST /documents/upload | multipart/form-data | file, privacy_accepted, X-Idempotency-Key | 202 | {job_id, status, expires_at} |
| GET /documents/{id}/status | - | - | 200 | {job_id, status, extracted_fields?, ocr_provider?, ocr_confidence?} |
| PATCH /documents/{id}/fields | JSON | {field_name: value, ...} | 200 | {job_id, corrections_applied, merged_fields} |
| POST /documents/{id}/calculate | - | - | 202 | {calculation_id} |
| GET /results/{id} | - | - | 200/202/500 | {calculation_id, tariff_lines[], line_duty_components[], estimated_refund, ...} |

---

## Business Rules Quick Reference

| BR | Name | Formula/Logic | Notes |
|----|------|----------------|-------|
| BR-001 | IEEPA Applicability | CN-only; non-CN →  | Only if country_of_origin=='CN' |
| BR-002 | MFN | entered_value × mfn_rate | Base tariff for all goods |
| BR-003 | Section 301 | entered_value × s301_rate | Additional tariff (trade war) |
| BR-004 | Section 232 | entered_value × s232_rate | Steel/aluminium only; applicable=False if not found |
| BR-005 | MPF | total_ev × 0.003464%; floor=.71; cap=.62 | Merchandise Processing Fee |
| BR-006 | HMF | total_ev × 0.00125% (vessel only); air= | Harbor Maintenance Fee |
| BR-007 | Refund Pathway | if days≤15: PSC; elif days≤180: PROTEST; else: INELIGIBLE | Based on summary_date |
| BR-008 | Estimated Refund | Σ IEEPA duties only | MFN/S301/S232/MPF/HMF not refundable |
| BR-009 | Rate Lookup | WHERE (hts, country, type, date_range) + Redis cache | Cache TTL=3600s |
| BR-010 | OCR Confidence | confidence < 0.80 → review_required=true | < 0.50 entire doc → UNRECOGNISED |
| BR-011 | Audit Trail | CalculationAudit (immutable, append-only) | Never UPDATE/DELETE audit table |

---

## Database Model Quick Reference

### users
`
id (UUID, PK)
email (VARCHAR, unique)
hashed_password (bcrypt)
role ('user' | 'admin')
is_active (bool)
is_email_verified (bool)
created_at, updated_at (timestamps)
`

### documents
`
id (UUID, PK) ← job_id
user_id (UUID, nullable) ← FK users
session_id (VARCHAR, nullable) ← guest session
idempotency_key (VARCHAR, unique)
status ('queued' | 'processing' | 'completed' | 'review_required' | 'failed')
extracted_fields (JSONB) ← OCR output
corrections (JSONB) ← user corrections
expires_at (timestamp) ← 24h TTL
created_at, updated_at
`

### calculations
`
id (UUID, PK)
document_id (UUID) ← FK documents
status ('pending' | 'calculating' | 'completed' | 'failed')
entry_number, summary_date, country_of_origin, mode_of_transport, total_entered_value
duty_components (JSONB) ← array of DutyComponent
total_duty, estimated_refund (NUMERIC 14,2)
refund_pathway ('PSC' | 'PROTEST' | 'INELIGIBLE')
days_since_summary (int)
pathway_rationale (text)
created_at, updated_at
`

### calculation_audit (immutable)
`
id (UUID, PK)
calculation_id (UUID) ← FK calculations
snapshot (JSONB) ← point-in-time copy of entire result
created_at (timestamp, no updated_at)
`

### tariff_rates
`
id (UUID, PK)
hts_code (VARCHAR)
country_code (VARCHAR) ← ISO alpha-2 or '*'
tariff_type ('MFN' | 'IEEPA' | 'S301' | 'S232')
rate_pct (NUMERIC 8,4)
effective_from (date), effective_to (date, nullable)
source_ref (VARCHAR) ← regulatory reference
updated_by (UUID)
created_at, updated_at
`

---

## JWT Token Structure

### Access Token
`
Header: {"alg": "HS256", "typ": "JWT"}
Payload: {
  "sub": "<user_id>",
  "role": "user" | "admin",
  "email": "<email>",
  "iat": <timestamp>,
  "exp": <timestamp> (iat + 15 min)
}
Secret: settings.JWT_SECRET_KEY
`

### Refresh Token
`
Header: {"alg": "HS256", "typ": "JWT"}
Payload: {
  "sub": "<user_id>",
  "type": "refresh",
  "jti": "<UUID>",
  "iat": <timestamp>,
  "exp": <timestamp> (iat + 7 days)
}
Secret: settings.JWT_SECRET_KEY
`

Refresh token JTI added to Redis blacklist: t_blacklist:{jti}
TTL = remaining_seconds_until_exp

---

## Redis Cache Keys

| Key Pattern | TTL | Purpose |
|-------------|-----|---------|
| rt_blacklist:{jti} | remaining_token_lifetime | Revoked refresh token JTI (max 7 days) |
| tariff:{hts}:{cc}:{type}:{YYYY-MM-DD} | 3600 | Cached tariff rate lookup |

---

## Common Error Codes

| Code | HTTP | Endpoint | Message |
|------|------|----------|---------|
| INVALID_CREDENTIALS | 401 | POST /auth/token | Email not found or password mismatch |
| EMAIL_NOT_VERIFIED | 403 | POST /auth/token | User inactive or email not verified |
| REFRESH_TOKEN_MISSING | 401 | POST /auth/refresh | No refresh_token cookie |
| REFRESH_TOKEN_REVOKED | 401 | POST /auth/refresh | Token found in Redis blacklist |
| REFRESH_TOKEN_EXPIRED | 401 | POST /auth/refresh | JWT exp in past or malformed |
| USER_NOT_FOUND | 401 | POST /auth/refresh | User ID from JWT not in DB |
| PRIVACY_NOT_ACCEPTED | 400 | POST /documents/upload | privacy_accepted != "true" |
| FILE_TOO_LARGE | 413 | POST /documents/upload | File > 20 MB |
| UNSUPPORTED_FILE_TYPE | 415 | POST /documents/upload | Magic bytes not PDF/JPEG/PNG |
| Job not found | 404 | GET /documents/{id}/status | Document not in DB |
| Access denied | 403 | GET /documents/{id}/status | session_id or user_id mismatch |
| JOB_NOT_READY | 409 | PATCH /documents/{id}/fields | Status not in (completed, review_required) |
| Cannot parse document fields | 422 | POST /documents/{id}/calculate | EntryInput parsing failed |
| Calculation engine error | 500 | POST /documents/{id}/calculate | Exception in calculate_entry() |
| Result not found | 404 | GET /api/v1/results/{id} | Calculation not in DB |
| Calculation in progress | 202 | GET /api/v1/results/{id} | Status in (pending, calculating) |
| Calculation failed | 500 | GET /api/v1/results/{id} | Status == failed |
| Rate limit exceeded | 429 | Any | Too many requests per endpoint |

---

## File Upload Validation

Order of validation:
1. ✓ privacy_accepted == "true" (exact match, case-insensitive check)
2. ✓ X-Idempotency-Key present (required header)
3. ✓ Check if idempotency_key already used → return existing 202
4. ✓ Content-Type header pre-check (fast-fail)
5. ✓ File chunked read with 20 MB limit enforcement
6. ✓ Magic bytes validation (python-magic)

Allowed MIME types (by magic bytes, not extension):
- application/pdf
- image/jpeg
- image/png

---

## Session Management

### Guest Session
- Created on first POST /upload (if no auth)
- Stored in httpOnly cookie: session_id
- Lifetime: 24 hours
- Used for GET /status, PATCH /fields, POST /calculate
- Expires after 24 hours or manual logout

### Authenticated Session
- Created on POST /auth/token (email + password)
- Access token in request body (store in memory, NOT localStorage)
- Refresh token in httpOnly cookie: efresh_token
- Access token TTL: 15 minutes
- Refresh token TTL: 7 days
- On POST /auth/refresh: old refresh_token blacklisted, new tokens issued
- On POST /auth/logout: refresh_token cookie expires, JTI blacklisted

---

## OCR Processing (Async Task)

### Input
- Document.id (job_id)
- Document.encrypted_file_path (encrypted file on disk)

### Processing
1. Decrypt file from disk
2. Primary: Google Document AI (Form Parser)
3. Fallback (if primary fails or confidence < 0.50): pytesseract
4. Extract ≥20 named fields (entry_number, summary_date, country_of_origin, etc.)
5. Attach confidence score (0.0-1.0) to each field

### Output
- Document.extracted_fields (JSONB) ← OCR output
- Document.ocr_provider ← "google_docai" | "tesseract"
- Document.ocr_confidence ← overall confidence
- Document.status:
  - "completed" if all fields valid
  - "review_required" if any field confidence < 0.80
  - "failed" if overall confidence < 0.50 or error

### Timeout
- 30 seconds max; if exceeded → status = "failed"

---

## Calculation Engine (Synchronous)

### Input
- Document.id (job_id)
- Document.extracted_fields + Document.corrections

### Processing (per line item + entry-level)
1. Parse EntryInput from document
2. For each line item:
   - Calc MFN (BR-002): tariff_rate lookup + enter_value × rate
   - Calc IEEPA (BR-001): CN-only; tariff_rate lookup + enter_value × rate
   - Calc S301 (BR-003): tariff_rate lookup + enter_value × rate
   - Calc S232 (BR-004): tariff_rate lookup + enter_value × rate; applicable only if rate found
3. Entry-level calculations:
   - Calc MPF (BR-005): total_ev × 0.003464%; apply floor/cap
   - Calc HMF (BR-006): vessel=yes? total_ev × 0.00125%; else 
   - Calc Refund Pathway (BR-007): days_elapsed logic
   - Calc Estimated Refund (BR-008): Σ IEEPA only
4. Create CalculationAudit (BR-011): snapshot of all inputs/outputs
5. Persist results to Calculation row

### Output
- Calculation.duty_components (array of DutyComponent)
- Calculation.total_duty
- Calculation.estimated_refund
- Calculation.refund_pathway
- Calculation.days_since_summary
- Calculation.pathway_rationale
- Calculation.status = "completed"
- CalculationAudit row (immutable)

---

## Dependency Injection

### FastAPI Dependencies

`python
# JWT authentication
CurrentUser: TokenPayload (Bearer JWT required, raises 401)
OptionalUser: TokenPayload | None (Bearer JWT optional)
AdminUser: TokenPayload + role=='admin' (raises 403 if not admin)

# Database
DBSession: AsyncSession (SQLAlchemy async session)

# Redis
RedisClient: aioredis.Redis

# Request metadata
Request: FastAPI Request object
Response: FastAPI Response object

# Cookies
session_id_cookie: str | None (from Cookie("session_id"))
refresh_token_cookie: str | None (from Cookie("refresh_token"))

# Headers
X-Idempotency-Key: str | None (from Header)
`

---

## Performance Considerations

- Tariff rate lookup cached in Redis (TTL=3600s)
- Cache invalidated on any admin rate update (DEL key)
- Calculation synchronous in-process (not async)
- Document upload async (Celery, OCR task)
- Database queries use indexes on:
  - users.email
  - documents.user_id, session_id, idempotency_key
  - calculations.document_id
  - tariff_rates.hts_code, country_code, tariff_type
- Rate limiting: slowapi with Redis backend (db /1)
- File cleanup: Celery Beat hourly task (deletes expired docs)

---

