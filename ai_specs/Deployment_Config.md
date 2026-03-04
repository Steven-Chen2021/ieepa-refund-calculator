# Deployment Configuration
**Document Reference:** DMX-TRS-IEEPA-2026-001 (Local Deployment Edition)  
**Based On:** Tech_Stack.md · Security_Spec.md · API_Endpoint.md · Business_Rules.md  
**Owner:** Office of the CIO, Dimerco Express Group  
**Version:** 1.0 | March 2026 | Internal — Confidential

> ⚠️ **無 AWS 服務**：所有雲端元件均以本地等效方案取代（詳見 Tech_Stack.md §3.1 AWS→Local 對照表）。

---

## Section 9.1 — Environment（環境定義）

### 9.1.1 三種環境概覽

| 屬性 | Development (dev) | Staging | Production (prod) |
|------|-------------------|---------|-------------------|
| **目的** | 本機開發 / 單元測試 | 整合測試 / UAT | 正式對外服務 |
| **主機** | localhost | staging.ieepa.dimerco.local | ieepa.dimerco.com |
| **TLS** | 無（HTTP）| 自簽憑證 | 正式 CA 憑證 |
| **資料庫** | PostgreSQL（Docker）| PostgreSQL（Docker）| PostgreSQL（獨立主機）|
| **Email** | MailHog（瀏覽器預覽）| SMTP Relay（測試用）| 正式 SMTP Relay |
| **OCR 主要** | Google Document AI | Google Document AI | Google Document AI |
| **OCR 備援** | pytesseract（本地）| pytesseract（本地）| pytesseract（本地）|
| **Redis** | Redis（Docker）| Redis（Docker）| Redis（獨立主機）|
| **檔案儲存** | `/data/` 本地卷冊 | `/data/` 本地卷冊 | `/data/` 持久卷冊（NFS/LVM）|
| **Debug** | ✅ 開啟 | ❌ 關閉 | ❌ 關閉 |
| **Rate Limit** | 寬鬆（測試用）| 正式值 | 正式值 |
| **日誌等級** | DEBUG | INFO | WARNING |

---

### 9.1.2 環境變數矩陣（.env 檔案）

