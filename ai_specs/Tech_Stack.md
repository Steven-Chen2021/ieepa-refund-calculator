# Tech Stack
**Document Reference:** DMX-TRS-IEEPA-2026-001 (Local Deployment Edition)  
**Based On BRS:** DMX-BRS-IEEPA-2026-001 v1.0  
**Owner:** Office of the CIO, Dimerco Express Group  
**Version:** 1.0 | March 2026 | Internal — Confidential  
**注意：** 本文件為本地部署版本，**不使用任何 AWS 服務**，所有雲端組件均以本地等效方案替代。

---

## Section 3.1 — Technology Stack

### 3.1.1 系統三層架構概覽（Local Deployment）

```
┌─────────────────────────────────────────────────────────┐
│              Tier 1：Presentation（前端）                 │
│         React 18 SPA  ←→  Nginx（靜態資源 + 反向代理）    │
└─────────────────────────────┬───────────────────────────┘
                              │ HTTP/HTTPS (TLS via Nginx)
┌─────────────────────────────▼───────────────────────────┐
│              Tier 2：Application（後端）                  │
│    FastAPI (Uvicorn/Gunicorn)  +  Celery Workers         │
└──────┬──────────────────────────────────┬───────────────┘
       │ SQLAlchemy (async)               │ Redis (queue/cache)
┌──────▼──────────────────────────────────▼───────────────┐
│              Tier 3：Data（資料層）                       │
│    PostgreSQL 15  |  Redis 7  |  Local File System       │
└─────────────────────────────────────────────────────────┘
```

---

### 3.1.2 前端技術棧（Frontend）

| 類別 | 套件 / 工具 | 版本 | 用途說明 |
|------|------------|------|---------|
| **框架** | React | 18.x | 函式元件 + Hooks，禁止使用 Class Components |
| **語言** | TypeScript | 5.x（strict mode）| 型別安全，所有元件及工具函式須有明確型別定義 |
| **樣式** | Tailwind CSS | v3.x | Utility-first，禁止引入其他 CSS Framework |
| **全域狀態** | Zustand | 4.x | 輕量全域狀態管理（上傳狀態、使用者 session）|
| **伺服器狀態** | TanStack Query | v5.x | API 請求快取、輪詢（polling OCR status）、樂觀更新 |
| **路由** | React Router | v6.x | SPA 頁面路由，含 Protected Route（登入驗證）|
| **檔案上傳** | react-dropzone | 14.x | 拖放上傳介面，限制 MIME type 於前端做第一層過濾 |
| **表單驗證** | React Hook Form + Zod | — | 表單狀態管理 + Schema 驗證（前端同步驗證）|
| **HTTP 客戶端** | Axios | 1.x | 統一 request/response interceptor（自動附加 JWT）|
| **建置工具** | Vite | 5.x | 開發 HMR 速度優化，生產環境 bundle 壓縮 |
| **測試** | Vitest + React Testing Library | — | 單元測試覆蓋率目標 ≥ 75% |
| **E2E 測試** | Playwright | — | 關鍵使用者旅程自動化測試 |
| **國際化** | react-i18next | — | 支援 `en` / `zh-CN` 語系切換，所有 UI 字串外部化 |
| **靜態服務** | Nginx | 1.25+ | 服務 React build 產物，反向代理至 FastAPI |

**頁面路由規劃：**

| Route | 頁面名稱 | 存取控制 |
|-------|----------|---------|
| `/` | Landing / Home | 公開 |
| `/calculate` | Calculator（單筆上傳）| 公開 |
| `/review` | Data Review（OCR 審查）| 公開（session-based）|
| `/results/:id` | Results（計算結果）| 公開 |
| `/register` | Registration（潛客表單）| 公開 |
| `/bulk` | Bulk Upload | 需登入（Registered User）|
| `/bulk/results/:id` | Bulk Results | 需登入 |
| `/admin/*` | Admin Portal | 需登入（Admin Role）|

