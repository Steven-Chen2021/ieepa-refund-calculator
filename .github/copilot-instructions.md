# Copilot Instructions — IEEPA Tariff Refund Calculator

Internal tool for Dimerco Express Group. Allows U.S. importers to upload CBP Form 7501 PDFs, get itemised tariff breakdowns (MFN / IEEPA / S301 / S232 / MPF / HMF), and receive an estimated IEEPA refund amount with a recommended pathway (PSC / PROTEST / INELIGIBLE). See `ai_specs/` for full specs.

---

## Project Structure

```
backend/          # FastAPI + Celery (Python 3.11+)
  app/
    api/v1/endpoints/   # REST API route handlers
    core/               # Config, security, dependencies
    db/                 # SQLAlchemy async engine + session
    models/             # SQLAlchemy ORM models
    schemas/            # Pydantic v2 request/response schemas
    services/           # Business logic layer
    ocr/                # OCR integration (Google Document AI + pytesseract fallback)
    tasks/              # Celery task definitions
    main.py             # FastAPI app factory
    celery_app.py       # Celery app instance
  alembic/              # DB migrations
  tests/
    unit/
    integration/
frontend/         # React 18 + TypeScript (Vite)
  src/
    components/{ui,forms,layout}/
    pages/              # Route-level components
    hooks/              # Custom React hooks
    store/              # Zustand global state
    i18n/               # en.json + zh-CN.json translation files
nginx/            # Reverse proxy config
data/             # Runtime data (uploads/, reports/, keys/) — gitignored
ai_specs/         # Authoritative specification documents
```

---

## Commands

### Backend
```bash
# Start all services
docker compose up -d

# Development (Vite dev server + hot reload API)
docker compose -f docker-compose.dev.yml up

# Run all backend tests
docker compose exec api pytest

# Run a single test file
docker compose exec api pytest tests/unit/test_calculation.py -v

# Run a single test
docker compose exec api pytest tests/unit/test_calculation.py::test_mpf_floor -v

# Apply DB migrations
docker compose exec api alembic upgrade head

# Generate a new migration
docker compose exec api alembic revision --autogenerate -m "description"
```

### Frontend
```bash
cd frontend
npm run dev          # Vite dev server (http://localhost:5173)
npm run build        # Production build
npm run test         # Vitest unit tests
npm run test -- --reporter=verbose src/utils/calculation.test.ts  # Single file
```

### E2E
```bash
cd e2e
npx playwright test
npx playwright test tests/upload-flow.spec.ts  # Single spec
```

---

## Architecture

### Request Flow (Single Entry)
1. `POST /api/v1/documents/upload` → validates MIME + magic bytes, encrypts file to `/data/uploads/`, queues Celery OCR job, returns `{ job_id }`
2. Celery worker runs OCR (Google Document AI primary; pytesseract fallback if confidence < 0.50 or API error)
3. Frontend polls `GET /api/v1/documents/{job_id}/status` until `completed` or `review_required`
4. User reviews fields on `/review`; low-confidence fields (< 0.80) shown with amber highlight; corrections saved via `PATCH /api/v1/documents/{job_id}/fields`
5. `POST /api/v1/documents/{job_id}/calculate` → queues calculation Celery job, returns `{ calculation_id }`
6. Calculation engine (Celery) applies BR-001 through BR-011, writes immutable `calculation_audit` row
7. Frontend navigates to `/results/:id` via `GET /api/v1/results/{calculation_id}`
8. PDF export: `POST /api/v1/results/{calculation_id}/export` → WeasyPrint → HMAC-signed download token (15 min TTL)
9. Lead capture: `POST /api/v1/leads` → AES-256-GCM encrypts PII → async CRM sync via Celery

### State Management (Frontend)
- **Zustand** for global UI state (upload progress, auth session)
- **TanStack Query** for all server state (API calls, OCR status polling, results caching)
- Never store JWT in `localStorage`; access token lives in memory, refresh token in `httpOnly` cookie

---

## Key Conventions

### Backend

**All business rules are non-negotiable and fully specified in `ai_specs/Business_Rules.md`** (BR-001–BR-011). Do not deviate without a formal change request.