```dotenv
# =========================================================
# .env.example — 複製為 .env 並填入正確值
# 每個環境維護一份；生產環境檔案權限設為 chmod 600
# 絕對不要將 .env 提交至版本控制
# =========================================================

# ---------------------------------------------------------
# 基本設定
# ---------------------------------------------------------
ENVIRONMENT=development              # development | staging | production
DEBUG=true                           # dev: true | staging/prod: false
LOG_LEVEL=DEBUG                      # DEBUG | INFO | WARNING | ERROR
APP_HOST=0.0.0.0
APP_PORT=8000
SECRET_KEY=REPLACE_WITH_32_BYTE_RANDOM_HEX   # python -c "import secrets; print(secrets.token_hex(32))"
ALLOWED_HOSTS=localhost,127.0.0.1

# ---------------------------------------------------------
# CORS 設定
# ---------------------------------------------------------
CORS_ORIGINS=http://localhost:5173   # dev; staging: https://staging.ieepa.dimerco.local; prod: https://ieepa.dimerco.com
CORS_ALLOW_CREDENTIALS=true

# ---------------------------------------------------------
# JWT 設定
# ---------------------------------------------------------
JWT_SECRET_KEY=REPLACE_WITH_64_BYTE_RANDOM_HEX
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# ---------------------------------------------------------
# 資料庫 — PostgreSQL
# ---------------------------------------------------------
POSTGRES_HOST=db                     # dev/staging: db（Docker service）; prod: db.internal.dimerco.local
POSTGRES_PORT=5432
POSTGRES_DB=ieepa_refund_db
POSTGRES_USER=ieepa_app
POSTGRES_PASSWORD=REPLACE_WITH_STRONG_PASSWORD
DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}

# ---------------------------------------------------------
# Redis
# ---------------------------------------------------------
REDIS_HOST=redis                     # dev/staging: redis（Docker service）; prod: redis.internal.dimerco.local
REDIS_PORT=6379
REDIS_PASSWORD=REPLACE_WITH_REDIS_PASSWORD   # prod: 必填; dev: 可空白
REDIS_URL=redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/0
CELERY_BROKER_URL=${REDIS_URL}
CELERY_RESULT_BACKEND=${REDIS_URL}
CACHE_TTL_SECONDS=3600               # HTS 稅率快取 1 小時

# ---------------------------------------------------------
# 本地檔案系統（取代 AWS S3）
# ---------------------------------------------------------
DATA_ROOT=/data
UPLOAD_DIR=${DATA_ROOT}/uploads      # 加密的原始上傳文件
REPORTS_DIR=${DATA_ROOT}/reports     # 計算後的 PDF 報告
KEYS_DIR=${DATA_ROOT}/keys           # Fernet 對稱金鑰（chmod 600）
FERNET_KEY_PATH=${KEYS_DIR}/app_secret.key
MAX_UPLOAD_SIZE_MB=20
ALLOWED_EXTENSIONS=pdf,jpg,jpeg,png
DOWNLOAD_TOKEN_EXPIRE_MINUTES=15     # GET /api/v1/files/download?token= 時效

# ---------------------------------------------------------
# OCR 設定
# ---------------------------------------------------------
# 主要：Google Document AI
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/google_service_account.json
GOOGLE_DOC_AI_PROJECT_ID=REPLACE_WITH_GCP_PROJECT_ID
GOOGLE_DOC_AI_LOCATION=us
GOOGLE_DOC_AI_PROCESSOR_ID=REPLACE_WITH_PROCESSOR_ID

# 備援：pytesseract（本地 Tesseract）
TESSERACT_CMD=/usr/bin/tesseract     # Docker 內路徑
OCR_FALLBACK_ENABLED=true
OCR_CONFIDENCE_THRESHOLD=0.80        # < 0.80 → review_required

# ---------------------------------------------------------
# Email（取代 AWS SES）
# ---------------------------------------------------------
SMTP_HOST=mailhog                    # dev: mailhog（Docker）; staging/prod: smtp.internal.dimerco.local
SMTP_PORT=1025                       # dev: 1025（MailHog）; prod: 587（STARTTLS）
SMTP_USERNAME=                       # prod: 填入正式帳號
SMTP_PASSWORD=                       # prod: 填入正式密碼
SMTP_USE_TLS=false                   # dev: false; prod: true
SMTP_FROM_ADDRESS=noreply@ieepa.dimerco.com
SMTP_FROM_NAME=Dimerco IEEPA Portal

# ---------------------------------------------------------
# PII 加密（Fernet AES-256-GCM，取代 AWS KMS）
# ---------------------------------------------------------
# Fernet key 由下方初始化腳本生成，儲存於 FERNET_KEY_PATH
# 此 env var 僅供開發時覆蓋；生產環境從 FERNET_KEY_PATH 讀取

# ---------------------------------------------------------
# Rate Limiting（取代 AWS WAF）
# ---------------------------------------------------------
RATE_LIMIT_UPLOAD=10/hour            # slowapi（Layer 2）
RATE_LIMIT_CALCULATE=10/minute
RATE_LIMIT_LOGIN=5/minute
RATE_LIMIT_GET=60/minute

# ---------------------------------------------------------
# 功能開關
# ---------------------------------------------------------
ENABLE_BULK_UPLOAD=true
ENABLE_CRM_SYNC=false                # 開發時關閉
CRM_WEBHOOK_URL=                     # prod: 填入 CRM endpoint
CRM_API_KEY=                         # prod: 填入 CRM API key

# ---------------------------------------------------------
# 清理排程（Celery Beat）
# ---------------------------------------------------------
FILE_CLEANUP_TTL_HOURS=24            # 上傳文件 24 小時後清除
REPORT_CLEANUP_TTL_DAYS=90           # PDF 報告 90 天後清除
CLEANUP_SCHEDULE_CRON=0 * * * *      # 每整點執行
```

---

### 9.1.3 各環境 .env 覆蓋差異摘要

| 變數 | Development | Staging | Production |
|------|------------|---------|-----------|
| `ENVIRONMENT` | `development` | `staging` | `production` |
| `DEBUG` | `true` | `false` | `false` |
| `LOG_LEVEL` | `DEBUG` | `INFO` | `WARNING` |
| `SMTP_HOST` | `mailhog` | `smtp.internal.dimerco.local` | `smtp.internal.dimerco.local` |
| `SMTP_PORT` | `1025` | `587` | `587` |
| `SMTP_USE_TLS` | `false` | `true` | `true` |
| `REDIS_PASSWORD` | （空白）| 強密碼 | 強密碼 |
| `CRM_SYNC` | `false` | `false` | `true` |
| `CORS_ORIGINS` | `http://localhost:5173` | `https://staging.ieepa.dimerco.local` | `https://ieepa.dimerco.com` |