---

### 3.1.3 後端技術棧（Backend）

| 類別 | 套件 / 工具 | 版本 | 用途說明 |
|------|------------|------|---------|
| **語言** | Python | 3.11+ | 主要後端語言 |
| **Web 框架** | FastAPI | 0.110+ | 非同步 REST API，自動產生 OpenAPI 3.1 文件 |
| **ASGI 伺服器** | Uvicorn + Gunicorn | — | Uvicorn workers，Gunicorn 管理 worker process |
| **任務佇列** | Celery | 5.x | 非同步工作（OCR Job、計算 Job、CRM 同步、檔案清理）|
| **佇列 Broker** | Redis | 7.x | Celery message broker 及 result backend |
| **ORM** | SQLAlchemy | 2.0 (async) | 資料庫存取，強制使用參數化查詢 |
| **Migration** | Alembic | — | 資料庫 Schema 版本管理 |
| **資料驗證** | Pydantic | v2 | 所有 Request / Response Schema 定義 |
| **JWT 驗證** | PyJWT | 2.x | Access Token（15 分鐘）、Refresh Token（7 天）|
| **密碼雜湊** | bcrypt（via passlib）| — | 使用者密碼雜湊儲存，work factor ≥ 12 |
| **PII 加密** | cryptography（Fernet / AES-256-GCM）| — | 加密 `email`, `phone`, `full_name` 欄位，取代 AWS KMS |
| **PDF 產製** | WeasyPrint | — | 伺服器端 HTML→PDF 轉換，含 Dimerco 品牌樣板 |
| **OCR 主引擎** | Google Document AI | — | Form Parser，提取 Form 7501 欄位 |
| **OCR 備援引擎** | pytesseract + pdf2image | — | 當 Google Document AI 不可用時的本地 OCR 備援（取代 AWS Textract）|
| **排程任務** | Celery Beat | — | 定時執行本地檔案 TTL 清理（每小時）|
| **速率限制** | slowapi（基於 limits）| — | API 層速率限制，取代 AWS WAF 基本限流功能 |
| **SMTP 郵件** | aiosmtplib | — | 非同步發送驗證信，透過本地 SMTP relay（取代 AWS SES）|
| **環境設定** | python-dotenv | — | 載入 `.env` 設定檔，取代 AWS Secrets Manager |
| **HTTP 安全標頭** | starlette（built-in）+ 自訂 Middleware | — | CSP、X-Frame-Options、HSTS 等標頭注入 |
| **測試** | pytest + httpx | — | 單元測試 + 非同步 API 整合測試，覆蓋率 ≥ 80% |
| **容器化** | Docker + Docker Compose | — | 多 stage build，本地 compose 編排所有服務 |

---

### 3.1.4 資料層（Data Tier）

#### PostgreSQL 15（主資料庫）

| 設定項目 | 值 |
|---------|-----|
| **版本** | PostgreSQL 15 |
| **部署方式** | Docker container（`postgres:15-alpine`）|
| **資料庫名稱** | `ieepa_refund_db` |
| **連線方式** | SQLAlchemy async engine（`asyncpg` driver）|
| **備份策略** | 每日 `pg_dump` 至本地備份目錄 `/data/backups/postgres/`，保留 30 天 |
| **讀寫分離** | 單機模式（本地部署不設 replica，如需擴展可加 pg_replication）|

**核心資料表（詳細 Schema 見 Technical_Foundation_&_Data.md）：**

| 資料表 | 用途 |
|--------|------|
| `documents` | 上傳文件狀態與 OCR 提取結果（JSONB）|
| `calculations` | 關稅計算結果（含退稅金額與途徑）|
| `leads` | 潛客聯絡資訊（PII 欄位 AES-256-GCM 加密）|
| `tariff_rates` | HTS 稅率資料庫（MFN / IEEPA / S301 / S232）|
| `users` | 已註冊使用者帳號（含 email 驗證狀態）|
| `admin_users` | 後台管理員帳號（role: admin）|
| `calculation_audit` | 計算稽核軌跡（不可刪除，Append-only）|
| `audit_log` | 管理員操作日誌（稅率變更等）|

