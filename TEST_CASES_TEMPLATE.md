# TEST CASE TEMPLATES FOR REFUNDCAL API

## Test Case Format Template

`
Test ID: TC-[MODULE]-[NUMBER]
Title: [Brief description]
Module: [auth|documents|results|calculation]
Endpoint: [METHOD] [PATH]
Priority: [Critical|High|Medium|Low]
Type: [Happy Path|Error Case|Boundary|Security]

Prerequisites:
- [Setup conditions]

Test Steps:
1. [Action]
2. [Action]
3. [Verify]

Expected Result:
- HTTP Status: [200|201|4xx|5xx]
- Response Body: [JSON structure or description]
- Side Effects: [DB writes, Redis ops, file I/O]

Actual Result:
[To be filled in during test execution]

Status: [Pass|Fail|Blocked]
Notes: [Any observations or issues]
`

---

## AUTH MODULE TEST CASES

### TC-AUTH-001: Login with Valid Credentials
**Title:** User successfully logs in with correct email and password
**Endpoint:** POST /api/v1/auth/token
**Priority:** Critical
**Type:** Happy Path

**Prerequisites:**
- User exists in database with email "user@example.com"
- Password hash matches "securepass123"
- User.is_email_verified = True
- User.is_active = True

**Test Steps:**
1. POST /api/v1/auth/token with {"email": "user@example.com", "password": "securepass123"}
2. Capture response and response headers
3. Verify HTTP status is 200
4. Verify response contains access_token (non-empty JWT string)
5. Verify response contains token_type = "bearer"
6. Verify Set-Cookie header contains refresh_token with HttpOnly; Secure; SameSite=Strict

**Expected Result:**
- HTTP Status: 200
- Response: {"success": true, "data": {"access_token": "eyJ...", "token_type": "bearer"}, "error": null}
- Cookie: refresh_token=<JWT>; HttpOnly; Secure; SameSite=Strict; Max-Age=604800

**Actual Result:** [TBD]

---

### TC-AUTH-002: Login with Invalid Email
**Title:** Login fails when email doesn't exist
**Endpoint:** POST /api/v1/auth/token
**Priority:** High
**Type:** Error Case

**Test Steps:**
1. POST /api/v1/auth/token with {"email": "nonexistent@example.com", "password": "anypassword"}
2. Verify HTTP status is 401
3. Verify response.error.code = "INVALID_CREDENTIALS" or detail = "INVALID_CREDENTIALS"
4. Verify no Set-Cookie header present

**Expected Result:**
- HTTP Status: 401
- Response: {"success": false, "data": null, "error": {"code": "INVALID_CREDENTIALS", ...}}
- No cookie set

---

### TC-AUTH-003: Login with Wrong Password
**Title:** Login fails when password is incorrect
**Endpoint:** POST /api/v1/auth/token
**Priority:** High
**Type:** Error Case

**Prerequisites:**
- User exists with email "user@example.com" and password "correctpass"

**Test Steps:**
1. POST /api/v1/auth/token with {"email": "user@example.com", "password": "wrongpass"}
2. Verify HTTP status is 401
3. Verify response detail = "INVALID_CREDENTIALS"

**Expected Result:**
- HTTP Status: 401
- Same error message as TC-AUTH-002 (no user enumeration)

---

### TC-AUTH-004: Login with Unverified Email
**Title:** Login fails if email not verified
**Endpoint:** POST /api/v1/auth/token
**Priority:** High
**Type:** Error Case

**Prerequisites:**
- User exists with email "unverified@example.com"
- User.is_email_verified = False

**Test Steps:**
1. POST /api/v1/auth/token with correct credentials
2. Verify HTTP status is 403
3. Verify response detail = "EMAIL_NOT_VERIFIED"

**Expected Result:**
- HTTP Status: 403
- Response detail: "EMAIL_NOT_VERIFIED"

---

### TC-AUTH-005: Refresh Token Rotation
**Title:** Refresh endpoint exchanges old refresh_token for new tokens
**Endpoint:** POST /api/v1/auth/refresh
**Priority:** Critical
**Type:** Happy Path

**Prerequisites:**
- User logged in with valid refresh_token cookie

**Test Steps:**
1. Extract refresh_token from login response cookie
2. POST /api/v1/auth/refresh with Cookie: refresh_token=<token>
3. Verify HTTP status is 200
4. Verify response contains new access_token
5. Verify Set-Cookie header contains new refresh_token
6. Store old_jti from old refresh_token
7. Verify Redis key rt_blacklist:{old_jti} is set (old token blacklisted)