---

## Section 9.2 — Deployment Requirements（部署需求）

### 9.2.1 主機先決條件

| 需求 | 最低規格 | 建議規格 | 驗證指令 |
|------|---------|---------|---------|
| CPU | 4 vCPU | 8 vCPU | `nproc` |
| RAM | 8 GB | 16 GB | `free -h` |
| Disk（/data 卷冊）| 100 GB | 500 GB | `df -h /data` |
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS | `lsb_release -a` |
| Docker Engine | 24.0+ | 最新穩定版 | `docker --version` |
| Docker Compose | v2.20+ | 最新穩定版 | `docker compose version` |
| Git | 2.x | — | `git --version` |
| 開放 Ports | 80, 443 對外 | — | `ss -tlnp` |

---

### 9.2.2 Docker Compose — Development（docker-compose.yml）

```yaml
# docker-compose.yml（Development）
version: "3.9"

services:

  # ─────────────────────────────────────────────────────────
  # Frontend（Vite Dev Server，含 HMR）
  # ─────────────────────────────────────────────────────────
  frontend:
    build:
      context: ./frontend
      target: development
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
      - /app/node_modules
    environment:
      VITE_API_BASE_URL: http://localhost:8000
    depends_on:
      - api

  # ─────────────────────────────────────────────────────────
  # Backend API（FastAPI + Uvicorn，--reload）
  # ─────────────────────────────────────────────────────────
  api:
    build:
      context: ./backend
      target: development
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
      - ./data:/data
    env_file:
      - .env
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

  # ─────────────────────────────────────────────────────────
  # Celery Worker（背景任務：OCR、計算、PDF 生成、清理）
  # ─────────────────────────────────────────────────────────
  worker:
    build:
      context: ./backend
      target: development
    volumes:
      - ./backend:/app
      - ./data:/data
    env_file:
      - .env
    command: celery -A app.celery_app worker --loglevel=debug --concurrency=4
    depends_on:
      - redis
      - db

  # ─────────────────────────────────────────────────────────
  # Celery Beat（排程任務：檔案清理、TTL）
  # ─────────────────────────────────────────────────────────
  beat:
    build:
      context: ./backend
      target: development
    volumes:
      - ./backend:/app
      - ./data:/data
    env_file:
      - .env
    command: celery -A app.celery_app beat --loglevel=info
    depends_on:
      - redis

  # ─────────────────────────────────────────────────────────
  # PostgreSQL 15
  # ─────────────────────────────────────────────────────────
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: ieepa_refund_db
      POSTGRES_USER: ieepa_app
      POSTGRES_PASSWORD: dev_password_only
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"          # 本機可直接存取（僅 dev）
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ieepa_app -d ieepa_refund_db"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ─────────────────────────────────────────────────────────
  # Redis 7
  # ─────────────────────────────────────────────────────────
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"          # 僅 dev 對外暴露
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ─────────────────────────────────────────────────────────
  # MailHog（取代 AWS SES，開發環境 SMTP）
  # ─────────────────────────────────────────────────────────
  mailhog:
    image: mailhog/mailhog:latest
    ports:
      - "1025:1025"          # SMTP
      - "8025:8025"          # Web UI（瀏覽器查看郵件）

volumes:
  postgres_data:
```

---

### 9.2.3 Docker Compose — Production（docker-compose.prod.yml）