#### Redis 7（快取 + 任務佇列）

| 用途 | 說明 |
|------|------|
| **Celery Broker** | OCR Job、計算 Job、CRM 同步、檔案清理的任務佇列 |
| **HTS 稅率快取** | TTL = 1 小時，稅率更新時立即 `DEL` 對應 key |
| **Session Store** | 訪客匿名 session（`session_id`），TTL = 24 小時 |
| **速率限制計數器** | slowapi 使用 Redis 儲存每 IP 的請求計數 |

#### 本地檔案系統（Local File System — 取代 AWS S3）

> **重要設計決策**：原 TRS 使用 AWS S3 儲存上傳文件及 PDF 報告。本地部署改用結構化本地目錄，並以 Celery Beat 定時任務模擬 S3 lifecycle policy 的 TTL 自動刪除行為。

**目錄結構：**

```
/data/
├── uploads/                          # 上傳的 Form 7501 文件（24h TTL）
│   └── {YYYY-MM-DD}/
│       └── {job_id}/
│           └── original.{ext}        # 加密儲存（AES-256-GCM）
├── reports/                          # 產製的 PDF 報告（15分鐘存取 token）
│   └── {calculation_id}/
│       └── report_{timestamp}.pdf
├── backups/
│   └── postgres/                     # 每日 DB 備份
└── keys/
    └── app_secret.key                # AES 加密主金鑰（權限 chmod 600，取代 AWS KMS）
```

**檔案存取安全：**

| 機制 | 說明 |
|------|------|
| **上傳文件加密** | 寫入磁碟前以 AES-256-GCM 加密（`cryptography.fernet`），金鑰存於 `keys/app_secret.key`，權限 `600` |
| **PDF 報告存取** | 產製後以 HMAC-SHA256 簽名產生帶時效（15 分鐘）的 Download Token，透過 `GET /api/v1/files/download?token=...` 驗證後才回傳檔案 |
| **TTL 清理任務** | Celery Beat 每小時執行一次，刪除 `uploads/` 下建立超過 24 小時的目錄 |
| **目錄不對外暴露** | Nginx 設定中 `/data/` 目錄不作為 static file 路徑，所有檔案存取均須通過 API 驗證 |

---

### 3.1.5 基礎設施與部署（Infrastructure — Local / Docker Compose）

> 原 TRS 使用 AWS ECS Fargate + ALB + CloudFront。本地部署以 Docker Compose 編排所有服務，Nginx 擔任反向代理與 TLS 終止節點。

**Docker Compose 服務清單：**

```yaml
# docker-compose.yml 服務組成
services:
  nginx:          # 反向代理 + TLS + 靜態資源服務（取代 ALB + CloudFront）
  frontend:       # React SPA build（Nginx 直接服務 dist/）
  api:            # FastAPI + Uvicorn/Gunicorn（2~N 個 replica）
  worker:         # Celery Worker（OCR / 計算 / CRM / 清理任務）
  beat:           # Celery Beat（定時任務排程）
  postgres:       # PostgreSQL 15
  redis:          # Redis 7
  smtp:           # MailHog（本地開發）/ 指向企業 SMTP relay（生產）
```

**Nginx 職責：**

| 功能 | 說明 |
|------|------|
| **TLS 終止** | Let's Encrypt（生產）/ 自簽憑證（開發），強制 TLS 1.3，停用 TLS 1.1/1.2 |
| **反向代理** | `location /api/` → FastAPI；`location /` → React SPA 靜態檔案 |
| **速率限制補充** | Nginx `limit_req` 模組作為 Application 層 slowapi 之前的第一道限流 |
| **HTTP 安全標頭** | `add_header` 注入 HSTS、X-Frame-Options、X-Content-Type-Options 等 |
| **Gzip 壓縮** | 壓縮 API 回應及靜態資源，降低頻寬消耗 |

