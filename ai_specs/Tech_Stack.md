# Tech Stack
**Document Reference:** DMX-TRS-IEEPA-2026-001 (Current Repository Implementation)
**Based On BRS:** DMX-BRS-IEEPA-2026-001 v1.0
**Owner:** Office of the CIO, Dimerco Express Group
**Version:** 1.1 | March 2026 | Internal - Confidential

This revision reflects the code currently present in the repository. It documents implemented architecture first and explicitly calls out scaffolded or not-yet-wired areas where relevant.

---

## Section 3.1 - Technology Stack

### 3.1.1 Current three-tier architecture

```
┌─────────────────────────────────────────────────────────┐
│              Tier 1: Presentation                       │
│   React 18 SPA served by Vite in development           │
│   (Nginx folder exists, but is not wired in dev flow)  │
└─────────────────────────────┬───────────────────────────┘
                              │ HTTP in development
┌─────────────────────────────▼───────────────────────────┐
│              Tier 2: Application                        │
│   FastAPI API + in-process calculation engine           │
│   Celery worker/beat currently used for OCR pipeline    │
└──────┬──────────────────────────────────┬───────────────┘
       │ SQLAlchemy async                 │ Redis
┌──────▼──────────────────────────────────▼───────────────┐
│              Tier 3: Data                               │
│   PostgreSQL 15 | Redis 7 | Local encrypted files       │
└─────────────────────────────────────────────────────────┘
```

### 3.1.2 Frontend stack

| Category | Package / Tool | Version | Current use |
|----------|----------------|---------|-------------|
| Framework | React | 18.3.1 | SPA built with function components and hooks |
| Language | TypeScript | 5.4.5 | Strict mode enabled in `tsconfig.json` |
| Routing | React Router DOM | 6.23.1 | Client-side routing |
| Server state | TanStack Query | 5.37.1 | Query client configured in `src/main.tsx` |
| Global state | Zustand | 4.5.2 | Upload state in `src/store/uploadStore.ts` |
| Forms | React Hook Form + Zod | 7.51.3 + 3.23.8 | Form validation and typed form state |
| Upload UI | react-dropzone | 14.2.3 | Drag-and-drop upload flow |
| HTTP client | Axios | 1.6.8 | API client layer under `src/api/` |
| i18n | i18next + react-i18next | 23.11.3 + 14.1.1 | `en` and `zh-CN` translations in `src/i18n/` |
| Styling | Tailwind CSS | 3.4.3 | Utility-first styling with custom brand tokens |
| Build tool | Vite | 5.2.11 | Local dev server and production build |
| React plugin | `@vitejs/plugin-react` | 4.3.0 | Vite React integration |
| CSS tooling | PostCSS + Autoprefixer | 8.4.38 + 10.4.19 | Tailwind processing |
| Unit tests | Vitest | 1.6.0 | Frontend test runner configured in `package.json` |

**Current frontend routes**

| Route | Status | Notes |
|-------|--------|-------|
| `/` | Implemented | Home page |
| `/calculate` | Implemented | Upload flow |
| `/review` | Implemented | OCR review flow |
| `/results/:id` | Implemented | Results page |
| `/register` | Placeholder | Renders "Registration coming soon." |

**Not currently implemented in the frontend**

- No `/bulk` routes are defined in `src/App.tsx`
- No `/admin/*` routes are defined in `src/App.tsx`
- No Playwright dependency or configuration is committed today

### 3.1.3 Backend stack