```yaml
# docker-compose.prod.yml（Production / Staging 共用，以環境變數區分）
version: "3.9"

services:

  # ─────────────────────────────────────────────────────────
  # Nginx（反向代理 + TLS + 靜態資源，取代 ALB+CloudFront）
  # ─────────────────────────────────────────────────────────
  nginx:
    image: nginx:1.25-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/certs:/etc/nginx/certs:ro    # TLS 憑證
      - ./frontend/dist:/usr/share/nginx/html:ro
      - nginx_logs:/var/log/nginx
    depends_on:
      - api
    restart: always

  # ─────────────────────────────────────────────────────────
  # Backend API（Gunicorn + Uvicorn Workers）
  # ─────────────────────────────────────────────────────────
  api:
    image: dimerco/ieepa-api:${APP_VERSION:-latest}
    build:
      context: ./backend
      target: production
    volumes:
      - /data:/data                   # 持久卷冊掛載
      - ./credentials:/app/credentials:ro  # Google Service Account
    env_file:
      - .env
    command: >
      gunicorn app.main:app
        -w 4 -k uvicorn.workers.UvicornWorker
        --bind 0.0.0.0:8000
        --access-logfile -
        --error-logfile -
        --timeout 120
    expose:
      - "8000"
    depends_on:
      - redis
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # ─────────────────────────────────────────────────────────
  # Celery Worker（生產：4 worker，concurrency=8）
  # ─────────────────────────────────────────────────────────
  worker:
    image: dimerco/ieepa-api:${APP_VERSION:-latest}
    volumes:
      - /data:/data
      - ./credentials:/app/credentials:ro
    env_file:
      - .env
    command: >
      celery -A app.celery_app worker
        --loglevel=warning
        --concurrency=8
        --queues=ocr,calculation,reports,cleanup
    depends_on:
      - redis
    restart: always

  # ─────────────────────────────────────────────────────────
  # Celery Beat
  # ─────────────────────────────────────────────────────────
  beat:
    image: dimerco/ieepa-api:${APP_VERSION:-latest}
    volumes:
      - /data:/data
    env_file:
      - .env
    command: celery -A app.celery_app beat --loglevel=warning
    depends_on:
      - redis
    restart: always

  # ─────────────────────────────────────────────────────────
  # Redis（生產：需設密碼，不對外暴露 port）
  # ─────────────────────────────────────────────────────────
  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD} --appendonly yes
    volumes:
      - redis_data:/data
    expose:
      - "6379"
    restart: always

volumes:
  redis_data:
  nginx_logs:
```

---

### 9.2.4 Nginx 完整設定（nginx/nginx.conf）

```nginx
# nginx/nginx.conf

user  nginx;
worker_processes  auto;

error_log  /var/log/nginx/error.log warn;
pid        /var/run/nginx.pid;

events {
    worker_connections  4096;
    use epoll;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    # 日誌格式（含 X-Request-ID）
    log_format  main  '$remote_addr - $remote_user [$time_local] "$request" '
                      '$status $body_bytes_sent "$http_referer" '
                      '"$http_user_agent" "$http_x_forwarded_for" '
                      'rid=$request_id';
    access_log  /var/log/nginx/access.log  main;

    sendfile        on;
    keepalive_timeout  65;
    server_tokens   off;      # 不暴露 Nginx 版本

    # ── 全域安全標頭 ─────────────────────────────────────
    add_header X-Frame-Options            "DENY"                      always;
    add_header X-Content-Type-Options     "nosniff"                   always;
    add_header X-XSS-Protection           "0"                         always;
    add_header Referrer-Policy            "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy         "geolocation=(), camera=(), microphone=()" always;
    add_header Content-Security-Policy    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; form-action 'self';" always;

    # ── Rate Limiting（取代 AWS WAF Layer 1）────────────
    limit_req_zone  $binary_remote_addr  zone=upload:10m   rate=10r/h;
    limit_req_zone  $binary_remote_addr  zone=login:10m    rate=5r/m;
    limit_req_zone  $binary_remote_addr  zone=api:10m      rate=60r/m;
    limit_req_status 429;

    # ── HTTP → HTTPS 重導向 ──────────────────────────────
    server {
        listen 80;
        server_name _;
        return 301 https://$host$request_uri;
    }

    # ── 主要 HTTPS Server ────────────────────────────────
    server {
        listen 443 ssl http2;
        server_name ieepa.dimerco.com;    # Staging: staging.ieepa.dimerco.local

        # TLS 設定（僅 1.3）
        ssl_certificate     /etc/nginx/certs/fullchain.pem;
        ssl_certificate_key /etc/nginx/certs/privkey.pem;
        ssl_protocols       TLSv1.3;
        ssl_ciphers         TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256;
        ssl_prefer_server_ciphers off;
        ssl_session_cache   shared:SSL:10m;
        ssl_session_timeout 10m;
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

        # 最大上傳大小（FR-021：20 MB）
        client_max_body_size 20M;

        # 請求 ID
        add_header X-Request-ID $request_id always;

        # ── 靜態資源（React Build）───────────────────────
        root /usr/share/nginx/html;
        index index.html;

        location / {
            try_files $uri $uri/ /index.html;
            limit_req zone=api burst=20 nodelay;
        }

        # ── API 反向代理 ─────────────────────────────────
        location /api/ {
            proxy_pass         http://api:8000;
            proxy_http_version 1.1;
            proxy_set_header   Host              $host;
            proxy_set_header   X-Real-IP         $remote_addr;
            proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
            proxy_set_header   X-Forwarded-Proto $scheme;
            proxy_set_header   X-Request-ID      $request_id;
            proxy_read_timeout 120s;

            limit_req zone=api burst=30 nodelay;
        }

        # ── 上傳端點（更嚴格的 Rate Limit）──────────────
        location /api/v1/documents/upload {
            proxy_pass         http://api:8000;
            proxy_set_header   Host              $host;
            proxy_set_header   X-Real-IP         $remote_addr;
            proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
            proxy_set_header   X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;   # 允許較長的 OCR 處理時間
            client_max_body_size 20M;

            limit_req zone=upload burst=5 nodelay;
        }

        # ── 登入端點（防暴力破解）────────────────────────
        location /api/v1/auth/token {
            proxy_pass         http://api:8000;
            proxy_set_header   Host $host;
            proxy_set_header   X-Real-IP $remote_addr;
            proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header   X-Forwarded-Proto $scheme;

            limit_req zone=login burst=2 nodelay;
        }

        # ── Health Check（不受 Rate Limit）───────────────
        location /health {
            proxy_pass http://api:8000/health;
            access_log off;
        }
    }
}
```