- **Tariff rate lookups** always use `(hts_code, country_code, tariff_type, summary_date)` as the composite key against the `tariff_rates` table. The `summary_date` must be the entry summary date, not today's date.
- **IEEPA applies only to `country_of_origin = 'CN'`**; all other origins return IEEPA = $0.
- **MPF has a floor ($32.71) and cap ($634.62)**; always enforce both boundaries.
- **HMF applies only when `mode_of_transport = 'vessel'`**; air cargo returns HMF = $0.
- **`calculation_audit` is append-only** — never issue UPDATE or DELETE on this table.
- **PII fields** (`email`, `phone`, `full_name`) in the `leads` table must be encrypted with `cryptography.fernet` before writing and decrypted on read. Never store plaintext PII.
- **File uploads** are encrypted with AES-256-GCM before writing to `/data/uploads/`. The key lives at `/data/keys/app_secret.key` (chmod 600, gitignored).
- Use **SQLAlchemy 2.0 async** patterns throughout (`async with session` / `await session.execute`).
- All request/response types are **Pydantic v2** schemas in `app/schemas/`.
- Redis cache key for tariff rates: invalidate with `DEL` immediately after any admin rate update.
- Rate limiting via **slowapi**; Nginx `limit_req` provides the outer layer.

### Frontend

- **All UI strings must be externalised** to `src/i18n/en.json` and `src/i18n/zh-CN.json`. No hardcoded user-visible text.
- Use **React Hook Form + Zod** for all forms; never build uncontrolled forms.
- **Tailwind CSS only** — do not introduce other CSS frameworks or CSS-in-JS.
- **No Class Components** — function components with hooks only.
- All TypeScript files must be in **strict mode** with explicit type annotations on all components and utility functions.
- OCR field confidence < 0.80 → amber border (`border-amber-500`) + `review_required: true` indicator.
- Colour tokens: Primary `#1E40AF`, Success `#16A34A`, Warning `#D97706`, Error `#DC2626`, IEEPA highlight `#FEF3C7`.
- **Legal disclaimer on results page is mandatory and must not be hideable.**

### Auth

- JWT: Access token 15 min (`Authorization: Bearer`), Refresh token 7 days (`httpOnly` cookie).
- JWT payload shape: `{ sub: uuid, role: "user"|"admin", email, iat, exp }`.
- FastAPI dependency `get_current_user` decodes and validates the Bearer token; admin routes additionally check `role == "admin"`.
- bcrypt work factor ≥ 12 via `passlib[bcrypt]`.

### Refund Pathway Logic (BR-007)
| `days_elapsed` (today − summary_date) | pathway |
|---|---|
| ≤ 15 | `PSC` |
| 16–180 | `PROTEST` |
| > 180 | `INELIGIBLE` |

### Environment & Secrets
- Copy `backend/.env.example` → `backend/.env`; never commit `.env`.
- `data/keys/` is gitignored; back up `app_secret.key` offline.
- Generate encryption key: `python -c "from cryptography.fernet import Fernet; open('data/keys/app_secret.key','wb').write(Fernet.generate_key())"`
- GCP service account JSON mounts to `/app/secrets/` inside the container.

### Celery Task Queues
- OCR jobs, calculation jobs, CRM sync, and file cleanup are all separate Celery tasks.
- CRM sync retry: exponential backoff — 1 min → 5 min → 30 min; after 3 failures set `crm_sync_status = 'failed'` and emit an alert.
- Celery Beat runs hourly to delete `uploads/` dirs older than 24 hours.

### Database
- DB name: `ieepa_refund_db`
- Async driver: `asyncpg`
- All DDL changes go through Alembic migrations.
- Core tables: `documents`, `calculations`, `leads`, `tariff_rates`, `users`, `admin_users`, `calculation_audit`, `audit_log`.

---

## Test Coverage Targets
- Backend (pytest): ≥ 80% coverage
- Frontend (Vitest): ≥ 75% coverage
- E2E (Playwright): critical user journeys (upload → review → results → lead capture)