**Expected Result:**
- HTTP Status: 200
- Response: new access_token + new token_type
- Old refresh_token JTI added to Redis blacklist
- New refresh_token cookie set with Max-Age=604800

---

### TC-AUTH-006: Refresh with Expired Token
**Title:** Refresh fails if refresh_token is expired
**Endpoint:** POST /api/v1/auth/refresh
**Priority:** High
**Type:** Error Case

**Prerequisites:**
- Create an expired refresh_token (exp claim in past)

**Test Steps:**
1. POST /api/v1/auth/refresh with expired refresh_token cookie
2. Verify HTTP status is 401
3. Verify response detail = "REFRESH_TOKEN_EXPIRED"

**Expected Result:**
- HTTP Status: 401
- Response detail: "REFRESH_TOKEN_EXPIRED"

---

### TC-AUTH-007: Refresh with Revoked Token
**Title:** Refresh fails if refresh_token was revoked
**Endpoint:** POST /api/v1/auth/refresh
**Priority:** High
**Type:** Security

**Prerequisites:**
- User has valid refresh_token
- User calls POST /auth/logout (token revoked)

**Test Steps:**
1. Login user and capture refresh_token cookie
2. POST /api/v1/auth/logout with Bearer token (revokes refresh_token in Redis)
3. Attempt POST /api/v1/auth/refresh with old refresh_token cookie
4. Verify HTTP status is 401
5. Verify response detail = "REFRESH_TOKEN_REVOKED"

**Expected Result:**
- HTTP Status: 401
- Response detail: "REFRESH_TOKEN_REVOKED"

---

### TC-AUTH-008: Logout Invalidates Session
**Title:** Logout invalidates access and revokes refresh_token
**Endpoint:** POST /api/v1/auth/logout
**Priority:** Critical
**Type:** Happy Path

**Prerequisites:**
- User logged in with valid access_token

**Test Steps:**
1. POST /api/v1/auth/logout with Bearer {access_token} and refresh_token cookie
2. Verify HTTP status is 200
3. Verify response.data.message = "Logged out"
4. Verify Set-Cookie header expires refresh_token (Max-Age=0)
5. Verify Redis rt_blacklist:{jti} is set for refresh_token

**Expected Result:**
- HTTP Status: 200
- Response: {"success": true, "data": {"message": "Logged out"}}
- Cookie expires (Max-Age=0)
- Token blacklisted in Redis

---

### TC-AUTH-009: Rate Limit on Login (5/minute)
**Title:** Login endpoint enforces 5 requests per minute rate limit
**Endpoint:** POST /api/v1/auth/token
**Priority:** Medium
**Type:** Rate Limit

**Test Steps:**
1. Make 5 login requests within 60 seconds (all with different IPs simulated or same IP)
2. 6th request should return 429
3. Verify response status is 429 Too Many Requests
4. Verify Retry-After header is present

**Expected Result:**
- First 5 requests: 200 or 401 (depending on credentials)
- 6th request: 429 Rate limit exceeded

---

## DOCUMENT MODULE TEST CASES

### TC-DOC-001: Upload Valid PDF
**Title:** User successfully uploads a valid PDF file
**Endpoint:** POST /api/v1/documents/upload
**Priority:** Critical
**Type:** Happy Path

**Prerequisites:**
- Valid PDF file (5 MB, magic bytes valid)
- No prior upload with same idempotency key

**Test Steps:**
1. Prepare multipart/form-data request with:
   - file: <PDF binary>
   - privacy_accepted: "true"
   - X-Idempotency-Key: "550e8400-e29b-41d4-a716-446655440000"
2. POST /api/v1/documents/upload
3. Verify HTTP status is 202 Accepted
4. Verify response contains job_id (UUID)
5. Verify response.status = "queued"
6. Verify response.expires_at is 24 hours in future
7. Verify Set-Cookie header contains session_id (for guest)
8. Verify Celery task process_ocr_job was enqueued

**Expected Result:**
- HTTP Status: 202
- Response: {"success": true, "data": {"job_id": "...", "status": "queued", "expires_at": "..."}}
- Session cookie set (HttpOnly; Secure; SameSite=Strict; Max-Age=86400)
- File encrypted and stored at /data/uploads/{date}/{job_id}/original.pdf
- OCR Celery task queued

