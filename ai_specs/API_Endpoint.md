# API Endpoint Specification
**Document Reference:** DMX-TRS-IEEPA-2026-001 (Local Deployment Edition)  
**Based On:** Project_Context.md · Business_Rules.md · Tech_Stack.md · Security_Spec.md · UI_Spec.md  
**Owner:** Office of the CIO, Dimerco Express Group  
**Version:** 1.0 | March 2026 | Internal — Confidential

---

## Section 6.4 — API Specification

### 全域規範（Global Conventions）

| 項目 | 規格 |
|------|------|
| **Base URL** | `https://ieepa.dimerco.com/api/v1` |
| **協定** | HTTPS only（TLS 1.3）|
| **JSON Envelope** | 所有回應統一格式：`{ "success": bool, "data": any, "error": string\|null, "meta": object\|null }` |
| **身份驗證** | `Authorization: Bearer <access_token>` Header；Refresh Token 使用 httpOnly Cookie |
| **冪等性** | 所有觸發非同步 Job 的 POST 端點需帶 `X-Idempotency-Key: <uuid>` Header |
| **分頁** | 列表端點使用 `?page=1&page_size=20`；回應 `meta.total`, `meta.page`, `meta.page_size` |
| **日期格式** | ISO 8601（`YYYY-MM-DD` 或 `YYYY-MM-DDTHH:MM:SSZ`）|
| **金額格式** | 數字（`NUMERIC`），不含貨幣符號，保留 2 位小數 |
| **文件位置** | OpenAPI 3.1 JSON：`GET /api/docs`（限內網存取）|

**標準 JSON Envelope 範例：**

```json
// 成功
{ "success": true,  "data": { ... },  "error": null, "meta": { "request_id": "uuid" } }

// 失敗
{ "success": false, "data": null, "error": "UNRECOGNISED_DOCUMENT", "meta": { "request_id": "uuid" } }
```

---

### 6.4.1 Document Upload & OCR（文件上傳與 OCR）

---

#### `POST /api/v1/documents/upload`

**說明：** 上傳 CBP Form 7501，觸發非同步 OCR Job。

| 項目 | 內容 |
|------|------|
| **Auth** | 不需要（Guest 可用）|
| **Rate Limit** | 10 次 / IP / 小時 |
| **Idempotency** | `X-Idempotency-Key` Header 必填 |
| **Content-Type** | `multipart/form-data` |

**Request：**

| 欄位 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `file` | File | ✓ | PDF / JPEG / PNG，最大 20MB |
| `privacy_accepted` | `"true"` | ✓ | 使用者同意隱私條款（字串 "true"）|
| `session_id` | string | — | 訪客 Session ID（若已有，由 Cookie 自動帶入）|

**Response `202 Accepted`：**

```json
{
  "success": true,
  "data": {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "queued",
    "expires_at": "2026-03-05T04:00:00Z"
  },
  "error": null,
  "meta": { "request_id": "req-uuid" }
}
```

**Response Headers：**
- `Set-Cookie: session_id=<uuid>; HttpOnly; Secure; SameSite=Strict; Max-Age=86400`（訪客首次上傳時設定）

**錯誤回應：**

| HTTP 狀態碼 | `error` 值 | 觸發條件 |
|-------------|-----------|---------|
| `400` | `PRIVACY_NOT_ACCEPTED` | `privacy_accepted` 非 `"true"` |
| `413` | `FILE_TOO_LARGE` | 檔案 > 20MB |
| `415` | `UNSUPPORTED_FILE_TYPE` | MIME / Magic Bytes 不符 |
| `429` | `RATE_LIMIT_EXCEEDED` | 超過每 IP 每小時 10 次 |

---

#### `GET /api/v1/documents/{job_id}/status`

**說明：** 輪詢文件 OCR 處理狀態。前端每 2 秒輪詢一次直到 `completed` 或 `failed`。

| 項目 | 內容 |
|------|------|
| **Auth** | 不需要（Session Cookie 用於授權存取自己的 Job）|
| **Rate Limit** | 60 次 / IP / 分鐘 |

