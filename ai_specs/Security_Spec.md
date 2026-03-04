# Security Specification
**Document Reference:** DMX-TRS-IEEPA-2026-001 (Local Deployment Edition)  
**Based On BRS:** DMX-BRS-IEEPA-2026-001 v1.0  
**Owner:** Office of the CIO, Dimerco Express Group  
**Version:** 1.0 | March 2026 | Internal — Confidential  
**注意：** 本文件為本地部署版本，已移除所有 AWS 依賴，資安控制以開源及本地等效方案實作。

---

## Section 7.1 — Authentication & Authorization（身份驗證與授權）

### 7.1.1 使用者角色與權限矩陣

| 角色 | 標識方式 | 可存取資源 |
|------|---------|-----------|
| **Guest**（匿名訪客）| 無 Token / 匿名 `session_id` cookie | 單筆文件上傳、OCR 查詢、計算結果查看、Lead 提交 |
| **Registered User** | JWT（`role: user`）| Guest 所有功能 + 批量上傳、歷史紀錄 |
| **Admin** | JWT（`role: admin`）| 所有 API + 稅率管理、潛客匯出、系統分析 |

---

### 7.1.2 JWT Token 規格

| 屬性 | Access Token | Refresh Token |
|------|-------------|---------------|
| **簽名演算法** | HS256（HMAC-SHA256）| HS256 |
| **簽名金鑰** | `SECRET_KEY`（環境變數，256-bit random hex）| 同 `SECRET_KEY` |
| **有效期** | **15 分鐘** | **7 天** |
| **傳遞方式** | `Authorization: Bearer <token>` Header | `httpOnly` Cookie（`refresh_token`）|
| **儲存位置（Client）** | 記憶體（不存 localStorage，防 XSS 竊取）| httpOnly Cookie（防 JavaScript 存取）|

**JWT Payload 結構：**

```json
{
  "sub": "<user_uuid>",
  "role": "user | admin",
  "email": "<user_email>",
  "iat": 1709500000,
  "exp": 1709500900
}
```

**實作規範（Python / PyJWT）：**

```python
# 產生 Access Token
import jwt
from datetime import datetime, timedelta, timezone

def create_access_token(user_id: str, role: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "email": email,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

# 驗證 Token（FastAPI Dependency）
async def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenPayload:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

---

### 7.1.3 密碼安全（Password Security）

| 規則 | 規格 |
|------|------|
| **雜湊演算法** | bcrypt，work factor（cost） ≥ **12** |
| **實作套件** | `passlib[bcrypt]` |
| **最小長度** | 8 個字元 |
| **複雜度要求** | 至少包含大寫、小寫、數字各一 |
| **禁止儲存明文** | 任何情況下不得以明文或可逆加密方式儲存密碼 |
| **錯誤訊息** | 登入失敗一律回傳「Email 或密碼錯誤」，不區分「帳號不存在」與「密碼錯誤」（防帳號枚舉）|

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
```

---

### 7.1.4 Token 刷新流程（Refresh Token Rotation）

```
Client                        API Server
  │                               │
  │── POST /api/v1/auth/token ──► │  (首次登入)
  │◄─ { access_token }           │  + Set-Cookie: refresh_token=...; httpOnly; Secure; SameSite=Strict
  │                               │
  │  (Access Token 過期後)         │
  │── POST /api/v1/auth/refresh ► │  (自動帶入 httpOnly Cookie)
  │   [Cookie: refresh_token]     │  驗證 Refresh Token 有效性
  │◄─ { access_token (新) }      │  + Set-Cookie: refresh_token=...(新，舊的失效)
  │                               │
  │── POST /api/v1/auth/logout ─► │
  │                               │  清除 Refresh Token（DB 黑名單 or 刪除）
  │◄─ 200 OK                     │  + Set-Cookie: refresh_token=; Max-Age=0
```

**Refresh Token 黑名單機制：**
- Refresh Token 使用後立即失效（Rotation）
- 登出時將 Token 加入 Redis 黑名單（TTL = 7 天）
- 每次驗證 Refresh Token 前先查詢 Redis 黑名單

