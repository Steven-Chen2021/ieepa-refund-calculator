# IEEPA Refund Calculator — Service Startup Guide

> **Document Ref:** DMX-TRS-IEEPA-2026-001  
> **Project:** Dimerco IEEPA Tariff Refund Calculator  
> **Stack:** FastAPI · Celery · PostgreSQL 15 · Redis 7 · React/Vite · Docker

---

## Architecture Overview

| Service | Technology | Port |
|---|---|---|
| **api** | FastAPI + Uvicorn (--reload) | 8000 |
| **worker** | Celery Worker (OCR / Calculation) | — |
| **beat** | Celery Beat (scheduled cleanup) | — |
| **db** | PostgreSQL 15 | 5432 |
| **redis** | Redis 7 (broker + cache) | 6379 |
| **mailhog** | MailHog (local SMTP) | 1025 / 8025 |
| **frontend** | React 18 + Vite (dev server, run separately) | 5173 |

---

## Prerequisites

Ensure the following are installed before proceeding:

- **Docker Desktop** (v4.x+) with Compose V2 — https://docs.docker.com/get-docker/
- **Node.js 18+** and **npm** (for running the frontend dev server)
- **Python 3.11+** (only needed for `init_keys.py` key generation, not for running the app)
- **Git**

Verify:

```bash
docker --version          # Docker version 24+
docker compose version    # Docker Compose version v2+
node --version            # v18+
python --version          # 3.11+
```

---

## Step 1 — Clone the Repository

```bash
git clone https://github.com/Steven-Chen2021/ieepa-refund-calculator.git
cd ieepa-refund-calculator
```

---

## Step 2 — Create the Backend Environment File

Copy the example environment file and fill in the required secrets:

```bash
cp .env.example backend/.env
```

Open `backend/.env` and replace all `REPLACE_WITH_*` values:

| Variable | Description | Example |
|---|---|---|
| `SECRET_KEY` | 32-byte random hex | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `JWT_SECRET_KEY` | 64-byte random hex | `python -c "import secrets; print(secrets.token_hex(64))"` |
| `POSTGRES_PASSWORD` | PostgreSQL password | any strong password |
| `GOOGLE_DOC_AI_PROJECT_ID` | GCP project ID | optional for dev (Tesseract fallback used) |
| `GOOGLE_DOC_AI_PROCESSOR_ID` | Document AI processor ID | optional for dev |

> **Dev shortcut:** For a local development environment, the default values in `config.py` are pre-filled with safe dev defaults (e.g. `POSTGRES_PASSWORD=dev_password_only`). You may leave most fields as-is — only `SECRET_KEY` and `JWT_SECRET_KEY` must be changed.

Minimum required `backend/.env` for local dev:

```dotenv
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG
SECRET_KEY=<your-32-byte-hex>
JWT_SECRET_KEY=<your-64-byte-hex>
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=ieepa_refund_db
POSTGRES_USER=ieepa_app
POSTGRES_PASSWORD=dev_password_only
REDIS_HOST=redis
REDIS_PORT=6379
CORS_ORIGINS=http://localhost:5173
SMTP_HOST=mailhog
SMTP_PORT=1025
OCR_FALLBACK_ENABLED=true
```

---

## Step 3 — Generate the Encryption Key

The application encrypts uploaded PDF files and PII fields using a Fernet AES-256 key.  
This key **must exist** before starting the containers.

```bash
# From the project root
python init_keys.py
```

This creates `data/keys/app_secret.key`.  

> ⚠️ **Back up this file immediately.** Losing it makes all encrypted data unrecoverable.  
> The `data/keys/` directory is in `.gitignore` and will never be committed.

---

## Step 4 — (Optional) Add Google Document AI Credentials

If you have a Google Cloud service account for Document AI:

```bash
mkdir -p backend/credentials
cp /path/to/your/service-account.json backend/credentials/google_service_account.json
```

If you skip this step, the system automatically falls back to the local **Tesseract OCR** engine, which is sufficient for digital CBP Form 7501 PDFs.

---

## Step 5 — Start Backend Services with Docker Compose

```bash
docker compose up -d
```

This starts: **api**, **worker**, **beat**, **db**, **redis**, **mailhog**

Check that all services are healthy:

```bash
docker compose ps
```

Expected output:
```
NAME        STATUS          PORTS
api         Up (healthy)    0.0.0.0:8000->8000/tcp
worker      Up
beat        Up
db          Up (healthy)    0.0.0.0:5432->5432/tcp
redis       Up (healthy)    0.0.0.0:6379->6379/tcp
mailhog     Up              0.0.0.0:1025->1025/tcp, 0.0.0.0:8025->8025/tcp
```

View logs:

```bash
docker compose logs -f api       # API server
docker compose logs -f worker    # Celery worker (OCR / calculation tasks)
```

---

## Step 6 — Run Database Migrations

On first startup (or after a schema change), run Alembic migrations:

```bash
docker compose exec api alembic upgrade head
```