**Response `200 OK`（處理中）：**

```json
{
  "success": true,
  "data": {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "processing",
    "ocr_provider": "google_document_ai",
    "progress_message": "Analysing document fields..."
  },
  "error": null,
  "meta": null
}
```

**Response `200 OK`（完成 — `completed` 或 `review_required`）：**

```json
{
  "success": true,
  "data": {
    "job_id": "550e8400-...",
    "status": "review_required",
    "ocr_provider": "google_document_ai",
    "ocr_confidence": 0.87,
    "extracted_fields": {
      "entry_number":      { "value": "ABC-1234567-8", "confidence": 0.98, "review_required": false },
      "summary_date":      { "value": "2026-02-15",    "confidence": 0.72, "review_required": true  },
      "country_of_origin": { "value": "CN",            "confidence": 0.95, "review_required": false },
      "entry_type":        { "value": "01",            "confidence": 0.91, "review_required": false },
      "importer_name":     { "value": "ABC Trading Inc.", "confidence": 0.88, "review_required": false },
      "port_code":         { "value": "1001",          "confidence": 0.94, "review_required": false },
      "mode_of_transport": { "value": "vessel",        "confidence": 0.89, "review_required": false },
      "total_duty_fees":   { "value": 4140.00,         "confidence": 0.93, "review_required": false },
      "line_items": [
        {
          "hts_code":      { "value": "8471300100",  "confidence": 0.96, "review_required": false },
          "entered_value": { "value": 12500.00,      "confidence": 0.94, "review_required": false },
          "duty_rate":     { "value": "20.0%",       "confidence": 0.65, "review_required": true  },
          "duty_amount":   { "value": 2500.00,       "confidence": 0.92, "review_required": false }
        }
      ],
      "review_required_count": 2
    }
  },
  "error": null,
  "meta": null
}
```

**Response `200 OK`（失敗）：**

```json
{
  "success": false,
  "data": { "job_id": "550e8400-...", "status": "failed" },
  "error": "UNRECOGNISED_DOCUMENT",
  "meta": null
}
```

---

#### `PATCH /api/v1/documents/{job_id}/fields`

**說明：** 儲存使用者在 `/review` 頁的手動欄位修正。

| 項目 | 內容 |
|------|------|
| **Auth** | 不需要（Session Cookie 驗證所有權）|
| **Content-Type** | `application/json` |

**Request Body：**

```json
{
  "corrections": {
    "summary_date": "2026-02-15",
    "line_items": [
      { "index": 0, "duty_rate": "20.0%" }
    ]
  }
}
```

**Response `200 OK`：**

```json
{
  "success": true,
  "data": {
    "job_id": "550e8400-...",
    "corrections_applied": 2,
    "merged_fields": { "...（完整合併後的 extracted_fields 結構）": "..." }
  },
  "error": null,
  "meta": null
}
```

---

#### `POST /api/v1/documents/{job_id}/calculate`

**說明：** 以最終欄位值觸發計算引擎（非同步）。

| 項目 | 內容 |
|------|------|
| **Auth** | 不需要（Session Cookie 驗證所有權）|
| **Idempotency** | `X-Idempotency-Key` Header 必填 |
| **前置條件** | Job `status` 須為 `completed` 或 `review_required`（使用者確認後）|

**Request Body：** 空 `{}`

**Response `202 Accepted`：**

```json
{
  "success": true,
  "data": {
    "calculation_id": "calc-uuid-here",
    "status": "pending"
  },
  "error": null,
  "meta": null
}
```

**錯誤回應：**

| HTTP 狀態碼 | `error` 值 | 說明 |
|-------------|-----------|------|
| `409` | `JOB_NOT_READY` | Job 狀態不是 `completed` 或 `review_required` |
| `422` | `INSUFFICIENT_FIELDS` | 必要欄位（hts_code, entered_value, summary_date, country_of_origin）缺失 |

---

### 6.4.2 Calculation Results（計算結果）

---

#### `GET /api/v1/results/{calculation_id}`

**說明：** 取得完整關稅分解及退稅估算結果。