---

### 9.2.5 Dockerfile（多階段建置）

**backend/Dockerfile:**
```dockerfile
# ── Stage 1: Base ────────────────────────────────────────
FROM python:3.11-slim AS base
WORKDIR /app

# 系統依賴（含 Tesseract + poppler for OCR fallback）
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-chi-sim \
    poppler-utils \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Development ────────────────────────────────
FROM base AS development
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .
EXPOSE 8000

# ── Stage 3: Production ─────────────────────────────────
FROM base AS production
# 非 root 用戶執行（安全性）
RUN groupadd -r appuser && useradd -r -g appuser appuser
COPY . .
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
```

**frontend/Dockerfile:**
```dockerfile
# ── Stage 1: Development ────────────────────────────────
FROM node:20-alpine AS development
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]

# ── Stage 2: Build ──────────────────────────────────────
FROM development AS builder
RUN npm run build

# ── Stage 3: Production（Nginx 靜態服務）────────────────
FROM nginx:1.25-alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.frontend.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

---

### 9.2.6 逐步部署流程

#### 初次部署（Development）

```bash
# 1. 複製專案
git clone https://github.com/dimerco/ieepa-portal.git
cd ieepa-portal

# 2. 初始化環境變數
cp .env.example .env
# 編輯 .env，填入必要值（DB 密碼、JWT secret 等）

# 3. 建立 /data 目錄結構
mkdir -p data/{uploads,reports,keys}
chmod 700 data/keys

# 4. 生成 Fernet 加密金鑰（取代 AWS KMS）
python -c "
from cryptography.fernet import Fernet
key = Fernet.generate_key()
with open('data/keys/app_secret.key', 'wb') as f:
    f.write(key)
import os; os.chmod('data/keys/app_secret.key', 0o600)
print('Fernet key generated successfully')
"

# 5. 啟動所有服務
docker compose up -d

# 6. 等待 DB 健康檢查通過後執行 Migration
sleep 15
docker compose exec api alembic upgrade head

# 7. 植入初始資料（稅率種子資料、Admin 帳號）
docker compose exec api python scripts/seed_tariff_rates.py
docker compose exec api python scripts/create_admin.py \
  --email admin@dimerco.com \
  --password "CHANGE_THIS_IMMEDIATELY"

# 8. 驗證服務
curl http://localhost:8000/health
# 預期回應：{"status":"healthy","version":"1.0.0","db":"connected","redis":"connected"}
```

---

#### 生產部署流程

```bash
# 1. 建置並推送 Docker Image
docker build -t dimerco/ieepa-api:${VERSION} --target production ./backend
docker build -t dimerco/ieepa-frontend:${VERSION} --target production ./frontend

