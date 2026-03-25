# API INVENTORY INDEX

## Generated Documentation Files

This folder now contains three comprehensive API inventory documents for the RefundCal FastAPI backend:

### 1. **API_INVENTORY.md** (16.7 KB)
**Primary comprehensive reference for all endpoints**

Contains:
- Detailed specifications for all 8 endpoints
- Complete request/response field documentation
- Business rule mappings (BR-001 through BR-011)
- Side effects and database operations for each endpoint
- Comprehensive error paths with HTTP status codes and error messages
- Authentication requirements and access control logic
- Rate limiting details
- Calculated field formulas
- Authentication flows (guest vs. registered user)
- Database model quick reference
- Redis cache keys and TTLs
- Security features summary
- Test case generation checklist

**Best For:** Complete API reference, writing detailed test specifications, understanding all edge cases

---

### 2. **API_QUICK_REFERENCE.md** (11.2 KB)
**Quick lookup tables and summaries**

Contains:
- Endpoint matrix table (method, path, auth, rate limit, status codes, errors)
- Request/response summary matrix
- Business rules quick reference table
- Database model quick reference with key fields
- JWT token structure details
- Redis cache key patterns
- Common error codes with HTTP status
- File upload validation checklist
- Session management overview
- OCR processing flow
- Calculation engine flow
- Dependency injection summary
- Performance considerations

**Best For:** Quick lookup during development, API review meetings, design validation

---

### 3. **TEST_CASES_TEMPLATE.md** (54+ KB)
**Comprehensive test case templates and examples**

Contains:
- Test case format template
- 80+ test cases organized by module:
  - Auth module: 9 test cases (login, refresh, logout, rate limits)
  - Document module: 25+ test cases (upload, status, corrections, calculate)
  - Results module: 5 test cases
  - Rate limit tests: 2 test cases
  - Edge cases: 5 test cases
  - Security tests: 6 test cases
  - Business rule tests: 20+ integrated into document tests
- Each test case includes:
  - Test ID, title, priority, type
  - Prerequisites
  - Test steps
  - Expected results
  - Error cases
  - Boundary conditions
- Examples of:
  - Happy path tests
  - Error case tests
  - Boundary value tests
  - Security tests
  - Rate limit tests
  - Idempotency tests

**Best For:** Creating automated test suites, manual testing, QA test plan development

---

## API OVERVIEW

### Endpoints Summary

| Method | Path | Purpose | Auth | Status |
|--------|------|---------|------|--------|
| POST | /api/v1/auth/token | Login | None | 200 |
| POST | /api/v1/auth/refresh | Rotate refresh token | Cookie | 200 |
| POST | /api/v1/auth/logout | Logout | JWT | 200 |
| POST | /api/v1/documents/upload | Upload CBP 7501 | Optional | 202 |
| GET | /api/v1/documents/{id}/status | Poll OCR status | Session/JWT | 200 |
| PATCH | /api/v1/documents/{id}/fields | Save corrections | Session/JWT | 200 |
| POST | /api/v1/documents/{id}/calculate | Trigger calculation | Session/JWT | 202 |
| GET | /api/v1/results/{id} | Get results | None | 200/202/500 |

---

## KEY TECHNICAL DETAILS

### Authentication
- **Access Token:** HS256 JWT, 15-minute TTL
- **Refresh Token:** HS256 JWT, 7-day TTL, HttpOnly cookie
- **Token Rotation:** On POST /auth/refresh, old token blacklisted in Redis
- **Access Control:** Session-based for guests, JWT for registered users, role-based for admin

### File Upload
- **Formats:** PDF, JPEG, PNG (validated by magic bytes, not extension)
- **Max Size:** 20 MB
- **Validation:** Content-Type pre-check → Magic bytes → Size limit
- **Storage:** Encrypted with Fernet AES-256 before storage
- **TTL:** 24 hours (auto-cleanup)

### Calculation Engine
- **Synchronous:** In-process, not async
- **Business Rules:** BR-001 through BR-011 applied
- **Main Calculations:**
  - MFN (all goods): entered_value × mfn_rate
  - IEEPA (CN only): entered_value × ieepa_rate
  - S301 (trade war): entered_value × s301_rate
  - S232 (steel/aluminium): entered_value × s232_rate
  - MPF: total × 0.3464%, floor=.71, cap=.62
  - HMF (vessel only): total × 0.125%, air=
  - Pathway: PSC (≤15d) | PROTEST (16-180d) | INELIGIBLE (>180d)
- **Refund Amount:** IEEPA duties only (non-refundable: MFN, S301, S232, MPF, HMF)
- **Audit Trail:** Immutable append-only record (BR-011)

### Rate Limiting
- All endpoints rate-limited per IP address
- Slowapi integration with Redis backend (/1)
- Limits: 5/min (login) to 60/min (status/results)

### Security
- Bcrypt password hashing (work factor ≥ 12)
- Refresh token rotation (old token blacklisted)
- HttpOnly, Secure, SameSite=Strict cookies
- CORS configurable by origin
- Security headers: CSP, HSTS, X-Frame-Options, X-Content-Type-Options
- No user enumeration (same error for "not found" and "wrong password")

---

## HOW TO USE THESE DOCUMENTS