| 項目 | 內容 |
|------|------|
| **Auth** | 不需要（知道 `calculation_id` 即可存取 — 設計為可分享連結）|
| **Rate Limit** | 60 次 / IP / 分鐘 |
| **Polling** | `status` 為 `calculating` 時前端繼續輪詢（每 2 秒）|

**Response `200 OK`（計算完成）：**

```json
{
  "success": true,
  "data": {
    "calculation_id": "calc-uuid-here",
    "status": "completed",
    "entry_summary": {
      "entry_number": "ABC-1234567-8",
      "summary_date": "2026-02-15",
      "country_of_origin": "CN",
      "port_code": "1001",
      "importer_name": "ABC Trading Inc.",
      "mode_of_transport": "vessel",
      "total_entered_value": 20700.00
    },
    "duty_components": [
      {
        "tariff_type": "MFN",
        "display_name": "MFN Base Tariff",
        "hts_code": "8471300100",
        "rate_pct": 7.5,
        "entered_value": 12500.00,
        "amount": 937.50,
        "refundable": false,
        "section_232_applicable": false
      },
      {
        "tariff_type": "IEEPA",
        "display_name": "IEEPA Tariff",
        "hts_code": "8471300100",
        "rate_pct": 20.0,
        "entered_value": 12500.00,
        "amount": 2500.00,
        "refundable": true,
        "section_232_applicable": false
      },
      {
        "tariff_type": "S301",
        "display_name": "Section 301 (List 3A)",
        "hts_code": "8471300100",
        "rate_pct": 25.0,
        "entered_value": 12500.00,
        "amount": 3125.00,
        "refundable": false,
        "section_232_applicable": false
      },
      {
        "tariff_type": "MPF",
        "display_name": "Merchandise Processing Fee",
        "rate_pct": 0.3464,
        "entered_value": 20700.00,
        "amount": 71.69,
        "refundable": false,
        "section_232_applicable": false
      },
      {
        "tariff_type": "HMF",
        "display_name": "Harbor Maintenance Fee",
        "rate_pct": 0.125,
        "entered_value": 20700.00,
        "amount": 25.88,
        "refundable": false,
        "section_232_applicable": false
      }
    ],
    "total_duty": 6660.07,
    "estimated_refund": 2500.00,
    "refund_pathway": "PSC",
    "pathway_rationale": "Your entry summary date (2026-02-15) is 17 days ago. A Post-Summary Correction must be filed within 15 days. As this window has passed, a CBP Protest is recommended.",
    "days_since_summary": 17,
    "disclaimer_text": "This estimate is for informational purposes only and does not constitute legal or tax advice. Consult a licensed Customs House Broker before filing.",
    "created_at": "2026-03-04T10:30:00Z"
  },
  "error": null,
  "meta": null
}
```

> **注意：** `pathway_rationale` 內容依 `refund_pathway` 動態產生，每種途徑有對應範本。

**Response `200 OK`（計算進行中）：**

```json
{
  "success": true,
  "data": { "calculation_id": "calc-uuid-here", "status": "calculating" },
  "error": null,
  "meta": null
}
```

---

#### `POST /api/v1/results/{calculation_id}/export`

**說明：** 觸發伺服器端 PDF 報告產製，回傳帶時效 Download Token。

| 項目 | 內容 |
|------|------|
| **Auth** | 不需要（`calculation_id` 驗證）|
| **前置條件** | 對應 `leads` 記錄須存在（已完成潛客表單）|
| **SLA** | PDF 須在 10 秒內產製完成 |

**Request Body：** 空 `{}`

**Response `200 OK`：**

```json
{
  "success": true,
  "data": {
    "download_token": "eyJhbGciOiJIUzI1NiJ9...",
    "download_url": "/api/v1/files/download?token=eyJhbGciOiJIUzI1NiJ9...",
    "expires_at": "2026-03-04T10:45:00Z",
    "filename": "IEEPA_Refund_ABC-1234567-8_20260304.pdf"
  },
  "error": null,
  "meta": null
}
```

**錯誤回應：**