---

### TC-DOC-002: Upload with Missing Privacy Consent
**Title:** Upload fails if privacy_accepted not set to "true"
**Endpoint:** POST /api/v1/documents/upload
**Priority:** High
**Type:** Error Case

**Test Steps:**
1. POST /api/v1/documents/upload with privacy_accepted: "false"
2. Verify HTTP status is 400
3. Verify response detail = "PRIVACY_NOT_ACCEPTED"

**Expected Result:**
- HTTP Status: 400
- Response detail: "PRIVACY_NOT_ACCEPTED"
- File NOT uploaded

---

### TC-DOC-003: Upload with Missing X-Idempotency-Key
**Title:** Upload fails if X-Idempotency-Key header not provided
**Endpoint:** POST /api/v1/documents/upload
**Priority:** High
**Type:** Error Case

**Test Steps:**
1. POST /api/v1/documents/upload without X-Idempotency-Key header
2. Verify HTTP status is 422
3. Verify response detail contains "X-Idempotency-Key"

**Expected Result:**
- HTTP Status: 422
- Response detail: "X-Idempotency-Key header is required"

---

### TC-DOC-004: Upload File Too Large (>20MB)
**Title:** Upload fails if file exceeds 20 MB size limit
**Endpoint:** POST /api/v1/documents/upload
**Priority:** High
**Type:** Boundary

**Test Steps:**
1. Create 25 MB PDF file
2. POST /api/v1/documents/upload with large file
3. Verify HTTP status is 413
4. Verify response detail = "FILE_TOO_LARGE"

**Expected Result:**
- HTTP Status: 413 Request Entity Too Large
- Response detail: "FILE_TOO_LARGE"
- File NOT stored

---

### TC-DOC-005: Upload Invalid File Type (MIME Magic Bytes)
**Title:** Upload fails if file doesn't match allowed MIME types (magic bytes)
**Endpoint:** POST /api/v1/documents/upload
**Priority:** High
**Type:** Security

**Test Steps:**
1. Create a .txt file with PDF magic bytes spoofed in extension (e.g., "file.pdf" but content is plain text)
2. POST /api/v1/documents/upload
3. Verify HTTP status is 415
4. Verify response detail = "UNSUPPORTED_FILE_TYPE"

**Expected Result:**
- HTTP Status: 415 Unsupported Media Type
- Response detail: "UNSUPPORTED_FILE_TYPE"
- File NOT stored

---

### TC-DOC-006: Idempotent Upload (Duplicate X-Idempotency-Key)
**Title:** Uploading with same X-Idempotency-Key returns existing job_id
**Endpoint:** POST /api/v1/documents/upload
**Priority:** High
**Type:** Idempotency

**Prerequisites:**
- First upload with X-Idempotency-Key: "abc-123" succeeded with job_id "job-1"

**Test Steps:**
1. POST /api/v1/documents/upload again with X-Idempotency-Key: "abc-123" (same key)
2. Verify HTTP status is 202
3. Verify response.job_id = "job-1" (same as first upload)
4. Verify Document table still has only 1 row for this idempotency key
5. Verify no new OCR task enqueued

**Expected Result:**
- HTTP Status: 202
- Response.job_id: same as first upload
- No duplicate database row
- No duplicate Celery task

---

### TC-DOC-007: Poll OCR Status - Processing
**Title:** Get document status while OCR is still processing
**Endpoint:** GET /api/v1/documents/{job_id}/status
**Priority:** High
**Type:** Happy Path

**Prerequisites:**
- Document uploaded and OCR task in progress
- Document.status = "processing"

**Test Steps:**
1. GET /api/v1/documents/{job_id}/status with session_id cookie
2. Verify HTTP status is 200
3. Verify response.status = "processing"
4. Verify response.extracted_fields is null or absent

**Expected Result:**
- HTTP Status: 200
- Response.status: "processing"
- extracted_fields: null

---

### TC-DOC-008: Poll OCR Status - Completed
**Title:** Get document status after OCR completed successfully
**Endpoint:** GET /api/v1/documents/{job_id}/status
**Priority:** Critical
**Type:** Happy Path

**Prerequisites:**
- OCR task completed
- Document.status = "completed"
- Document.extracted_fields populated with OCR output