# 2. 傳送 Image 到生產主機（無私有 Registry 時）
docker save dimerco/ieepa-api:${VERSION} | gzip | \
  ssh prod-server "docker load"

# 3. 在生產主機執行
ssh prod-server << 'EOF'
  cd /opt/ieepa-portal
  export APP_VERSION=<NEW_VERSION>
  
  # Zero-downtime 更新（先啟動新容器，再停舊容器）
  docker compose -f docker-compose.prod.yml pull
  docker compose -f docker-compose.prod.yml up -d --no-deps api worker beat
  
  # 執行 Migration（僅 API 服務）
  docker compose -f docker-compose.prod.yml exec api alembic upgrade head
  
  # 確認健康狀態
  curl https://ieepa.dimerco.com/health
EOF

# 4. 驗證 Smoke Test
curl -k https://ieepa.dimerco.com/api/v1/tariff-rates/8471300100
```

---

### 9.2.7 Alembic 資料庫 Migration

```bash
# 建立新 Migration
docker compose exec api alembic revision --autogenerate -m "add_calculation_audit_table"

# 套用所有未執行的 Migration（向前）
docker compose exec api alembic upgrade head

# 回退一個版本（緊急回滾）
docker compose exec api alembic downgrade -1

# 查看當前版本
docker compose exec api alembic current

# 查看 Migration 歷史
docker compose exec api alembic history --verbose
```

---

### 9.2.8 Health Check Endpoints

| Endpoint | 用途 | 預期回應 | 監控頻率 |
|---------|------|---------|---------|
| `GET /health` | 服務整體健康 | `{"status":"healthy","db":"connected","redis":"connected"}` | 30 秒 |
| `GET /health/db` | 資料庫連線 | `{"status":"ok","latency_ms":5}` | 60 秒 |
| `GET /health/redis` | Redis 連線 | `{"status":"ok","latency_ms":1}` | 60 秒 |
| `GET /health/worker` | Celery Worker | `{"status":"ok","active_tasks":0,"reserved_tasks":0}` | 60 秒 |

---

### 9.2.9 備份與還原

```bash
# ── 資料庫備份 ──────────────────────────────────────────
# 每日備份（建議設定 cron job）
BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
docker compose -f docker-compose.prod.yml exec db pg_dump \
  -U ieepa_app ieepa_refund_db | gzip > \
  /opt/backups/db/ieepa_${BACKUP_DATE}.sql.gz

# 還原資料庫
gunzip -c /opt/backups/db/ieepa_YYYYMMDD_HHMMSS.sql.gz | \
  docker compose exec -T db psql -U ieepa_app ieepa_refund_db

# ── 加密金鑰備份（極機密）──────────────────────────────
# Fernet Key 離線備份：每次金鑰輪換後執行
cp /data/keys/app_secret.key /opt/backups/keys/app_secret_${BACKUP_DATE}.key
chmod 600 /opt/backups/keys/app_secret_${BACKUP_DATE}.key

# ── /data 目錄備份 ──────────────────────────────────────
# 每日備份上傳文件與報告
rsync -avz --delete /data/uploads/ /opt/backups/uploads_${BACKUP_DATE}/
rsync -avz --delete /data/reports/ /opt/backups/reports_${BACKUP_DATE}/

# ── Redis 快照備份（非必要，可重建）────────────────────
docker compose exec redis redis-cli BGSAVE
cp /var/lib/docker/volumes/ieepa_redis_data/_data/dump.rdb \
   /opt/backups/redis/dump_${BACKUP_DATE}.rdb
```

---

### 9.2.10 回滾程序

```bash
# 程式碼回滾（生產）
ssh prod-server << 'EOF'
  cd /opt/ieepa-portal
  
  # 1. 回退 API 到前一個版本
  export APP_VERSION=<PREVIOUS_VERSION>
  docker compose -f docker-compose.prod.yml up -d --no-deps api worker beat
  
  # 2. 如有 Schema 變更，回退 Migration
  docker compose -f docker-compose.prod.yml exec api alembic downgrade -1
  
  # 3. 確認健康
  curl https://ieepa.dimerco.com/health