---

### 7.1.5 電子郵件驗證流程（Email Verification）

```
POST /api/v1/auth/register
    │
    ▼
建立 users 記錄（is_active = false）
    │
    ▼
產生 email_verification_token（UUID v4，TTL = 24h，存入 Redis）
    │
    ▼
發送驗證信至使用者 Email（含驗證連結 /verify?token=...）
    │
    ▼
使用者點擊連結 GET /api/v1/auth/verify?token=...
    │
    ▼
驗證 token 有效且未過期 → users.is_active = true → 清除 Redis token
    │
    ▼
回傳成功訊息，引導使用者登入
```

---

### 7.1.6 Admin 端點保護

```python
# FastAPI Dependency：要求 Admin 角色
async def require_admin(current_user: TokenPayload = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# 使用方式
@router.get("/api/v1/admin/rates")
async def list_rates(admin: TokenPayload = Depends(require_admin)):
    ...
```

所有 `/api/v1/admin/*` 路由均掛載 `require_admin` dependency。未帶 Token、Token 過期、或 `role != admin` 的請求一律回傳 **HTTP 403**。

---

### 7.1.7 匿名訪客 Session 管理

訪客（未登入使用者）使用 `session_id` 追蹤計算歷程，以便在同一 Session 內關聯 document → calculation → lead：

| 項目 | 規格 |
|------|------|
| **Session ID 格式** | UUID v4（伺服器端產生）|
| **傳遞方式** | 回應第一次上傳請求時設定 `session_id` Cookie |
| **Cookie 屬性** | `HttpOnly; Secure; SameSite=Strict; Max-Age=86400`（24h）|
| **伺服器端儲存** | Redis，TTL = 24 小時 |
| **關聯資料** | `documents.session_id` 欄位 |

---

## Section 7.3 — Security Controls（安全控制措施）

### 7.3.1 傳輸層安全（Transport Security）

| 控制項 | 規格 | 實作方式 |
|--------|------|---------|
| **TLS 版本** | 強制 **TLS 1.3**，停用 TLS 1.0 / 1.1 / 1.2 | Nginx `ssl_protocols TLSv1.3` |
| **憑證** | 生產環境使用 Let's Encrypt（自動續期）；開發環境使用 mkcert 自簽憑證 | Nginx + Certbot |
| **HSTS** | `Strict-Transport-Security: max-age=31536000; includeSubDomains` | Nginx `add_header` |
| **HTTP → HTTPS 強制跳轉** | 所有 HTTP 請求 301 重導向至 HTTPS | Nginx `return 301 https://` |

**Nginx TLS 設定範例：**

```nginx
server {
    listen 443 ssl http2;
    ssl_certificate     /etc/letsencrypt/live/ieepa.dimerco.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ieepa.dimerco.com/privkey.pem;
    ssl_protocols       TLSv1.3;
    ssl_ciphers         TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256;
    ssl_prefer_server_ciphers off;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
}
```

---

### 7.3.2 HTTP 安全標頭（Security Headers）

所有回應均須包含以下 HTTP 標頭，透過 Nginx 及 FastAPI Middleware 雙層注入：

| 標頭 | 值 | 防護目標 |
|------|-----|---------|
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'` | XSS、Clickjacking |
| `X-Frame-Options` | `DENY` | Clickjacking |
| `X-Content-Type-Options` | `nosniff` | MIME Sniffing |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | 資訊洩漏 |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` | 瀏覽器 API 濫用 |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | 降級攻擊 |

**FastAPI Middleware 實作：**

```python
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)
```

---

### 7.3.3 速率限制（Rate Limiting — 取代 AWS WAF）

**雙層防護架構：**

```
請求進入
    │
    ▼
[Layer 1] Nginx limit_req（連線層）
    │ 超限 → 直接回傳 HTTP 429，不進入應用程式
    ▼
[Layer 2] slowapi（FastAPI 應用層）
    │ 精細化控制（依 endpoint、依 IP）
    ▼