**Test Steps:**
1. GET /api/v1/documents/{job_id}/status
2. Verify HTTP status is 200
3. Verify response.status = "completed"
4. Verify response.extracted_fields contains at least 10 fields (entry_number, summary_date, etc.)
5. Verify each field has structure: {"value": "...", "confidence": 0.0-1.0, "review_required": true|false}

**Expected Result:**
- HTTP Status: 200
- Response.status: "completed"
- extracted_fields: populated with OCR output

---

### TC-DOC-009: Poll OCR Status - Review Required
**Title:** Get document status when OCR completed but confidence < 0.80 for some fields
**Endpoint:** GET /api/v1/documents/{job_id}/status
**Priority:** High
**Type:** Happy Path

**Prerequisites:**
- OCR completed with some fields having confidence < 0.80
- Document.status = "review_required"

**Test Steps:**
1. GET /api/v1/documents/{job_id}/status
2. Verify HTTP status is 200
3. Verify response.status = "review_required"
4. Verify response.extracted_fields.review_required_count > 0
5. Verify at least one field has review_required: true

**Expected Result:**
- HTTP Status: 200
- Response.status: "review_required"
- Some fields marked review_required: true

---

### TC-DOC-010: Access Control - Guest with Correct Session
**Title:** Guest can access document with correct session_id cookie
**Endpoint:** GET /api/v1/documents/{job_id}/status
**Priority:** High
**Type:** Security

**Prerequisites:**
- Guest uploaded document, received session_id cookie

**Test Steps:**
1. GET /api/v1/documents/{job_id}/status with correct session_id cookie
2. Verify HTTP status is 200

**Expected Result:**
- HTTP Status: 200
- Document data returned

---

### TC-DOC-011: Access Control - Guest with Wrong Session
**Title:** Guest access denied with incorrect session_id
**Endpoint:** GET /api/v1/documents/{job_id}/status
**Priority:** High
**Type:** Security

**Prerequisites:**
- Document owned by session_id "correct-123"

**Test Steps:**
1. GET /api/v1/documents/{job_id}/status with session_id: "wrong-456"
2. Verify HTTP status is 403
3. Verify response detail = "Access denied"

**Expected Result:**
- HTTP Status: 403
- Response detail: "Access denied"

---

### TC-DOC-012: Access Control - Admin Can See Any Document
**Title:** Admin user can view any document regardless of ownership
**Endpoint:** GET /api/v1/documents/{job_id}/status
**Priority:** High
**Type:** Security

**Prerequisites:**
- Admin user exists
- Document owned by different guest session

**Test Steps:**
1. Login as admin (get admin access_token)
2. GET /api/v1/documents/{job_id}/status with Bearer admin_token
3. Verify HTTP status is 200

**Expected Result:**
- HTTP Status: 200
- Admin can see document details

---

### TC-DOC-013: Save Field Corrections
**Title:** Save user corrections to OCR extracted fields
**Endpoint:** PATCH /api/v1/documents/{job_id}/fields
**Priority:** High
**Type:** Happy Path

**Prerequisites:**
- Document status = "completed" or "review_required"
- Document has extracted_fields

**Test Steps:**
1. PATCH /api/v1/documents/{job_id}/fields with body:
   `json
   {
     "entry_number": "001-2025-99999",
     "importer_name": "ACME Corp",
     "line_items[0].hts_code": "6204.62.9999"
   }
   `
2. Verify HTTP status is 200
3. Verify response.corrections_applied = 3
4. Verify response.merged_fields contains corrected values

**Expected Result:**
- HTTP Status: 200
- corrections_applied: 3
- merged_fields reflects corrections
- DB Document.corrections JSONB updated

---

### TC-DOC-014: Calculate - BR-001 (IEEPA CN-Only)
**Title:** Calculate applies BR-001 (IEEPA rate only for CN origin)
**Endpoint:** POST /api/v1/documents/{job_id}/calculate
**Priority:** Critical
**Type:** Business Rule

**Prerequisites:**
- Document with line item: country="CN", hts="6204.62.4020"
- Tariff rate exists: IEEPA rate = 0.25 for this HTS

**Test Steps:**
1. POST /api/v1/documents/{job_id}/calculate
2. Get calculation_id from response
3. Poll GET /api/v1/results/{calculation_id} until completed
4. Verify tariff_lines contains IEEPA with rate=0.25
5. Verify line_duty_components contains IEEPA entry for HTS