| Category | Package / Tool | Version | Current use |
|----------|----------------|---------|-------------|
| Language | Python | 3.11 | Backend runtime from `python:3.11-slim` |
| Web framework | FastAPI | 0.110.3 | REST API with OpenAPI docs |
| ASGI server | Uvicorn | 0.29.0 | Development server command in compose |
| Process manager | Gunicorn | 22.0.0 | Installed for production-style serving |
| Task queue | Celery | 5.4.0 | Worker and beat services are defined |
| Redis client | redis-py | 5.0.6 | Async Redis usage plus Celery transport |
| ORM | SQLAlchemy | 2.0.30 | Async ORM and query layer |
| DB driver | asyncpg | 0.29.0 | PostgreSQL async driver |
| Migrations | Alembic | 1.13.2 | Initial schema migration committed |
| Validation | Pydantic | 2.7.4 | Request and response models |
| Settings | pydantic-settings | 2.3.4 | `.env`-backed settings object |
| JWT | PyJWT | 2.8.0 | Access and refresh token handling |
| Password hashing | passlib[bcrypt] | 1.7.4 | bcrypt hashing with 12 rounds |
| Encryption | cryptography | 42.0.8 | Fernet-based file and PII encryption |
| Upload parsing | python-multipart | 0.0.9 | Multipart form uploads |
| MIME detection | python-magic | 0.4.27 | Magic-bytes file validation |
| OCR primary | Google Document AI | 2.29.0 | Primary OCR provider |
| OCR fallback | pytesseract + pdf2image | 0.3.10 + 1.17.0 | Local OCR fallback path |
| PDF/image helpers | Pillow + pdfplumber + pdfminer.six | 10.4.0 + 0.11.4 + 20231228 | OCR preprocessing/parsing support |
| PDF generation | WeasyPrint | 62.3 | Installed, but export endpoint is not currently mounted |
| Email | aiosmtplib | 3.0.1 | SMTP integration support |
| Rate limiting | slowapi | 0.1.9 | App-level request throttling |
| HTTP client | httpx | 0.27.0 | Utility and test HTTP client |
| Env loading | python-dotenv | 1.0.1 | `.env` support |

**Current API surface**

| Router | Endpoints implemented today |
|--------|-----------------------------|
| `auth` | `POST /api/v1/auth/token`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout` |
| `documents` | `POST /api/v1/documents/upload`, `GET /api/v1/documents/{job_id}/status`, `PATCH /api/v1/documents/{job_id}/fields`, `POST /api/v1/documents/{job_id}/calculate` |
| `results` | `GET /api/v1/results/{calculation_id}` |

**Current backend behavior notes**

- The calculation step currently runs **synchronously in the API process** inside `POST /documents/{job_id}/calculate`
- Celery currently registers only `app.tasks.ocr`
- The repository includes models and settings for CRM sync, reporting, and admin concerns, but those flows are not all exposed as mounted API endpoints yet

### 3.1.4 Data tier

#### PostgreSQL 15

| Setting | Value |
|---------|-------|
| Version | PostgreSQL 15 |
| Container image | `postgres:15-alpine` |
| Database name | `ieepa_refund_db` |
| Access pattern | SQLAlchemy async engine with `asyncpg` |
| Migration state | One initial Alembic migration is committed |

**Core tables currently created by migration**

| Table | Purpose |
|-------|---------|
| `users` | Registered users and admins via `role` enum |
| `documents` | Upload metadata, OCR status, extracted fields, corrections |
| `calculations` | Tariff calculation results |
| `calculation_audit` | Append-only calculation snapshots protected by trigger |
| `leads` | Lead/contact records with encrypted PII columns |
| `tariff_rates` | Tariff rate lookup data |
| `audit_log` | Administrative audit trail |

**Important schema alignment notes**

- There is **no separate `admin_users` table** in the current schema; admin access is represented by `users.role = 'admin'`
- Lead and CRM-related schema is present even though the lead submission API flow is not currently mounted

#### Redis 7

| Use | Current role |
|-----|--------------|
| Celery broker | Used by worker/beat services |
| Celery result backend | Configured via the same Redis instance |
| Rate limiting counters | Used by slowapi |
| Refresh-token revocation | Used by auth token blacklist logic |
| Cache | Available for tariff-rate caching via app logic |

**Current note:** guest upload ownership is tracked through a `session_id` cookie stored on the `documents` row, not through a Redis-backed session store.

#### Local file system

| Path | Current role |
|------|--------------|
| `/data/uploads` | Encrypted uploaded source files |
| `/data/reports` | Report output directory configured in settings |
| `/data/keys` | Fernet key storage |

**Encryption details**

- Uploaded files are encrypted with `cryptography.fernet`
- The implementation uses Fernet authenticated encryption (`AES-128-CBC + HMAC-SHA256`), not AES-GCM
- PII model fields use a SQLAlchemy `EncryptedString` type backed by Fernet

### 3.1.5 Runtime and infrastructure

#### Docker Compose services currently defined

| Service | Status | Purpose |
|---------|--------|---------|
| `api` | Implemented | FastAPI app via Uvicorn with `--reload` |
| `worker` | Implemented | Celery worker |
| `beat` | Implemented | Celery Beat scheduler |
| `db` | Implemented | PostgreSQL 15 |
| `redis` | Implemented | Redis 7 |
| `mailhog` | Implemented | Local SMTP capture in development |

**Current development flow**

- `docker compose up -d` starts backend-side services
- The frontend runs separately with `cd frontend && npm run dev`
- `vite.config.ts` proxies `/api` to `http://localhost:8000`