| HTTP 狀態碼 | `error` 值 | 說明 |
|-------------|-----------|------|
| `403` | `LEAD_REQUIRED` | 對應 `calculation_id` 尚未提交潛客表單 |
| `504` | `PDF_GENERATION_TIMEOUT` | 超過 10 秒仍未完成 |

---

#### `GET /api/v1/files/download`

**說明：** 使用帶時效 Token 下載本地儲存的 PDF 報告（取代 S3 Pre-signed URL）。

| 項目 | 內容 |
|------|------|
| **Auth** | Query Param `?token=<signed-token>`（HMAC-SHA256 簽名，15 分鐘有效）|
| **Response** | 直接串流回傳 PDF 檔案 |
| **Content-Type** | `application/pdf` |

**Response（成功）：** 直接回傳 PDF binary 串流，Headers：
```
Content-Type: application/pdf
Content-Disposition: attachment; filename="IEEPA_Refund_ABC-1234567-8_20260304.pdf"
```

**錯誤回應：**

| HTTP 狀態碼 | `error` 值 | 說明 |
|-------------|-----------|------|
| `403` | `TOKEN_EXPIRED` | Token 已超過 15 分鐘 |
| `403` | `INVALID_TOKEN` | Token 簽名驗證失敗 |
| `404` | `FILE_NOT_FOUND` | PDF 檔案已被清理或不存在 |

---

#### `GET /api/v1/results/{calculation_id}/summary`

**說明：** 輕量版結果摘要（不含完整 duty_components），用於分享連結預覽。

| 項目 | 內容 |
|------|------|
| **Auth** | 不需要 |

**Response `200 OK`：**

```json
{
  "success": true,
  "data": {
    "calculation_id": "calc-uuid-here",
    "entry_number": "ABC-1234567-8",
    "total_entered_value": 20700.00,
    "estimated_refund": 2500.00,
    "refund_pathway": "PSC",
    "created_at": "2026-03-04T10:30:00Z"
  },
  "error": null,
  "meta": null
}
```

---

### 6.4.3 Bulk Upload（批量上傳）

---

#### `POST /api/v1/bulk/upload`

**說明：** 上傳 CSV / XLSX 批量計算多筆 Entry Summary。

| 項目 | 內容 |
|------|------|
| **Auth** | 需要（`role: user` 或 `role: admin`）|
| **Content-Type** | `multipart/form-data` |
| **Idempotency** | `X-Idempotency-Key` Header 必填 |

**Request：**

| 欄位 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `file` | File | ✓ | CSV 或 XLSX，依範本 Schema |

**Response `202 Accepted`：**

```json
{
  "success": true,
  "data": {
    "bulk_job_id": "bulk-uuid-here",
    "status": "queued",
    "total_rows": 48,
    "valid_rows": 46,
    "invalid_rows": 2,
    "validation_errors": [
      { "row": 3,  "field": "hts_code_1", "error": "Invalid HTS code format" },
      { "row": 17, "field": "summary_date", "error": "Date out of range" }
    ]
  },
  "error": null,
  "meta": null
}
```

---

#### `GET /api/v1/bulk/{bulk_job_id}/status`

**說明：** 輪詢批量工作進度。

| 項目 | 內容 |
|------|------|
| **Auth** | 需要（擁有者驗證）|

**Response `200 OK`：**

```json
{
  "success": true,
  "data": {
    "bulk_job_id": "bulk-uuid-here",
    "total": 46,
    "completed": 32,
    "failed": 1,
    "in_progress": 13,
    "progress_pct": 71.7,
    "results_preview": [
      {
        "entry_number": "XXX-111-1",
        "estimated_refund": 2340.00,
        "refund_pathway": "PSC",
        "status": "completed"
      }
    ]
  },
  "error": null,
  "meta": null
}
```

---

#### `GET /api/v1/bulk/{bulk_job_id}/results`

**說明：** 取得批量工作的完整結果陣列。

| 項目 | 內容 |
|------|------|
| **Auth** | 需要（擁有者驗證）|
| **前置條件** | 所有 Job 須已完成（`in_progress = 0`）|