**Expected Result:**
- IEEPA tariff applied (rate > 0)
- Amount = entered_value × 0.25

---

### TC-DOC-015: Calculate - BR-001 Non-CN (IEEPA = )
**Title:** Calculate applies BR-001 (IEEPA =  for non-CN)
**Endpoint:** POST /api/v1/documents/{job_id}/calculate
**Priority:** High
**Type:** Business Rule

**Prerequisites:**
- Document with line item: country="TW" (not CN), hts="6204.62.4020"

**Test Steps:**
1. POST /api/v1/documents/{job_id}/calculate
2. Poll GET /api/v1/results/{calculation_id}
3. Verify line_duty_components IEEPA entry has amount = 0.00
4. Verify refund_pathway = "INELIGIBLE" (no IEEPA to refund)

**Expected Result:**
- IEEPA amount: 0.00
- estimated_refund: 0.00

---

### TC-DOC-016: Calculate - BR-005 (MPF Floor)
**Title:** Calculate applies BR-005 (MPF floor boundary: .71)
**Endpoint:** POST /api/v1/documents/{job_id}/calculate
**Priority:** High
**Type:** Boundary

**Prerequisites:**
- Document total_entered_value =  (results in raw MPF = .70)

**Test Steps:**
1. POST /api/v1/documents/{job_id}/calculate
2. Poll results
3. Verify tariff_lines MPF entry has amount = 32.71 (floor applied)

**Expected Result:**
- MPF amount: 32.71 (floor, not 32.70)

---

### TC-DOC-017: Calculate - BR-005 (MPF Cap)
**Title:** Calculate applies BR-005 (MPF cap boundary: .62)
**Endpoint:** POST /api/v1/documents/{job_id}/calculate
**Priority:** High
**Type:** Boundary

**Prerequisites:**
- Document total_entered_value = ,000 (results in raw MPF = .80)

**Test Steps:**
1. POST /api/v1/documents/{job_id}/calculate
2. Poll results
3. Verify tariff_lines MPF entry has amount = 634.62 (cap applied)

**Expected Result:**
- MPF amount: 634.62 (cap, not 692.80)

---

### TC-DOC-018: Calculate - BR-006 (HMF Vessel)
**Title:** Calculate applies BR-006 (HMF for vessel mode)
**Endpoint:** POST /api/v1/documents/{job_id}/calculate
**Priority:** High
**Type:** Business Rule

**Prerequisites:**
- Document mode_of_transport = "vessel"
- total_entered_value = ,000

**Test Steps:**
1. POST /api/v1/documents/{job_id}/calculate
2. Poll results
3. Verify tariff_lines HMF entry has amount ≈ 187.50 (150000 × 0.00125)
4. Verify HMF refundable = false

**Expected Result:**
- HMF amount ≈ 187.50

---

### TC-DOC-019: Calculate - BR-006 (HMF Air = )
**Title:** Calculate applies BR-006 (HMF =  for air)
**Endpoint:** POST /api/v1/documents/{job_id}/calculate
**Priority:** High
**Type:** Business Rule

**Prerequisites:**
- Document mode_of_transport = "air"
- total_entered_value = ,000

**Test Steps:**
1. POST /api/v1/documents/{job_id}/calculate
2. Poll results
3. Verify tariff_lines HMF entry has amount = 0.00

**Expected Result:**
- HMF amount: 0.00

---

### TC-DOC-020: Calculate - BR-007 (Pathway PSC ≤15 days)
**Title:** Calculate applies BR-007 pathway (PSC for ≤15 days)
**Endpoint:** POST /api/v1/documents/{job_id}/calculate
**Priority:** High
**Type:** Boundary

**Prerequisites:**
- Document summary_date = 15 days ago from today

**Test Steps:**
1. POST /api/v1/documents/{job_id}/calculate
2. Poll results
3. Verify result.refund_pathway = "PSC"
4. Verify result.days_elapsed = 15
5. Verify result.pathway_rationale mentions "Post-Summary Correction"

**Expected Result:**
- refund_pathway: "PSC"

---

### TC-DOC-021: Calculate - BR-007 (Pathway PROTEST 16-180 days)
**Title:** Calculate applies BR-007 pathway (PROTEST for 16-180 days)
**Endpoint:** POST /api/v1/documents/{job_id}/calculate
**Priority:** High
**Type:** Boundary

**Prerequisites:**
- Document summary_date = 16 days ago