EOF
```

---

### 9.2.11 上線前檢核清單（Pre-Launch Checklist）

此清單對應 TRS §14 驗收標準，部署正式環境前須逐項確認。

| # | 項目 | 驗證方法 | 負責人 | 狀態 |
|---|------|---------|-------|------|
| 1 | TLS 1.3 設定正確（無 TLS 1.2 或以下） | `openssl s_client -connect ieepa.dimerco.com:443 -tls1_2` 應失敗 | DevOps | ☐ |
| 2 | HTTP 安全標頭完整（X-Frame-Options, CSP 等） | `curl -I https://ieepa.dimerco.com` 逐項核對 | DevOps | ☐ |
| 3 | Rate Limiting 生效 | 觸發 429 並確認 `Retry-After` 標頭存在 | QA | ☐ |
| 4 | 檔案 Magic Bytes 驗證生效（拒絕偽裝 PDF 的 EXE）| TC-OCR-006 Case D | QA | ☐ |
| 5 | PII 欄位已加密儲存（直接查 DB 確認密文）| TC-SEC-002 | QA | ☐ |
| 6 | 計算稽核不可刪除（DB trigger 確認）| TC-CALC-010 | Dev | ☐ |
| 7 | Admin 帳號預設密碼已修改 | 登入測試 | Admin | ☐ |
| 8 | Admin 帳號至少 2 人（TRS §4.3）| DB 查詢 `SELECT count(*) FROM users WHERE role='admin'` | Admin | ☐ |
| 9 | OCR 準確率 ≥ 95%（TC-OCR-001 通過）| pytest 測試報告 | QA | ☐ |
| 10 | CHB 驗算案例 CHB-001/002/003 差異 ≤ 2%（TC-CALC-011）| 人工核對 | 業務 | ☐ |
| 11 | 稅率種子資料已植入（MFN、IEEPA、S301、S232）| `GET /api/v1/admin/rates` 確認筆數 | Dev | ☐ |
| 12 | 備份程序已測試（DB 備份 + 還原成功）| 乾跑還原至 staging | DevOps | ☐ |
| 13 | Fernet Key 離線備份已完成 | 確認 `/opt/backups/keys/` 目錄 | DevOps | ☐ |
| 14 | `/data` 目錄掛載為持久卷冊（非容器內部）| `docker inspect` 確認 mounts | DevOps | ☐ |
| 15 | 免責聲明（Disclaimer）在 Results 頁面顯示且不可關閉 | E2E TC-E2E-001 Step 8 | QA | ☐ |
| 16 | Privacy Consent checkbox 為必填（不勾選無法上傳）| TC-FE-001 | QA | ☐ |
| 17 | Email 驗證流程完整可用（新用戶收到信並可驗證）| TC-API-004 | QA | ☐ |
| 18 | CRM Webhook 連線測試通過（若 staging 已開啟）| `POST /api/v1/leads` 後確認 CRM 有資料 | 業務 | ☐ |
| 19 | `bandit` 零個 HIGH/CRITICAL 問題 | CI 報告 | Dev | ☐ |
| 20 | `pip-audit` + `npm audit` 零個 CRITICAL 漏洞 | CI 報告 | Dev | ☐ |

---

### 9.2.12 CI/CD Pipeline 概要（GitHub Actions）

```yaml
# .github/workflows/ci.yml（供 AI agent 開發參考）
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:

jobs:
  backend-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: ieepa_test_db
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
        options: --health-cmd pg_isready --health-interval 10s
      redis:
        image: redis:7
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r backend/requirements.txt -r backend/requirements-dev.txt
      - run: cd backend && pytest --cov=app --cov-fail-under=80 -v
      - run: cd backend && bandit -r app/ -ll
      - run: cd backend && pip-audit

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: cd frontend && npm ci
      - run: cd frontend && npm run test:coverage -- --coverage.lines=75
      - run: cd frontend && npm audit --audit-level=critical

  e2e-tests:
    runs-on: ubuntu-latest
    needs: [backend-tests, frontend-tests]
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - run: docker compose up -d
      - run: sleep 30 && docker compose exec api alembic upgrade head
      - run: cd e2e && npx playwright install --with-deps
      - run: cd e2e && npx playwright test
```

---

*Prepared by the Office of the CIO, Dimerco Express Group | Version 1.0 | March 2026 | Confidential*