**Response `200 OK`：**

```json
{
  "success": true,
  "data": {
    "bulk_job_id": "bulk-uuid-here",
    "aggregate": {
      "total_entries": 46,
      "total_refundable": 28450.00,
      "pathway_breakdown": {
        "PSC": 12,
        "PROTEST": 18,
        "INELIGIBLE": 16
      }
    },
    "results": [
      {
        "calculation_id": "calc-uuid-1",
        "entry_number": "XXX-111-1",
        "summary_date": "2026-02-10",
        "country_of_origin": "CN",
        "total_entered_value": 15000.00,
        "estimated_refund": 2340.00,
        "refund_pathway": "PSC",
        "status": "completed"
      }
    ]
  },
  "error": null,
  "meta": { "total": 46, "page": 1, "page_size": 50 }
}
```

---

### 6.4.4 Lead Capture & Auth（潛客捕捉與身份驗證）

---

#### `POST /api/v1/leads`

**說明：** 提交潛客聯絡資訊，觸發非同步 CRM 同步。

| 項目 | 內容 |
|------|------|
| **Auth** | 不需要（Guest 可用）|
| **PII 處理** | `full_name`, `email`, `phone` 在後端 AES-256-GCM 加密後才存入 DB |

**Request Body：**

```json
{
  "full_name": "Jane Smith",
  "company_name": "ABC Trading Inc.",
  "email": "jane.smith@abctrading.com",
  "phone": "+15551234567",
  "country": "US",
  "preferred_contact": "email",
  "contact_consent": true,
  "calculation_id": "calc-uuid-here"
}
```

**Response `201 Created`：**

```json
{
  "success": true,
  "data": {
    "lead_id": "lead-uuid-here",
    "crm_sync_status": "pending",
    "message": "Thank you. Our team will be in touch within 1 business day."
  },
  "error": null,
  "meta": null
}
```

**錯誤回應：**

| HTTP 狀態碼 | `error` 值 | 說明 |
|-------------|-----------|------|
| `400` | `VALIDATION_ERROR` | 必填欄位缺失或格式錯誤 |
| `404` | `CALCULATION_NOT_FOUND` | `calculation_id` 不存在 |
| `409` | `LEAD_ALREADY_EXISTS` | 同一 `calculation_id` 已提交過潛客 |

---

#### `POST /api/v1/auth/register`

**說明：** 建立使用者帳號（需電子郵件驗證）。

| 項目 | 內容 |
|------|------|
| **Auth** | 不需要 |
| **後續動作** | 發送驗證 Email，帳號 `is_active = false` 直到驗證完成 |

**Request Body：**

```json
{
  "email": "jane@abctrading.com",
  "password": "Secure!Pass123",
  "password_confirm": "Secure!Pass123",
  "full_name": "Jane Smith",
  "company_name": "ABC Trading Inc."
}
```

**Response `201 Created`：**

```json
{
  "success": true,
  "data": {
    "user_id": "user-uuid-here",
    "email": "jane@abctrading.com",
    "is_active": false,
    "message": "Verification email sent. Please check your inbox."
  },
  "error": null,
  "meta": null
}
```

**錯誤回應：**

| HTTP 狀態碼 | `error` 值 | 說明 |
|-------------|-----------|------|
| `409` | `EMAIL_ALREADY_REGISTERED` | Email 已存在 |
| `400` | `PASSWORD_MISMATCH` | 兩次密碼不一致 |
| `400` | `PASSWORD_TOO_WEAK` | 密碼不符合複雜度要求 |

---

#### `GET /api/v1/auth/verify`

**說明：** 驗證 Email 驗證 Token，啟用帳號。

| 項目 | 內容 |
|------|------|
| **Auth** | 不需要 |
| **Query Param** | `?token=<verification-token>` |

**Response `200 OK`：**

```json
{
  "success": true,
  "data": { "message": "Email verified. You can now log in." },
  "error": null,
  "meta": null
}
```

---

#### `POST /api/v1/auth/token`

**說明：** 登入，取得 JWT Access Token + Refresh Token。

