# IEEPA Tariff Refund Calculator

> **Internal Tool — Dimerco Express Group**  
> Document Reference: DMX-TRS-IEEPA-2026-001 | Version 1.0 | March 2026 | Confidential

A web-based portal that allows U.S. importers and licensed customs brokers to upload CBP Form 7501 PDFs, receive an itemised tariff breakdown (MFN / IEEPA / Section 301 / Section 232 / MPF / HMF), and obtain an estimated IEEPA refund amount with a recommended refund pathway (PSC / Protest / Ineligible).

---

## Table of Contents

- [Background](#background)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [API Overview](#api-overview)
- [Business Rules](#business-rules)
- [Security](#security)
- [Testing](#testing)
- [Deployment](#deployment)

---

## Background

Since 2025, the United States has imposed additional IEEPA tariffs on goods of Chinese origin under the International Emergency Economic Powers Act. Most importers are unaware that:

- Paid IEEPA tariffs may be refundable.
- Refund pathways (Post-Summary Correction / Protest) have strict deadlines.
- Correct calculation requires complex HTS rate decomposition and CBP rule knowledge.

This tool automates the entire process — from OCR extraction of Form 7501 fields to a one-click refund estimate with pathway recommendation.

---

## Features

| Feature | Description |
|---------|-------------|
| **PDF/Image Upload** | Upload CBP Form 7501 (PDF, JPEG, PNG) with drag-and-drop |
| **OCR Extraction** | Google Document AI (primary) + pytesseract (fallback) |
| **Field Review** | Low-confidence fields highlighted for manual correction |
| **Tariff Breakdown** | Itemised MFN / IEEPA / S301 / S232 / MPF / HMF per line item |
| **Refund Estimate** | Total estimated IEEPA refund with confidence score |
| **Pathway Recommendation** | PSC (≤ 15 days) / Protest (16–180 days) / Ineligible (> 180 days) |
| **PDF Report** | Downloadable branded report with HMAC-signed time-limited token |
| **Bilingual UI** | English / Simplified Chinese (zh-CN) |
| **Bulk Upload** | CSV/XLSX batch processing for registered users |
| **Admin Portal** | HTS rate management, lead list, usage analytics |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Tier 1: Presentation (Frontend)             │
│         React 18 SPA  ←→  Nginx (static + proxy)        │
└─────────────────────────┬───────────────────────────────┘
                          │ HTTP/HTTPS (TLS via Nginx)
┌─────────────────────────▼───────────────────────────────┐
│              Tier 2: Application (Backend)               │
│    FastAPI (Uvicorn/Gunicorn)  +  Celery Workers         │
└──────┬──────────────────────────────────┬───────────────┘
       │ SQLAlchemy (async)               │ Redis (queue/cache)
┌──────▼──────────────────────────────────▼───────────────┐
│              Tier 3: Data                                 │
│    PostgreSQL 15  |  Redis 7  |  Local File System       │
└─────────────────────────────────────────────────────────┘
```

### Request Flow

1. `POST /api/v1/documents/upload` → validates MIME + magic bytes, encrypts file to `/data/uploads/`, queues Celery OCR job, returns `{ job_id }`
2. Celery worker runs OCR (Google Document AI primary; pytesseract fallback if confidence < 0.50 or API error)
3. Frontend polls `GET /api/v1/documents/{job_id}/status` until `completed` or `review_required`
4. User reviews fields on `/review`; low-confidence fields (< 0.80) shown with amber highlight; corrections saved via `PATCH /api/v1/documents/{job_id}/fields`
5. `POST /api/v1/documents/{job_id}/calculate` → runs BR-001–BR-011 calculation engine in-process, writes immutable `calculation_audit` row, returns `{ calculation_id }`
6. Frontend navigates to `/results/:id` via `GET /api/v1/results/{calculation_id}`
8. PDF export: `POST /api/v1/results/{calculation_id}/export` → WeasyPrint → HMAC-signed download token (15 min TTL)
9. Lead capture: `POST /api/v1/leads` → AES-256-GCM encrypts PII → async CRM sync via Celery

---

## Tech Stack

### Backend

| Category | Package | Version | Purpose |
|----------|---------|---------|---------|
| Language | Python | 3.11+ | Primary backend language |
| Web Framework | FastAPI | 0.110+ | Async REST API, OpenAPI 3.1 docs |
| ASGI Server | Uvicorn + Gunicorn | — | Production process management |
| Task Queue | Celery | 5.x | Async jobs (OCR, calculation, CRM sync, cleanup) |
| Queue Broker | Redis | 7.x | Celery broker + result backend |
| ORM | SQLAlchemy | 2.0 async | Database access with parameterised queries |
| Migrations | Alembic | — | Schema version control |
| Validation | Pydantic | v2 | All request/response schemas |
| JWT | PyJWT | 2.x | Access token (15 min) + Refresh token (7 days) |
| Password | passlib[bcrypt] | — | bcrypt work factor ≥ 12 |
| Encryption | cryptography (Fernet) | — | AES-256 file encryption + PII field encryption |
| PDF | WeasyPrint | — | Server-side HTML → PDF generation |
| OCR Primary | Google Document AI | — | Form Parser for CBP Form 7501 |
| OCR Fallback | pytesseract + pdf2image | — | Local Tesseract fallback |
| Rate Limiting | slowapi | — | Per-IP rate limiting (backed by Redis) |
| MIME Detection | python-magic | 0.4.27 | Magic bytes validation (SEC-007) |

### Frontend

| Category | Package | Version | Purpose |
|----------|---------|---------|---------|
| Framework | React | 18.x | Function components + hooks |
| Language | TypeScript | 5.x (strict) | Type-safe UI |
| Styling | Tailwind CSS | v3.x | Utility-first CSS only |
| Global State | Zustand | 4.x | Upload progress, auth session |
| Server State | TanStack Query | v5.x | API caching, OCR status polling |
| Routing | React Router | v6.x | SPA routing with protected routes |
| Forms | React Hook Form + Zod | — | Controlled forms with schema validation |
| HTTP | Axios | 1.x | Interceptors for JWT injection |
| Build | Vite | 5.x | Dev HMR + production bundling |
| i18n | react-i18next | — | en / zh-CN language switching |
| Testing | Vitest + RTL | — | Unit tests (≥ 75% coverage) |
| E2E | Playwright | — | Critical user journey automation |

---

## Project Structure

```
backend/
  app/
    api/v1/
      endpoints/
        auth.py          # POST /auth/token, /refresh, /logout
        documents.py     # POST /upload, GET /{job_id}/status, PATCH /{job_id}/fields, POST /{job_id}/calculate
        results.py       # GET /results/{calculation_id}
      router.py          # API v1 router wiring
    core/
      config.py          # Settings (pydantic-settings + .env)
      dependencies.py    # FastAPI Depends() factories (get_current_user, get_db, get_redis, …)
      limiter.py         # slowapi Limiter singleton
      security.py        # JWT helpers, bcrypt, Redis token blacklist
    db/
      base.py            # SQLAlchemy declarative base
      session.py         # Async engine + get_db() dependency
    engine/
      calculator.py      # BR-001–BR-011 tariff calculation engine
    middleware/
      security_headers.py # CSP, HSTS, X-Frame-Options, etc.
    models/              # SQLAlchemy ORM models
    ocr/
      crypto.py          # Fernet file encrypt/decrypt
      google_docai.py    # Google Document AI integration
      models.py          # OcrField, OcrResult dataclasses
      tesseract.py       # pytesseract fallback
    schemas/             # Pydantic v2 request/response schemas
    tasks/
      ocr.py             # process_ocr_job Celery task
    main.py              # FastAPI app factory
    celery_app.py        # Celery app instance
  alembic/               # DB migrations
  tests/
    unit/
    integration/
frontend/
  index.html             # HTML entry point
  package.json           # npm dependencies (React 18, Vite 5, Tailwind 3, TanStack Query v5, …)
  vite.config.ts         # Vite config — dev server port 5173, /api proxy → localhost:8000
  tsconfig.json          # TypeScript strict mode config
  tailwind.config.js     # Tailwind content paths + brand colour tokens
  postcss.config.js      # PostCSS (Tailwind + Autoprefixer)
  src/
    main.tsx             # React root — QueryClientProvider + BrowserRouter
    App.tsx              # Route definitions (/, /calculate, /review, /results/:id, /register, …)
    index.css            # Tailwind directives (@tailwind base/components/utilities)
    components/{ui,forms,layout}/
    pages/               # Route-level components (HomePage, CalculatePage, ReviewPage, ResultsPage)
    hooks/               # Custom React hooks
    store/               # Zustand global state
    i18n/                # en.json + zh-CN.json
nginx/                   # Reverse proxy config
data/                    # Runtime data (uploads/, reports/, keys/) — gitignored
ai_specs/                # Authoritative specification documents
```

---

## Getting Started

### Prerequisites

- Docker 24+ and Docker Compose v2
- GCP service account JSON with Document AI access (optional — falls back to pytesseract)

### 1. Clone and configure

```bash
git clone https://github.com/Steven-Chen2021/ieepa-refund-calculator.git
cd ieepa-refund-calculator

# Copy environment template
cp backend/.env.example backend/.env
# Edit backend/.env and fill in all required values
```

### 2. Generate encryption key

```bash
python init_keys.py
# Creates data/keys/app_secret.key (chmod 600, gitignored)
```

### 3. Start services

```bash
# Start all backend services (API, Celery, DB, Redis, MailHog)
docker compose up -d

# Apply database migrations (first time only)
docker compose exec api alembic upgrade head
```

### 4. Start the frontend dev server

The frontend runs separately from Docker using the local Node.js toolchain:

```bash
cd frontend
npm install      # first time only
npm run dev      # starts Vite dev server on http://localhost:5173
```

> The Vite dev server proxies `/api/*` requests to `http://localhost:8000` automatically.

### 5. Access the application

| Service | URL |
|---------|-----|
| Frontend (dev) | http://localhost:5173 |
| API | http://localhost:8000 |
| API Docs (Swagger UI) | http://localhost:8000/api/docs |
| Health check | http://localhost:8000/health |
| MailHog (dev SMTP) | http://localhost:8025 |

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env`. Key variables:

```dotenv
# Application
SECRET_KEY=<random-256-bit-hex>
ENVIRONMENT=development          # development | staging | production

# JWT
JWT_SECRET_KEY=<random-secret>
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# Database
POSTGRES_USER=ieepa_app
POSTGRES_PASSWORD=<strong-password>
POSTGRES_DB=ieepa_refund_db

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# File storage
FERNET_KEY_PATH=/data/keys/app_secret.key
MAX_UPLOAD_SIZE_MB=20

# OCR (optional — falls back to pytesseract)
GOOGLE_DOC_AI_PROJECT_ID=<gcp-project-id>
GOOGLE_DOC_AI_PROCESSOR_ID=<processor-id>
GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/gcp-service-account.json

# Rate limiting
RATE_LIMIT_UPLOAD=10/hour
RATE_LIMIT_LOGIN=5/minute
```

> ⚠️ **Never commit `.env` or `data/keys/app_secret.key`** — both are gitignored. Back up `app_secret.key` offline.

---

## API Overview

All endpoints are prefixed with `/api/v1`. Interactive docs available at `/api/docs`.

### Authentication

| Method | Endpoint | Description | Rate Limit |
|--------|----------|-------------|-----------|
| `POST` | `/auth/token` | Login → access token + refresh cookie | 5/min |
| `POST` | `/auth/refresh` | Rotate refresh token | — |
| `POST` | `/auth/logout` | Revoke refresh token + clear cookie | — |

**JWT payload:** `{ sub: uuid, role: "user"\|"admin", email, iat, exp }`  
**Refresh token:** stored in `httpOnly; Secure; SameSite=Strict` cookie (not localStorage)

### Documents

| Method | Endpoint | Description | Auth | Rate Limit |
|--------|----------|-------------|------|-----------|
| `POST` | `/documents/upload` | Upload Form 7501, queue OCR job | Optional | 10/hour |
| `GET` | `/documents/{job_id}/status` | Poll OCR status + extracted fields | Session/JWT | 60/min |
| `PATCH` | `/documents/{job_id}/fields` | Save user corrections | Session/JWT | — |
| `POST` | `/documents/{job_id}/calculate` | Run tariff calculation (BR-001–BR-011), returns `calculation_id` | Session/JWT | 20/min |

**Upload response (202):**
```json
{
  "success": true,
  "data": {
    "job_id": "uuid",
    "status": "queued",
    "expires_at": "2026-03-05T09:55:26Z"
  }
}
```

**Calculate response (202):**
```json
{
  "success": true,
  "data": { "calculation_id": "uuid" }
}
```

### Results

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| `GET` | `/results/{calculation_id}` | Retrieve completed calculation result | — |

**Result response (200):**
```json
{
  "success": true,
  "data": {
    "calculation_id": "uuid",
    "entry_number": "...",
    "summary_date": "2026-01-28",
    "country_of_origin": "CN",
    "estimated_refund": 1234.56,
    "refund_pathway": "PROTEST",
    "days_elapsed": 35,
    "tariff_lines": [
      { "tariff_type": "MFN",   "rate": 0.075,   "amount": 375.00, "refundable": false },
      { "tariff_type": "IEEPA", "rate": 0.20,    "amount": 1000.00,"refundable": true  },
      { "tariff_type": "MPF",   "rate": 0.003464,"amount": 173.20, "refundable": false },
      { "tariff_type": "HMF",   "rate": 0.00125, "amount": 62.50,  "refundable": false }
    ],
    "total_duty": 1610.70
  }
}
```

> Returns **HTTP 202** while calculation is still in progress (frontend polls until 200).

### Standard Response Envelope

```json
{
  "success": true | false,
  "data": { ... } | null,
  "error": { "code": "ERROR_CODE", "message": "..." } | null,
  "meta": { "page": 1, "total": 100 } | null
}
```

---

## Business Rules

All calculation logic strictly follows `ai_specs/Business_Rules.md` (BR-001 through BR-011).

### Key Rules

| Rule | Description |
|------|-------------|
| **BR-001** | IEEPA applies **only** to `country_of_origin = 'CN'`; all other origins return IEEPA = $0 |
| **BR-003** | MPF floor **$32.71**, cap **$634.62** — both boundaries always enforced |
| **BR-004** | HMF applies **only** when `mode_of_transport = 'vessel'`; air cargo → HMF = $0 |
| **BR-007** | Refund pathway by days since entry summary date: ≤ 15 days → **PSC**, 16–180 days → **PROTEST**, > 180 days → **INELIGIBLE** |
| **BR-010** | OCR field confidence < 0.80 → `review_required: true` (amber highlight in UI) |
| **BR-011** | `calculation_audit` is **append-only** — no UPDATE or DELETE ever |

### Tariff Breakdown Order

```
Total Duty = MFN + IEEPA + Section 301 + Section 232 + MPF + HMF
Estimated Refund = IEEPA component (if CN origin + within deadline)
```

---

## Security

Implemented per `ai_specs/Security_Spec.md`.

| Control | Implementation |
|---------|----------------|
| **File MIME validation** | `python-magic` magic bytes check (SEC-007) — Content-Type header alone is not trusted |
| **File encryption** | Fernet AES-256 before writing to disk; key at `/data/keys/app_secret.key` (chmod 600) |
| **PII encryption** | `email`, `phone`, `full_name` in `leads` table encrypted with Fernet before write |
| **JWT** | HS256, 15-min access token in memory; 7-day refresh token in `httpOnly` cookie |
| **Refresh token rotation** | Old JTI blacklisted in Redis on every `/auth/refresh` call |
| **Rate limiting** | slowapi (Redis-backed) + Nginx `limit_req` outer layer |
| **Security headers** | CSP, HSTS, X-Frame-Options: DENY, X-Content-Type-Options, Referrer-Policy, Permissions-Policy |
| **SQL injection** | SQLAlchemy parameterised queries only — no raw string interpolation |
| **Bcrypt** | Work factor ≥ 12 |

### Security Headers (injected on every response)

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

> **Docs exception:** `/api/docs`, `/api/redoc`, and `/api/openapi.json` receive a relaxed `script-src` and `style-src` that also allows `https://cdn.jsdelivr.net` (required by Swagger UI / ReDoc). All other paths use the strict policy above.

---

## Testing

### Backend (pytest)

```bash
# All tests
docker compose exec api pytest

# Single file
docker compose exec api pytest tests/unit/test_calculation.py -v

# Single test
docker compose exec api pytest tests/unit/test_calculation.py::test_mpf_floor -v

# With coverage report
docker compose exec api pytest --cov=app --cov-report=term-missing
```

Coverage target: **≥ 80%**

### Frontend (Vitest)

```bash
cd frontend
npm run test
npm run test -- --reporter=verbose src/utils/calculation.test.ts
```

Coverage target: **≥ 75%**

### E2E (Playwright)

```bash
cd e2e
npx playwright test
npx playwright test tests/upload-flow.spec.ts
```

Critical journeys covered: upload → review → results → lead capture

---

## Deployment

### Docker Compose Services

| Service | Role |
|---------|------|
| `nginx` | Reverse proxy + TLS termination + static files |
| `api` | FastAPI (Uvicorn workers) |
| `worker` | Celery worker (OCR, calculation, CRM sync, cleanup) |
| `beat` | Celery Beat (hourly file cleanup schedule) |
| `postgres` | PostgreSQL 15 |
| `redis` | Redis 7 (broker + cache + rate limit counters) |
| `smtp` | MailHog (dev) / enterprise SMTP relay (prod) |

### Scale API Workers

```bash
# Staging
docker compose up --scale api=2 -d

# Production
docker compose up --scale api=4 -d
```

### Generate a New Migration

```bash
docker compose exec api alembic revision --autogenerate -m "description"
docker compose exec api alembic upgrade head
```

### Key Rotation

```bash
# Regenerate file encryption key (invalidates all existing encrypted uploads)
python -c "from cryptography.fernet import Fernet; open('data/keys/app_secret.key','wb').write(Fernet.generate_key())"
```

---

## Contributing

1. All business logic changes must reference the corresponding BR-xxx rule in `ai_specs/Business_Rules.md`.
2. `calculation_audit` table is append-only — never issue UPDATE or DELETE.
3. All UI strings must be externalised to `src/i18n/en.json` and `src/i18n/zh-CN.json`.
4. Never store JWT in `localStorage`; access token in memory, refresh token in `httpOnly` cookie.
5. The legal disclaimer on the results page is mandatory and must not be hideable.

---

*Prepared by the Office of the CIO, Dimerco Express Group | Version 1.1 | March 2026 | Internal — Confidential*