業務邏輯處理
```

**速率限制規則：**

| 端點類型 | 限制規則 | 超限回應 |
|----------|---------|---------|
| **文件上傳** `POST /api/v1/documents/upload` | 每 IP 每小時 **10 次** | HTTP 429 + `Retry-After` Header |
| **一般 GET 請求** | 每 IP 每分鐘 **60 次** | HTTP 429 + `Retry-After` Header |
| **計算觸發** `POST /api/v1/documents/*/calculate` | 每 IP 每分鐘 **10 次** | HTTP 429 + `Retry-After` Header |
| **登入嘗試** `POST /api/v1/auth/token` | 每 IP 每分鐘 **5 次** | HTTP 429（防暴力破解）|
| **Admin API** `/api/v1/admin/*` | 每 Admin 帳號每分鐘 **30 次** | HTTP 429 |

**slowapi 實作範例：**

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, storage_uri="redis://redis:6379/1")
app.state.limiter = limiter

@router.post("/api/v1/documents/upload")
@limiter.limit("10/hour")
async def upload_document(request: Request, ...):
    ...
```

**Nginx Layer 1 設定：**

```nginx
http {
    limit_req_zone $binary_remote_addr zone=upload:10m rate=10r/h;
    limit_req_zone $binary_remote_addr zone=api:10m    rate=60r/m;
    limit_req_status 429;

    location /api/v1/documents/upload {
        limit_req zone=upload burst=2 nodelay;
        proxy_pass http://api;
    }
    location /api/ {
        limit_req zone=api burst=10 nodelay;
        proxy_pass http://api;
    }
}
```

---

### 7.3.4 檔案上傳安全（File Upload Security）

| 控制項 | 規格 | 實作說明 |
|--------|------|---------|
| **MIME 驗證** | 同時驗證 Content-Type Header **與** 檔案 Magic Bytes，不信任副檔名 | `python-magic` 套件讀取實際 Magic Bytes |
| **允許格式** | `application/pdf`、`image/jpeg`、`image/png` | Magic Bytes：`%PDF`、`FFD8FF`、`89504E47` |
| **最大檔案大小** | 20 MB | Nginx `client_max_body_size 20M` + FastAPI 驗證 |
| **檔案名稱正規化** | 儲存時使用 `job_id` 作為檔名，丟棄原始檔名（防 Path Traversal）| 原始檔名僅記錄於 `documents.original_name` |
| **病毒掃描** | 使用 ClamAV（本地安裝）在 Worker 接收到 Job 後掃描，陽性結果直接刪除檔案並通知 | `clamd` Python binding |
| **儲存加密** | 寫入本地磁碟前以 **AES-256-GCM** 加密 | `cryptography.fernet.Fernet.encrypt()` |

```python
import magic

ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png"}
ALLOWED_MAGIC_BYTES = {
    b"%PDF": "application/pdf",
    bytes([0xFF, 0xD8, 0xFF]): "image/jpeg",
    bytes([0x89, 0x50, 0x4E, 0x47]): "image/png",
}

async def validate_upload(file: UploadFile) -> None:
    content = await file.read(8192)  # 讀取前 8KB 做檢測
    await file.seek(0)

    detected_mime = magic.from_buffer(content, mime=True)
    if detected_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=415, detail="UNSUPPORTED_FILE_TYPE")

    if file.size > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="FILE_TOO_LARGE")
```

---

### 7.3.5 PII 資料加密（PII Encryption）

`leads` 資料表中的 `email`、`phone`、`full_name` 欄位須在**應用層加密後**才能寫入資料庫：

| 項目 | 規格 |
|------|------|
| **加密演算法** | AES-256-GCM（透過 `cryptography.fernet.Fernet`，內含 HMAC-SHA256 完整性驗證）|
| **金鑰儲存** | `/data/keys/app_secret.key`（檔案權限 `chmod 600`，取代 AWS KMS）|
| **金鑰載入** | 應用啟動時讀取一次存入記憶體（`APP_ENCRYPTION_KEY` 環境變數）|
| **解密時機** | 僅在 CRM 同步任務、Admin 匯出 CSV 時解密，一般 API 回應不解密 |
| **DB Dump 安全** | 無金鑰的情況下 DB Dump 中的 PII 欄位為不可讀密文 |

```python
from cryptography.fernet import Fernet

class PIIEncryptor:
    def __init__(self, key: bytes):
        self.fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        return self.fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self.fernet.decrypt(ciphertext.encode()).decode()

# 初始化（應用啟動時執行一次）
pii_encryptor = PIIEncryptor(settings.APP_ENCRYPTION_KEY.encode())
```

---

### 7.3.6 SQL 注入防護（SQL Injection Prevention）

| 規則 | 說明 |
|------|------|
| **強制使用 ORM** | 所有資料庫查詢透過 SQLAlchemy 2.0 ORM 或 `text()` 搭配 bindparams，禁止任何形式的字串拼接 SQL |
| **禁止的寫法** | `f"SELECT * FROM users WHERE email='{email}'"` — 嚴禁，Code Review 必查 |
| **允許的寫法** | `select(User).where(User.email == email)` 或 `text("SELECT * FROM users WHERE email=:email").bindparams(email=email)` |
| **驗證機制** | CI 流程中執行 `bandit` 靜態分析，偵測 SQL 字串拼接 |

---

### 7.3.7 日誌安全（Logging Security）

| 規則 | 說明 |
|------|------|
| **禁止記錄的內容** | 檔案內容、提取欄位值（OCR 結果）、PII（姓名/Email/電話）、JWT Token 內容、密碼 |
| **允許記錄的內容** | `document_id`、`job_id`、`calculation_id`、狀態轉換、錯誤代碼、IP 位址（僅非敏感 API）|
| **Download Token** | Pre-signed download token 不得出現在任何 log 中 |
| **Log 格式** | 結構化 JSON log（使用 `structlog`），包含 `timestamp`、`level`、`request_id`、`event` |
| **Log 儲存位置** | `/var/log/ieepa/` + Docker log driver，保留 30 天後輪換刪除 |

---

### 7.3.8 稽核日誌（Audit Log）

以下操作需在 `audit_log` 資料表留存不可刪除的稽核記錄：

| 操作類型 | 記錄欄位 |
|----------|---------|
| 管理員登入 | `admin_id`, `ip_address`, `timestamp`, `event: admin_login` |
| 稅率新增 / 修改 / 刪除 | `admin_id`, `hts_code`, `old_value`, `new_value`, `timestamp` |
| 批量稅率匯入 | `admin_id`, `filename`, `rows_success`, `rows_failed`, `timestamp` |
| 計算結果查詢（Admin）| `admin_id`, `calculation_id`, `timestamp` |
| 潛客資料匯出（CSV）| `admin_id`, `filter_params`, `row_count`, `timestamp` |

`audit_log` 資料表須設定 PostgreSQL Row-Level Security 或應用層攔截，**禁止 `DELETE` 操作**。

---

### 7.3.9 CORS 設定（Cross-Origin Resource Sharing）

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ieepa.dimerco.com",          # 生產
        "https://staging.ieepa.dimerco.local", # 測試
        "http://localhost:5173",               # 開發（Vite Dev Server）
    ],
    allow_credentials=True,   # 允許攜帶 Cookie（Refresh Token）
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Idempotency-Key"],
)
```

> **注意**：禁止使用 `allow_origins=["*"]`（尤其是當 `allow_credentials=True` 時，瀏覽器亦會拒絕此設定）。

---

### 7.3.10 隱私合規控制（Privacy Compliance）

| 控制項 | ID | 實作要求 |
|--------|-----|---------|
| **隱私聲明展示** | COMP-001 | `/calculate` 頁面上傳介面前顯示隱私聲明全文，法務核准版本 |
| **使用者勾選同意** | COMP-002 | 勾選前上傳按鈕 disabled；API 層驗證 `privacy_accepted: true` 旗標，未帶旗標的上傳請求回傳 HTTP 400 |
| **資料刪除接受時間戳** | COMP-002 | `privacy_accepted_at TIMESTAMPTZ` 記錄於 `documents` 資料表 |
| **GDPR 刪除請求** | COMP-003 | `DELETE /api/v1/users/me/data` 端點，30 天內清除 `leads`、`calculations`、`users` 所有關聯記錄 |
| **不用於模型訓練** | COMP-006 | 合約（DPA）及隱私聲明明文禁止，Google Document AI 須設定「不使用資料訓練」選項 |
| **強制免責聲明** | COMP-005 | 所有 Results 頁面（`/results/:id`, `/bulk/results/:id`）均以固定 Banner 顯示免責聲明，前端禁止提供隱藏按鈕 |
| **上傳文件 24h 自動刪除** | SEC-003 | Celery Beat 每小時執行清理 Job，刪除 `uploads/` 下超過 24 小時的目錄；DB 同步更新 `documents.expires_at` |
| **GA4 無 PII** | INT-009 | GA4 事件參數僅包含 `refund_range_bucket`（如 `$0-$1k`）、`pathway`、`country`，禁止傳入 `name`/`email`/`company` |

---

### 7.3.11 安全測試要求（Security Testing）

| 測試類型 | 工具 | 時機 | 標準 |
|----------|------|------|------|
| **靜態分析（SAST）** | `bandit`（Python）、`semgrep` | 每次 PR（CI 自動執行）| 0 個 High/Critical 問題 |
| **依賴漏洞掃描** | `pip-audit`（Python）、`npm audit`（前端）| 每次 PR（CI 自動執行）| 0 個 Critical 漏洞 |
| **滲透測試** | 第三方獨立執行（OWASP Top 10）| 生產部署前一次，此後每年一次 | 所有 Critical 及 High 問題修復後才可上線 |
| **HTTP 標頭掃描** | `securityheaders.com` 或 `mozilla observatory` | Staging 部署後手動執行 | 評級 ≥ A |
| **TLS 設定掃描** | `testssl.sh` 本地執行 | Staging 部署後手動執行 | TLS 1.1/1.2 確認停用 |

---

### 7.3.12 安全需求快速對照表（SEC-xxx Traceability）

| 需求 ID | 描述 | 本地實作方案 | 驗收標準 |
|---------|------|------------|---------|
| SEC-001 | 強制 TLS 1.3 | Nginx `ssl_protocols TLSv1.3` | `testssl.sh` 確認 TLS 1.1/1.2 停用 |
| SEC-002 | 文件儲存加密（原 S3 SSE-KMS）| AES-256-GCM 應用層加密，金鑰存 `/data/keys/` | 直接讀取磁碟檔案為密文，無法還原 |
| SEC-003 | 文件 24h 自動刪除（原 S3 Lifecycle）| Celery Beat 定時清理任務 | 測試物件建立 24h 後確認被刪除 |
| SEC-004 | 禁止記錄文件內容 | structlog 規則 + Code Review | Log 輸出審查無任何 OCR 欄位值 |
| SEC-005 | 速率限制 | Nginx `limit_req` + slowapi | 超過限制收到 HTTP 429 + Retry-After |
| SEC-006 | Admin API 需有效 JWT（admin role）| FastAPI `require_admin` Dependency | 無效 Token 回傳 403 |
| SEC-007 | 檔案驗證依 MIME + Magic Bytes | `python-magic` 驗證 | .exe 改名 .pdf 被拒絕 |
| SEC-008 | 參數化 SQL 查詢 | SQLAlchemy ORM + `bandit` 掃描 | `bandit` 掃描零 B608 報告 |
| SEC-009 | HTTP 安全標頭 | Nginx + FastAPI Middleware | `mozilla observatory` ≥ A |
| SEC-010 | 滲透測試 | 第三方獨立執行 | 上線前 Critical/High 清零 |
| SEC-011 | PII AES-256 加密（原 AWS KMS）| `cryptography.fernet`，金鑰存本地 | DB dump 中 PII 欄位為密文 |

---

*Prepared by the Office of the CIO, Dimerco Express Group | Version 1.0 | March 2026 | Confidential*