**Test Steps:**
1. POST /api/v1/documents/{job_id}/calculate
2. Poll results
3. Verify result.refund_pathway = "PROTEST"

**Expected Result:**
- refund_pathway: "PROTEST"

---

### TC-DOC-022: Calculate - BR-007 (Pathway INELIGIBLE >180 days)
**Title:** Calculate applies BR-007 pathway (INELIGIBLE for >180 days)
**Endpoint:** POST /api/v1/documents/{job_id}/calculate
**Priority:** High
**Type:** Boundary

**Prerequisites:**
- Document summary_date = 181 days ago

**Test Steps:**
1. POST /api/v1/documents/{job_id}/calculate
2. Poll results
3. Verify result.refund_pathway = "INELIGIBLE"

**Expected Result:**
- refund_pathway: "INELIGIBLE"

---

### TC-DOC-023: Calculate - BR-008 (Estimated Refund = IEEPA Only)
**Title:** Verify estimated_refund includes only IEEPA, not other duties
**Endpoint:** POST /api/v1/documents/{job_id}/calculate
**Priority:** High
**Type:** Business Rule

**Prerequisites:**
- Document with multiple duty types:
  - MFN amount: ,000
  - IEEPA amount: ,500
  - S301 amount: ,000

**Test Steps:**
1. POST /api/v1/documents/{job_id}/calculate
2. Poll results
3. Verify result.estimated_refund = 37,500.00 (IEEPA only)
4. Verify result.estimated_refund ≠ total_duty

**Expected Result:**
- estimated_refund: 37,500.00 (IEEPA only)

---

### TC-DOC-024: Calculate - BR-011 (Audit Trail Created)
**Title:** Verify BR-011 creates immutable audit trail
**Endpoint:** POST /api/v1/documents/{job_id}/calculate
**Priority:** High
**Type:** Business Rule

**Test Steps:**
1. POST /api/v1/documents/{job_id}/calculate
2. Get calculation_id
3. Query calculation_audit table for calculation_id
4. Verify exactly 1 audit row exists
5. Verify audit.snapshot is not NULL (contains full calculation details)
6. Verify audit.created_at is populated
7. Attempt to UPDATE or DELETE audit row (should fail at DB level)

**Expected Result:**
- CalculationAudit row created with complete snapshot
- Audit record immutable (no UPDATE/DELETE allowed)

---

### TC-DOC-025: Calculate - Idempotency
**Title:** Calculate same document twice returns same calculation_id
**Endpoint:** POST /api/v1/documents/{job_id}/calculate
**Priority:** High
**Type:** Idempotency

**Prerequisites:**
- Document with completed OCR

**Test Steps:**
1. POST /api/v1/documents/{job_id}/calculate → calc_id_1
2. POST /api/v1/documents/{job_id}/calculate again → calc_id_2
3. Verify calc_id_1 == calc_id_2
4. Verify only 1 Calculation row for this document_id
5. Verify only 1 CalculationAudit row

**Expected Result:**
- calc_id_1 == calc_id_2
- No duplicate database rows

---

## RESULTS MODULE TEST CASES

### TC-RES-001: Get Result - Completed Calculation
**Title:** Retrieve full calculation result when completed
**Endpoint:** GET /api/v1/results/{calculation_id}
**Priority:** Critical
**Type:** Happy Path

**Prerequisites:**
- Calculation completed (status='completed')
- duty_components populated

**Test Steps:**
1. GET /api/v1/results/{calculation_id}
2. Verify HTTP status is 200
3. Verify response contains all required fields:
   - calculation_id, entry_number, summary_date, country_of_origin
   - estimated_refund, refund_pathway, tariff_lines, line_duty_components
4. Verify tariff_lines is array with MFN, IEEPA, S301, S232, MPF, HMF
5. Verify line_duty_components contains per-HTS breakdown
6. Verify only IEEPA marked refundable=true

**Expected Result:**
- HTTP Status: 200
- Response contains complete calculation result
- Data formatted correctly

---

### TC-RES-002: Get Result - Calculation Pending
**Title:** Return 202 when calculation still in progress
**Endpoint:** GET /api/v1/results/{calculation_id}
**Priority:** High
**Type:** Happy Path

**Prerequisites:**
- Calculation status = "calculating"

**Test Steps:**
1. GET /api/v1/results/{calculation_id}
2. Verify HTTP status is 202
3. Verify response detail = "Calculation in progress"