| 項目 | 內容 |
|------|------|
| **Auth** | 不需要 |
| **Rate Limit** | 每 IP 每分鐘 **5 次**（防暴力破解）|
| **Content-Type** | `application/json` |

**Request Body：**

```json
{
  "email": "jane@abctrading.com",
  "password": "Secure!Pass123"
}
```

**Response `200 OK`：**

```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiJ9...",
    "token_type": "Bearer",
    "expires_in": 900
  },
  "error": null,
  "meta": null
}
```

**Response Headers：**
```
Set-Cookie: refresh_token=<token>; HttpOnly; Secure; SameSite=Strict; Max-Age=604800; Path=/api/v1/auth/refresh
```

**錯誤回應：**

| HTTP 狀態碼 | `error` 值 | 說明 |
|-------------|-----------|------|
| `401` | `INVALID_CREDENTIALS` | Email 或密碼錯誤（不區分兩者）|
| `403` | `EMAIL_NOT_VERIFIED` | 帳號尚未完成 Email 驗證 |
| `429` | `RATE_LIMIT_EXCEEDED` | 登入嘗試過於頻繁 |

---

#### `POST /api/v1/auth/refresh`

**說明：** 使用 Refresh Token Cookie 換取新的 Access Token。

| 項目 | 內容 |
|------|------|
| **Auth** | httpOnly Cookie `refresh_token`（自動帶入）|
| **Rotation** | 每次刷新後舊 Refresh Token 立即失效，新 Token 由 Set-Cookie 回傳 |

**Request Body：** 空 `{}`

**Response `200 OK`：**

```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiJ9...(新 Token)",
    "token_type": "Bearer",
    "expires_in": 900
  },
  "error": null,
  "meta": null
}
```

**錯誤回應：**

| HTTP 狀態碼 | `error` 值 | 說明 |
|-------------|-----------|------|
| `401` | `REFRESH_TOKEN_EXPIRED` | Refresh Token 已超過 7 天 |
| `401` | `REFRESH_TOKEN_REVOKED` | Token 已被登出（黑名單）|

---

#### `POST /api/v1/auth/logout`

**說明：** 登出，將 Refresh Token 加入黑名單。

| 項目 | 內容 |
|------|------|
| **Auth** | `Authorization: Bearer <access_token>` |

**Response `200 OK`：**

```json
{
  "success": true,
  "data": { "message": "Logged out successfully." },
  "error": null,
  "meta": null
}
```

**Response Headers：**
```
Set-Cookie: refresh_token=; HttpOnly; Secure; SameSite=Strict; Max-Age=0; Path=/api/v1/auth/refresh
```

---

### 6.4.5 Admin Endpoints（管理後台端點）

> **所有 Admin 端點** 均需 `Authorization: Bearer <token>`（`role: admin`）。未帶 Token 或角色不符一律回傳 `403`。

---

#### `GET /api/v1/admin/rates`

**說明：** 列出 HTS 稅率，支援篩選與分頁。

**Query Params：**

| 參數 | 類型 | 說明 |
|------|------|------|
| `hts_code` | string | 模糊搜尋（`LIKE %value%`）|
| `country_code` | string | 精確篩選 |
| `tariff_type` | string | `MFN` \| `IEEPA` \| `S301` \| `S232` |
| `page` | int | 預設 1 |
| `page_size` | int | 預設 20，最大 100 |

**Response `200 OK`：**

```json
{
  "success": true,
  "data": [
    {
      "id": "rate-uuid",
      "hts_code": "8471300100",
      "country_code": "CN",
      "tariff_type": "IEEPA",
      "rate_pct": 20.0,
      "effective_from": "2025-04-02",
      "effective_to": null,
      "source_ref": "90 FR 12345",
      "updated_by": "admin-uuid",
      "updated_at": "2026-03-01T09:00:00Z"
    }
  ],
  "error": null,
  "meta": { "total": 1842, "page": 1, "page_size": 20 }
}
```

---

#### `PUT /api/v1/admin/rates/{rate_id}`