Verify migration ran successfully:

```bash
docker compose exec api alembic current
```

---

## Step 7 — Start the Frontend Dev Server

The frontend is **not included** in Docker Compose and must be run separately.

```bash
cd frontend
npm install         # first time only
npm run dev
```

The Vite dev server starts at **http://localhost:5173**

> The frontend proxies API calls to `http://localhost:8000` (configured in `vite.config.ts`).

---

## Step 8 — Verify the Full Stack

| Service | URL | Expected |
|---|---|---|
| Frontend | http://localhost:5173 | Upload page renders |
| API (health) | http://localhost:8000/api/v1/health | `{"status":"ok"}` |
| API (Swagger) | http://localhost:8000/docs | Interactive API docs |
| MailHog UI | http://localhost:8025 | Email inbox (for dev) |

---

## Common Commands

### Rebuild containers (after dependency changes)

```bash
# After modifying backend/requirements.txt:
docker compose up -d --build api worker beat
```

### Stop all services

```bash
docker compose down
```

### Stop and delete all data (full reset)

```bash
docker compose down -v   # removes postgres_data volume
```

### Reset the upload store (re-run migrations on clean DB)

```bash
docker compose down -v
docker compose up -d
docker compose exec api alembic upgrade head
```

### Run backend tests

```bash
docker compose exec api pytest
```

### View Celery task queue

```bash
docker compose exec worker celery -A app.celery_app inspect active
```

---

## Service Port Reference

| Service | Port | Purpose |
|---|---|---|
| Frontend (Vite) | **5173** | React dev server |
| Backend API | **8000** | FastAPI / Uvicorn |
| PostgreSQL | **5432** | Database (dev only exposed) |
| Redis | **6379** | Celery broker / cache (dev only exposed) |
| MailHog SMTP | **1025** | Dev email sending |
| MailHog Web UI | **8025** | View sent emails in browser |

---

## Environment Quick Reference

### Development (default)

```
ENVIRONMENT=development
SMTP_HOST=mailhog                  # emails captured by MailHog
OCR_FALLBACK_ENABLED=true          # uses local Tesseract, no GCP needed
ENABLE_CRM_SYNC=false              # CRM webhook disabled
DEBUG=true
```

### Staging / Production

Additional changes required:

```
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=<strong-secret>
JWT_SECRET_KEY=<strong-secret>
POSTGRES_PASSWORD=<strong-password>
REDIS_PASSWORD=<strong-password>
CORS_ORIGINS=https://ieepa.dimerco.com
SMTP_HOST=smtp.internal.dimerco.local
SMTP_PORT=587
SMTP_USE_TLS=true
ENABLE_CRM_SYNC=true
CRM_WEBHOOK_URL=<crm-endpoint>
CRM_API_KEY=<crm-key>
```

---

## Troubleshooting

### `api` container fails to start — database not ready

The `api` service has a `depends_on: db: condition: service_healthy` guard.  
If the DB takes longer than expected:

```bash
docker compose logs db             # check PostgreSQL startup logs
docker compose restart api         # retry after db is healthy
```

### `alembic upgrade head` fails — table already exists

```bash
docker compose exec api alembic stamp head   # mark as current without running
```

### Drag-and-drop does not respond

- Ensure you have **checked the privacy consent checkbox** first — the dropzone is disabled until accepted.
- If returning from a previous upload, the state should auto-reset on page load.

### OCR returns empty fields

- Confirm the PDF is a digital (not scanned) CBP Form 7501.
- Check `docker compose logs worker` for extraction errors.
- `pdfplumber` is used for digital PDFs; ensure it installed correctly via `docker compose up -d --build worker`.

### Port conflict on 5432 or 6379

Stop any local PostgreSQL or Redis instances, or change the host-side port mapping in `docker-compose.yml`:

```yaml
ports:
  - "5433:5432"   # map to 5433 on host instead
```

---

## File Structure Reference

```
ieepa-refund-calculator/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/   # FastAPI route handlers
│   │   ├── core/config.py      # All settings (pydantic-settings)
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── ocr/tesseract.py    # pdfplumber + Tesseract OCR engine
│   │   └── engine/calculator.py# Tariff calculation logic
│   ├── alembic/                # Database migration scripts
│   ├── requirements.txt        # Python dependencies
│   └── .env                    # ← create from .env.example (never commit)
├── frontend/
│   ├── src/pages/              # React pages (Home, Calculate, Review, Results)
│   ├── src/components/         # Shared UI components
│   └── tailwind.config.js      # Dimerco brand design tokens
├── data/
│   ├── keys/app_secret.key     # ← Fernet encryption key (never commit)
│   ├── uploads/                # Uploaded PDFs (auto-cleaned after 24h)
│   └── reports/                # Generated reports (auto-cleaned after 90 days)
├── docker-compose.yml          # All backend services
├── init_keys.py                # Key generation utility
└── .env.example                # Environment variable template
```