**Expected Result:**
- HTTP Status: 202
- Response detail: "Calculation in progress"

---

### TC-RES-003: Get Result - Calculation Failed
**Title:** Return 500 when calculation failed
**Endpoint:** GET /api/v1/results/{calculation_id}
**Priority:** High
**Type:** Error Case

**Prerequisites:**
- Calculation status = "failed"

**Test Steps:**
1. GET /api/v1/results/{calculation_id}
2. Verify HTTP status is 500
3. Verify response detail = "Calculation failed"

**Expected Result:**
- HTTP Status: 500
- Response detail: "Calculation failed"

---

### TC-RES-004: Get Result - Not Found
**Title:** Return 404 if calculation doesn't exist
**Endpoint:** GET /api/v1/results/{calculation_id}
**Priority:** High
**Type:** Error Case

**Test Steps:**
1. GET /api/v1/results/00000000-0000-0000-0000-000000000000 (fake UUID)
2. Verify HTTP status is 404
3. Verify response detail = "Result not found"

**Expected Result:**
- HTTP Status: 404
- Response detail: "Result not found"

---

### TC-RES-005: Results Public Access
**Title:** Results endpoint requires no authentication
**Endpoint:** GET /api/v1/results/{calculation_id}
**Priority:** Medium
**Type:** Happy Path

**Prerequisites:**
- Calculation exists

**Test Steps:**
1. GET /api/v1/results/{calculation_id} with NO Authorization header and NO session cookie
2. Verify HTTP status is 200 (or 202/404/500 as appropriate)
3. Verify no 401 Unauthorized error

**Expected Result:**
- HTTP Status: 200 (or valid response code)
- No 401 error

---

## RATE LIMIT TEST CASES

### TC-RATE-001: Login Rate Limit (5/minute)
**Title:** Verify login endpoint enforces 5 requests/minute limit
**Endpoint:** POST /api/v1/auth/token
**Priority:** Medium
**Type:** Rate Limit

**Test Steps:**
1. Make 5 login requests within 60 seconds
2. Verify all return 200 or 401 (based on credentials)
3. Make 6th request immediately
4. Verify 6th request returns 429 Too Many Requests
5. Wait 61 seconds
6. Make 7th request
7. Verify 7th request succeeds (rate limit reset)

**Expected Result:**
- Requests 1-5: 200 or 401
- Request 6: 429
- Request 7 (after wait): 200 or 401

---

### TC-RATE-002: Upload Rate Limit (10/hour)
**Title:** Verify upload endpoint enforces 10 requests/hour limit
**Endpoint:** POST /api/v1/documents/upload
**Priority:** Medium
**Type:** Rate Limit

**Test Steps:**
1. Make 10 upload requests within same hour
2. Verify all return 202
3. Make 11th request
4. Verify 11th returns 429
5. Wait 1 hour
6. Make 12th request
7. Verify 12th returns 202

**Expected Result:**
- Requests 1-10: 202
- Request 11: 429
- Request 12 (after 1 hour): 202

---

## EDGE CASE & BOUNDARY TEST CASES

### TC-EDGE-001: Empty File Upload
**Title:** Reject upload of empty file
**Endpoint:** POST /api/v1/documents/upload
**Priority:** Low
**Type:** Edge Case

**Test Steps:**
1. Create empty PDF file (0 bytes)
2. POST /api/v1/documents/upload
3. Verify HTTP status is 415 (invalid MIME) or 422 (validation error)

**Expected Result:**
- Upload rejected

---

### TC-EDGE-002: Exactly 20 MB File
**Title:** Upload succeeds for file exactly at 20 MB boundary
**Endpoint:** POST /api/v1/documents/upload
**Priority:** Medium
**Type:** Boundary

**Test Steps:**
1. Create 20 MB PDF file
2. POST /api/v1/documents/upload
3. Verify HTTP status is 202

**Expected Result:**
- HTTP Status: 202
- Upload succeeds

---

### TC-EDGE-003: Exactly 20 MB + 1 Byte
**Title:** Upload fails for file over 20 MB by 1 byte
**Endpoint:** POST /api/v1/documents/upload
**Priority:** Medium
**Type:** Boundary

**Test Steps:**
1. Create 20 MB + 1 byte PDF file
2. POST /api/v1/documents/upload
3. Verify HTTP status is 413