**說明：** 更新稅率記錄。操作記入 `audit_log`，立即清除 Redis 快取。

**Request Body：**

```json
{
  "rate_pct": 25.0,
  "effective_from": "2026-04-01",
  "effective_to": null,
  "source_ref": "90 FR 99999"
}
```

**Response `200 OK`：**

```json
{
  "success": true,
  "data": {
    "id": "rate-uuid",
    "hts_code": "8471300100",
    "country_code": "CN",
    "tariff_type": "IEEPA",
    "rate_pct": 25.0,
    "effective_from": "2026-04-01",
    "effective_to": null,
    "cache_invalidated": true,
    "audit_log_id": "audit-uuid"
  },
  "error": null,
  "meta": null
}
```

---

#### `POST /api/v1/admin/rates/import`

**說明：** 批量匯入稅率 CSV。

**Request：** `multipart/form-data` + `file`（CSV）

**CSV 格式：**
```csv
hts_code,country_code,tariff_type,rate_pct,effective_from,effective_to,source_ref
8471300100,CN,IEEPA,20.0,2025-04-02,,90 FR 12345
```

**Response `200 OK`：**

```json
{
  "success": true,
  "data": {
    "total_rows": 150,
    "success_count": 147,
    "failed_count": 3,
    "failures": [
      { "row": 12, "error": "Invalid HTS code: 847130010" },
      { "row": 45, "error": "Rate must be positive" }
    ]
  },
  "error": null,
  "meta": null
}
```

---

#### `GET /api/v1/admin/leads`

**說明：** 取得潛客列表，支援篩選與 CSV 匯出。

**Query Params：**

| 參數 | 類型 | 說明 |
|------|------|------|
| `date_from` | date | `created_at` 起始日期 |
| `date_to` | date | `created_at` 結束日期 |
| `country` | string | ISO alpha-2 |
| `refund_pathway` | string | `PSC` \| `PROTEST` \| `INELIGIBLE` |
| `crm_sync_status` | string | `pending` \| `synced` \| `failed` |
| `export` | bool | `true` 時回傳 UTF-8 CSV 附件 |
| `page` | int | 預設 1 |
| `page_size` | int | 預設 20，最大 100 |

**Response `200 OK`（JSON 格式）：**

```json
{
  "success": true,
  "data": [
    {
      "id": "lead-uuid",
      "calculation_id": "calc-uuid",
      "company_name": "ABC Trading Inc.",
      "country": "US",
      "preferred_contact": "email",
      "estimated_refund": 2500.00,
      "refund_pathway": "PSC",
      "crm_sync_status": "synced",
      "crm_lead_id": "CRM-12345",
      "created_at": "2026-03-04T10:30:00Z"
    }
  ],
  "error": null,
  "meta": { "total": 342, "page": 1, "page_size": 20 }
}
```

> **注意：** `full_name`, `email`, `phone` 在此 API 中**不解密回傳**（Admin 列表不直接暴露 PII），僅 CSV 匯出時解密。

**Response（`export=true`，CSV 格式）：**

```
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="leads_export_20260304.csv"
```

---

#### `GET /api/v1/admin/analytics`

**說明：** 取得使用統計數據。

**Response `200 OK`：**

```json
{
  "success": true,
  "data": {
    "daily_calculation_counts": [
      { "date": "2026-03-04", "count": 142 },
      { "date": "2026-03-03", "count": 118 }
    ],
    "top_10_hts_codes": [
      { "hts_code": "8471300100", "count": 234, "avg_ieepa_amount": 2340.50 }
    ],
    "avg_estimated_refund": 1842.30,
    "lead_capture_rate": 0.34,
    "avg_processing_time_seconds": 18.4,
    "pathway_breakdown": {
      "PSC": 412,
      "PROTEST": 688,
      "INELIGIBLE": 234
    },
    "period_days": 30
  },
  "error": null,
  "meta": null
}
```

---

### 6.4.6 API 完整端點索引（Endpoint Index）