**Repository state notes**

- `nginx/` exists, but `nginx/nginx.conf` is currently empty
- `frontend/Dockerfile` exists, but is currently empty
- The repository is presently documented and wired primarily for local development

### 3.1.6 OCR and calculation architecture

#### OCR pipeline

1. `POST /api/v1/documents/upload`
2. Validate `Content-Type`, magic bytes, file size, privacy acceptance, and idempotency header
3. Encrypt the upload to `/data/uploads/...`
4. Queue Celery OCR task `app.tasks.ocr.process_ocr_job`
5. OCR task uses Google Document AI first, then falls back to pytesseract when needed
6. Results are stored in `documents.extracted_fields`
7. Low-confidence fields are marked for review

#### Calculation pipeline

1. `POST /api/v1/documents/{job_id}/calculate`
2. Parse merged OCR fields plus user corrections
3. Create `calculations` row with `calculating` status
4. Execute `calculate_entry(...)` in-process
5. Persist duty components and final result
6. Read result through `GET /api/v1/results/{calculation_id}`

**Important alignment note:** the current repository does **not** dispatch calculation to Celery even though broader product docs may describe async calculation workers.

### 3.1.7 Auth and security stack

| Area | Implementation |
|------|----------------|
| Access auth | Bearer JWT via FastAPI dependency |
| Access token TTL | 15 minutes |
| Refresh auth | `httpOnly`, `secure`, `SameSite=Strict` cookie |
| Refresh revocation | Redis-backed blacklist |
| Password hashing | bcrypt via Passlib |
| Security headers | Custom Starlette middleware |
| CORS | FastAPI `CORSMiddleware` |
| Upload validation | `python-magic` plus size and MIME checks |
| Guest ownership | `session_id` cookie for unauthenticated uploads |

### 3.1.8 Testing and developer tooling

#### Backend

| Tool | Version | Purpose |
|------|---------|---------|
| pytest | 8.2.2 | Test runner |
| pytest-asyncio | 0.23.7 | Async test support |
| pytest-cov | 5.0.0 | Coverage reporting |
| httpx | 0.27.0 | Async API test client |
| black | 24.4.2 | Formatting |
| ruff | 0.5.1 | Linting |
| mypy | 1.10.0 | Static typing checks |

#### Frontend

| Tool | Version | Purpose |
|------|---------|---------|
| Vitest | 1.6.0 | Unit tests |
| TypeScript compiler | 5.4.5 | Type checking in build script |

**Current note:** the `e2e/` directory exists, but no Playwright dependency or config file is committed in the current repository snapshot.

### 3.1.9 Implemented vs scaffolded/planned areas

The repository already contains code or configuration hooks for several broader product capabilities, but they are not all fully wired into the current running architecture:

- Lead and CRM sync data structures exist, but no mounted lead submission endpoint is currently present in `api/v1/router.py`
- WeasyPrint is installed and `REPORTS_DIR` is configured, but no results export endpoint is currently mounted
- Admin authorization support exists in dependencies and schema, but no admin API router is mounted today
- Bulk upload is referenced in settings and higher-level docs, but no bulk frontend route or backend endpoint is currently implemented
- Nginx and frontend container placeholders exist in the repository, but the active local development flow does not use them yet

---

*Prepared by the Office of the CIO, Dimerco Express Group | Version 1.1 | March 2026 | Confidential*