**部署環境：**

| 環境 | URL（範例）| 啟動方式 |
|------|-----------|---------|
| **Development** | `http://localhost:5173`（Vite Dev Server）| `docker compose -f docker-compose.dev.yml up` |
| **Staging** | `https://staging.ieepa.dimerco.local` | `docker compose up --scale api=2` |
| **Production** | `https://ieepa.dimerco.com` | `docker compose up --scale api=4 -d` |

---

### 3.1.6 OCR 服務（OCR Services）

| 引擎 | 角色 | 觸發條件 |
|------|------|---------|
| **Google Document AI**（Form Parser）| 主要引擎 | 正常情況，呼叫 Google Cloud API |
| **pytesseract + pdf2image**（本地 Tesseract）| 備援引擎（取代 AWS Textract）| Google Document AI 回傳錯誤、網路不通、或整體信心 < 0.50 |

> **備援引擎說明**：本地 Tesseract OCR 準確度低於 Google Document AI，備援時若信心仍 < 0.50 則回傳 `UNRECOGNISED_DOCUMENT`，引導使用者手動輸入欄位值。

---

### 3.1.7 CRM 整合

| 項目 | 說明 |
|------|------|
| **整合方式** | Celery Worker 非同步呼叫 Dimerco CRM REST API |
| **重試策略** | 指數退避：第 1 次 1 分鐘、第 2 次 5 分鐘、第 3 次 30 分鐘 |
| **失敗處理** | 3 次重試後 `crm_sync_status = 'failed'`，記錄至 `audit_log`，觸發 email 告警 |
| **傳送欄位** | `full_name`, `company_name`, `email`, `phone`, `country`, `estimated_refund`, `refund_pathway`, `source: IEEPA_Calculator` |

---

### 3.1.8 密鑰與環境變數管理（取代 AWS Secrets Manager）

所有敏感設定透過 `.env` 檔案注入（`.env` 不可提交至 Git Repository）：

```dotenv
# .env.example（僅範例，不含真實值）

# Application
SECRET_KEY=<random-256-bit-hex>          # JWT 簽名金鑰
APP_ENCRYPTION_KEY=<fernet-key>          # AES-256 PII 加密主金鑰（取代 AWS KMS）
ALGORITHM=HS256

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/ieepa_refund_db

# Redis
REDIS_URL=redis://redis:6379/0

# OCR
GOOGLE_DOCUMENT_AI_PROJECT_ID=<gcp-project-id>
GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/gcp-service-account.json

# CRM
CRM_API_URL=https://crm.dimerco.com/api/v1
CRM_API_KEY=<crm-api-key>

# SMTP
SMTP_HOST=smtp.dimerco.com
SMTP_PORT=587
SMTP_USER=noreply@dimerco.com
SMTP_PASSWORD=<smtp-password>

# File Storage
UPLOAD_DIR=/data/uploads
REPORTS_DIR=/data/reports
FILE_ENCRYPTION_KEY_PATH=/data/keys/app_secret.key

# GA4
GA4_MEASUREMENT_ID=G-XXXXXXXXXX
```

**金鑰管理規範：**

| 金鑰 | 儲存位置 | 權限 | 輪換策略 |
|------|---------|------|---------|
| `APP_ENCRYPTION_KEY`（AES 主金鑰）| `/data/keys/app_secret.key` | `chmod 600`，僅 app user 可讀 | 每年或事故時人工輪換 |
| `SECRET_KEY`（JWT 簽名）| `.env` | 不提交 Git | 每 90 天或人員異動時輪換 |
| GCP Service Account JSON | `/app/secrets/`（Docker volume mount）| `chmod 600` | 每 90 天輪換 |

---

*Prepared by the Office of the CIO, Dimerco Express Group | Version 1.0 | March 2026 | Confidential*