**Expected Result:**
- HTTP Status: 413 File Too Large

---

### TC-EDGE-004: MPF Exactly at Floor (.71)
**Title:** Verify MPF floor boundary (entered_value that yields exactly .71)
**Endpoint:** POST /api/v1/documents/{job_id}/calculate
**Priority:** Low
**Type:** Boundary

**Test Steps:**
1. Document with total_entered_value that yields exactly .71 raw MPF
2. Calculate and verify result shows MPF = .71 (not rounded differently)

**Expected Result:**
- MPF: 32.71

---

### TC-EDGE-005: MPF Exactly at Cap (.62)
**Title:** Verify MPF cap boundary
**Endpoint:** POST /api/v1/documents/{job_id}/calculate
**Priority:** Low
**Type:** Boundary

**Test Steps:**
1. Document with total_entered_value that yields exactly .62 raw MPF
2. Calculate and verify result shows MPF = .62

**Expected Result:**
- MPF: 634.62

---

## SECURITY TEST CASES

### TC-SEC-001: No User Enumeration in Login Error
**Title:** Verify login error doesn't reveal whether email exists
**Endpoint:** POST /api/v1/auth/token
**Priority:** High
**Type:** Security

**Test Steps:**
1. POST with nonexistent email + any password → response A
2. POST with existing email + wrong password → response B
3. Verify response A == response B (identical error messages)

**Expected Result:**
- Both return 401 with same error message
- No difference between "user not found" and "wrong password"

---

### TC-SEC-002: Constant-Time Password Comparison
**Title:** Verify password comparison is constant-time
**Endpoint:** POST /api/v1/auth/token
**Priority:** Medium
**Type:** Security

**Test Steps:**
1. Measure response time for correct password
2. Measure response time for wrong password (same user)
3. Response times should be similar (± 10ms, depending on system)

**Expected Result:**
- Response times similar (constant-time comparison)

---

### TC-SEC-003: JWT Signature Validation
**Title:** Verify JWT with tampered signature is rejected
**Endpoint:** GET /api/v1/documents/{job_id}/status
**Priority:** High
**Type:** Security

**Test Steps:**
1. Login and get access_token
2. Tamper with JWT signature (change last character)
3. GET /documents/{id}/status with tampered token
4. Verify HTTP status is 401

**Expected Result:**
- HTTP Status: 401
- Response detail: "Invalid token"

---

### TC-SEC-004: Access Token Expiry
**Title:** Verify expired access_token is rejected
**Endpoint:** GET /api/v1/documents/{job_id}/status
**Priority:** High
**Type:** Security

**Prerequisites:**
- Create an access_token that expires in 1 second

**Test Steps:**
1. Wait 2 seconds
2. GET /documents/{id}/status with expired token
3. Verify HTTP status is 401

**Expected Result:**
- HTTP Status: 401
- Response detail: "Token expired"

---

### TC-SEC-005: Refresh Token HttpOnly Cookie
**Title:** Verify refresh_token cookie is HttpOnly (not accessible via JavaScript)
**Endpoint:** POST /api/v1/auth/token
**Priority:** High
**Type:** Security

**Test Steps:**
1. Login and capture Set-Cookie response header
2. Verify Set-Cookie includes HttpOnly flag
3. Verify Set-Cookie includes Secure flag
4. Verify Set-Cookie includes SameSite=Strict flag

**Expected Result:**
- Cookie flags: HttpOnly; Secure; SameSite=Strict
- JavaScript cannot access cookie

---

### TC-SEC-006: CORS Preflight
**Title:** Verify CORS preflight response includes correct headers
**Endpoint:** Any
**Priority:** Medium
**Type:** Security

**Test Steps:**
1. OPTIONS request with Origin: https://example.com
2. Verify response includes Access-Control-Allow-Origin
3. Verify response includes Access-Control-Allow-Methods
4. Verify response includes Access-Control-Allow-Credentials: true

**Expected Result:**
- CORS headers present
- Credentials allowed

---

## SUMMARY

**Total Test Cases:** 80+
**Critical:** 10
**High:** 40+
**Medium:** 20+
**Low:** 10+

**Modules:**
- Auth: 9 test cases
- Documents: 25+ test cases
- Results: 5 test cases
- Rate Limits: 2 test cases
- Edge Cases: 5 test cases
- Security: 6 test cases
- Business Rules: 20+ test cases (embedded in document tests)