| # | Method | Path | Auth | 用途 |
|---|--------|------|------|------|
| 1 | `POST` | `/api/v1/documents/upload` | None | 上傳 Form 7501，觸發 OCR |
| 2 | `GET` | `/api/v1/documents/{job_id}/status` | Session | OCR 處理狀態輪詢 |
| 3 | `PATCH` | `/api/v1/documents/{job_id}/fields` | Session | 儲存 OCR 欄位修正 |
| 4 | `POST` | `/api/v1/documents/{job_id}/calculate` | Session | 觸發計算引擎 |
| 5 | `GET` | `/api/v1/results/{calculation_id}` | None | 取得完整計算結果 |
| 6 | `POST` | `/api/v1/results/{calculation_id}/export` | None + Lead | 觸發 PDF 產製 |
| 7 | `GET` | `/api/v1/results/{calculation_id}/summary` | None | 輕量結果摘要（分享用）|
| 8 | `GET` | `/api/v1/files/download` | Token（Query）| 下載本地 PDF 報告 |
| 9 | `POST` | `/api/v1/bulk/upload` | User/Admin | 批量 CSV/XLSX 上傳 |
| 10 | `GET` | `/api/v1/bulk/{bulk_job_id}/status` | User/Admin | 批量進度輪詢 |
| 11 | `GET` | `/api/v1/bulk/{bulk_job_id}/results` | User/Admin | 批量完整結果 |
| 12 | `POST` | `/api/v1/leads` | None | 提交潛客資訊 |
| 13 | `POST` | `/api/v1/auth/register` | None | 使用者註冊 |
| 14 | `GET` | `/api/v1/auth/verify` | Token（Query）| Email 驗證 |
| 15 | `POST` | `/api/v1/auth/token` | None | 登入取得 JWT |
| 16 | `POST` | `/api/v1/auth/refresh` | Cookie | 刷新 Access Token |
| 17 | `POST` | `/api/v1/auth/logout` | Bearer | 登出 |
| 18 | `GET` | `/api/v1/admin/rates` | Admin | 稅率列表 |
| 19 | `PUT` | `/api/v1/admin/rates/{rate_id}` | Admin | 更新稅率 |
| 20 | `POST` | `/api/v1/admin/rates/import` | Admin | 批量匯入稅率 |
| 21 | `GET` | `/api/v1/admin/leads` | Admin | 潛客列表 / CSV 匯出 |
| 22 | `GET` | `/api/v1/admin/analytics` | Admin | 使用統計 |

---

### 6.4.7 前後端整合時序圖（Integration Sequence）

```
Browser                    FastAPI                   Celery Worker
   │                          │                            │
   │── POST /documents/upload ─►│                          │
   │◄─ { job_id, "queued" } ──│── enqueue(OCR_JOB) ──────►│
   │                          │                            │ OCR processing
   │── GET /documents/{id}/status ─► (polling every 2s)   │
   │◄─ { status: "processing" }│                          │
   │── GET /documents/{id}/status ─►                      │
   │◄─ { status: "review_required", extracted_fields } ◄──│
   │                          │                            │
   │  [User reviews /review]  │                            │
   │── PATCH /documents/{id}/fields ─►│                   │
   │◄─ { merged_fields } ─────│                           │
   │── POST /documents/{id}/calculate ─►│                 │
   │◄─ { calculation_id } ────│── enqueue(CALC_JOB) ─────►│
   │                          │                            │ Calculation
   │── GET /results/{id} ─────►  (polling every 2s)       │
   │◄─ { status: "calculating" }│                         │
   │── GET /results/{id} ─────►                           │
   │◄─ { status: "completed", duty_components, ... } ◄────│
   │                          │                            │
   │  [User at /register]     │                            │
   │── POST /leads ───────────►│── enqueue(CRM_JOB) ──────►│
   │◄─ { lead_id, "pending" } │                            │ CRM sync
   │── POST /results/{id}/export ─►│                      │
   │◄─ { download_token, ... } │                          │
   │── GET /files/download?token=... ─►│                  │
   │◄─ [PDF binary stream] ───│                           │
```

---

*Prepared by the Office of the CIO, Dimerco Express Group | Version 1.0 | March 2026 | Confidential*