### For API Integration Testing
1. Read **API_INVENTORY.md** sections for the endpoint you're testing
2. Review **API_QUICK_REFERENCE.md** error codes table
3. Use **TEST_CASES_TEMPLATE.md** to create specific test cases
4. Reference business rules section for expected calculations

### For Manual Testing
1. Use **API_QUICK_REFERENCE.md** endpoint matrix for quick lookup
2. Reference **TEST_CASES_TEMPLATE.md** for test steps
3. Check error codes table for expected responses

### For Test Automation
1. Copy test case format from **TEST_CASES_TEMPLATE.md**
2. Implement parametrized tests for boundary cases (MPF floor/cap, pathway boundaries)
3. Reference **API_INVENTORY.md** for exact field names and types
4. Use business rules section for validation logic

### For API Documentation
1. Use **API_QUICK_REFERENCE.md** endpoint matrix as reference
2. Supplement with **API_INVENTORY.md** detailed specifications
3. Include relevant error codes from quick reference

### For Development
1. **API_QUICK_REFERENCE.md** - quick lookup during coding
2. **API_INVENTORY.md** - when you need full context
3. Reference database models section when querying

---

## TEST CASE COVERAGE SUMMARY

**Endpoint Coverage:**
- ✓ POST /auth/token: 3 test cases (happy, invalid email, wrong password, unverified)
- ✓ POST /auth/refresh: 3 test cases (happy, expired, revoked)
- ✓ POST /auth/logout: 1 test case
- ✓ POST /documents/upload: 7 test cases (happy, validation errors, idempotency, file types, size)
- ✓ GET /documents/{id}/status: 7 test cases (polling, completed, review required, access control)
- ✓ PATCH /documents/{id}/fields: 2 test cases (happy, preconditions)
- ✓ POST /documents/{id}/calculate: 13 test cases (all BR-001-BR-011, idempotency)
- ✓ GET /api/v1/results/{id}: 5 test cases (completed, pending, failed, not found, public access)

**Business Rule Coverage:**
- ✓ BR-001 (IEEPA CN-only): 2 test cases (CN, non-CN)
- ✓ BR-002 (MFN): Covered in calculation tests
- ✓ BR-003 (S301): Covered in calculation tests
- ✓ BR-004 (S232): Covered in calculation tests
- ✓ BR-005 (MPF): 3 test cases (floor, cap, normal range)
- ✓ BR-006 (HMF): 2 test cases (vessel, air)
- ✓ BR-007 (Pathway): 3 test cases (PSC, PROTEST, INELIGIBLE boundaries)
- ✓ BR-008 (Estimated Refund): 1 test case
- ✓ BR-009 (Rate Lookup): Covered in calculation tests
- ✓ BR-010 (OCR Confidence): Covered in status tests
- ✓ BR-011 (Audit Trail): 1 test case

**Error Path Coverage:**
- ✓ 400 Bad Request: privacy_accepted validation
- ✓ 401 Unauthorized: All authentication endpoints
- ✓ 403 Forbidden: Access control (session/user mismatch, unverified email, admin check)
- ✓ 404 Not Found: Document/calculation not found
- ✓ 409 Conflict: Precondition failures (JOB_NOT_READY)
- ✓ 413 Request Entity Too Large: File size limit
- ✓ 415 Unsupported Media Type: Invalid file MIME
- ✓ 422 Unprocessable Entity: Parse errors, missing headers
- ✓ 429 Too Many Requests: Rate limit
- ✓ 500 Internal Server Error: Calculation engine errors

**Security Tests:**
- ✓ No user enumeration
- ✓ Constant-time password comparison
- ✓ JWT signature validation
- ✓ Token expiry enforcement
- ✓ HttpOnly cookie flags
- ✓ CORS preflight

**Additional Tests:**
- ✓ Rate limiting: 2 test cases
- ✓ Idempotency: 2 test cases
- ✓ Boundary values: 3 test cases
- ✓ Edge cases: 5 test cases

---

## QUICK START

**For New Developers:**
1. Start with **API_QUICK_REFERENCE.md** endpoint matrix
2. Then read the relevant section in **API_INVENTORY.md**
3. Check examples and error codes

**For QA Engineers:**
1. Review **TEST_CASES_TEMPLATE.md** overview
2. Create test cases using the provided templates
3. Cross-reference **API_QUICK_REFERENCE.md** error codes

**For API Consumers:**
1. Read endpoint details from **API_INVENTORY.md**
2. Review sample requests/responses in TEST_CASES_TEMPLATE.md
3. Check rate limits and auth requirements in **API_QUICK_REFERENCE.md**

---

## Document Metadata

| Document | Size | Purpose | Best For |
|----------|------|---------|----------|
| API_INVENTORY.md | 16.7 KB | Comprehensive reference | Complete specs, test design |
| API_QUICK_REFERENCE.md | 11.2 KB | Quick lookup tables | Quick answers, reviews |
| TEST_CASES_TEMPLATE.md | 54+ KB | Test case templates | Test automation, QA |

**Total:** 82+ KB of detailed API documentation

**Coverage:** 
- 8 endpoints fully documented
- 80+ test cases provided
- 11 business rules covered
- 10+ HTTP status codes explained
- 20+ error codes documented

---

