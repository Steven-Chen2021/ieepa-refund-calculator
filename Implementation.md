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

## OCR Pipeline — HTS Rate Matching

### Problem

CBP Form 7501 Box 33 **omits 0% duty rates entirely**. A line group may contain
5 HTS codes but only 3 printed rates. Positional (order-based) matching of rates
to codes is therefore unreliable and produces wrong assignments.

Example — Line 001 of sample `2810306.pdf`:

| HTS Code | Type | Rate | PDF Printed? |
|---|---|---|---|
| `9903.88.03` | S301 | 25% | ✅ |
| `9903.01.24` | IEEPA | 10% | ✅ |
| `9903.01.33` | IEEPA | **0%** | ❌ omitted |
| `9903.85.08` | S232 | 50% | ✅ |
| `8508.70.0000` | MFN | **0%** | ❌ omitted |

### Solution — Three-Layer Fix

**Layer 1 — Tesseract parser (`app/ocr/tesseract.py`)**

`_extract_line_items` uses a two-phase approach:

- **Phase 1 (parse):** Accumulates each line group into a `_GroupData` structure
  storing supplemental HTS rows, the main HTS row, and all PDF-printed
  rate/duty pairs (`pdf_rate_duty_pairs`) for cross-validation only.
- **Phase 2 (assemble):** Propagates `entered_value` from the main HTS row to
  every supplemental row in the group. Sets `duty_rate` and `duty_amount` to
  `_missing_field()` (value=None) — rates are filled by Layer 3.

**Layer 2 — Google Document AI parser (`app/ocr/google_docai.py`)**

`_post_process_table_items` runs after raw table extraction:

- Inherits blank `line_number` cells from the previous non-blank row
  (DocAI continuation rows often have no line_number cell).
- Propagates `entered_value` from the main HTS row to supplemental rows.
- Collects `pdf_rate_duty_pairs` from rate/duty cells per group.
- Clears `duty_rate` / `duty_amount` on all rows — filled by Layer 3.

**Layer 3 — Tariff enrichment service (`app/services/tariff_enrichment.py`)**

Called from `app/tasks/ocr.py` after OCR extraction, before persisting to DB.

- `infer_tariff_type(hts_code)` maps HTS prefix to `TariffType`:
  - `9903.01.xx` → IEEPA
  - `9903.88.xx` → S301
  - `9903.80–82.xx` → S232 (steel)
  - `9903.85–86.xx` → S232 (aluminium)
  - Other `9903.xx.xx` → tries S232 then S301 in order
  - All other codes → MFN
- `enrich_extracted_fields(extracted_dict, country, summary_date, session)`
  queries the `tariff_rates` DB table (no Redis — OCR Celery task context)
  for each HTS code using the same composite-key logic as the calculator:
  `(hts_code, country_code IN [cc, '*'], tariff_type, effective_from ≤ date ≤ effective_to)`.
  Sets `duty_rate` (e.g. `"25%"`) and `duty_amount` as `OcrField` objects
  with `confidence=0.95`. Sets `rate_source="db"` on success, `"not_found"` on miss.
- BR-001 enforced: IEEPA returns $0 immediately for non-CN goods.
- Cross-validates: sum of DB-computed duties vs `pdf_rate_duty_pairs` —
  warns (non-fatal) if difference exceeds 5%.

### Enrichment is Non-Fatal

If enrichment fails for any reason (DB unavailable, missing date/country), the
OCR pipeline logs a warning and continues with `duty_rate=None` fields. The
calculator performs its own authoritative DB lookup at calculation time regardless.

### Data Flow

```
PDF upload
   │
   ▼
[OCR: DocAI or Tesseract]
   │  → extracts HTS codes with entered_value propagated to all rows
   │  → stores pdf_rate_duty_pairs (for cross-validation only)
   │  → duty_rate = None (pending DB enrichment)
   │
   ▼
[tariff_enrichment.enrich_extracted_fields()]
   │  → infer_tariff_type(hts_code)  — prefix-based TariffType hint
   │  → DB query: tariff_rates (composite key, no Redis)
   │  → duty_rate = "25%"  (OcrField, confidence=0.95)
   │  → duty_amount = "35.25"  (Decimal, ROUND_HALF_UP)
   │  → cross-validate vs pdf_rate_duty_pairs (warn-only)
   │
   ▼
[extracted_fields saved to documents table]
   │
   ▼
[calculator.calculate_entry()]
   → entered_value × DB rate (Redis-cached) → final duty amounts
```

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

### Duty rates show as `null` after OCR

The post-OCR tariff enrichment step queries the `tariff_rates` table to assign
authoritative rates to each HTS code. If rates are missing:

1. Confirm `tariff_rates` table is populated — run:
   ```bash
   docker compose exec api alembic upgrade head
   docker compose exec db psql -U ieepa_app -d ieepa_refund_db -c "SELECT COUNT(*) FROM tariff_rates;"
   ```
2. Check worker logs for `tariff enrichment failed` or `No DB rate found` warnings:
   ```bash
   docker compose logs worker | grep enrichment
   ```
3. Enrichment failure is **non-fatal** — the calculator will still perform its own
   DB lookup at calculation time. `duty_rate=null` in `extracted_fields` is acceptable.

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
│   │   ├── api/v1/endpoints/   # FastAPI route handlers (auth, documents, results)
│   │   ├── core/config.py      # All settings (pydantic-settings)
│   │   ├── engine/calculator.py# BR-001–BR-011 tariff calculation logic
│   │   ├── middleware/         # Security headers middleware
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── ocr/                # Google Document AI + Tesseract fallback + Fernet crypto
│   │   │   ├── google_docai.py # DocAI parser + _post_process_table_items (HTS rate fix)
│   │   │   └── tesseract.py    # pdfplumber/Tesseract parser + two-phase _extract_line_items
│   │   ├── schemas/            # Pydantic v2 request/response schemas
│   │   ├── services/
│   │   │   └── tariff_enrichment.py  # Post-OCR DB rate lookup per HTS code
│   │   └── tasks/ocr.py        # Celery OCR task (calls tariff_enrichment after OCR)
│   ├── alembic/                # Database migration scripts
│   ├── scripts/                # Developer utility scripts (e.g. test_ocr_extraction.py)
│   ├── tests/
│   │   ├── unit/               # pytest unit tests (calculation, OCR confidence, classification)
│   │   └── integration/        # pytest integration tests
│   ├── requirements.txt        # Python dependencies
│   └── .env                    # ← create from .env.example (never commit)
├── frontend/
│   ├── icon/                   # Static image assets
│   │   ├── DimercoLogo.svg     # Dimerco brand logo (vector)
│   │   ├── check.png           # Checkmark icon
│   │   ├── uploadCloud.png     # Cloud upload icon
│   │   └── wallet.png          # Wallet icon
│   ├── src/
│   │   ├── api/                # Axios API client (client.ts, documents.ts, results.ts)
│   │   ├── components/ui/      # Shared UI components (Navbar, PathwayBadge, StepIndicator, …)
│   │   ├── i18n/               # en.json + zh-CN.json translation files
│   │   ├── pages/              # Route-level components (Home, Calculate, Review, Results)
│   │   ├── store/              # Zustand global state (uploadStore)
│   │   └── hooks/              # Custom React hooks
│   └── tailwind.config.js      # Dimerco brand design tokens
├── data/
│   ├── keys/app_secret.key     # ← Fernet encryption key (never commit)
│   ├── uploads/                # Uploaded PDFs (auto-cleaned after 24h)
│   └── reports/                # Generated reports (auto-cleaned after 90 days)
├── 7501Samples/                # Sample CBP Form 7501 PDFs for development/testing
├── docker-compose.yml          # All backend services
├── init_keys.py                # Key generation utility
└── .env.example                # Environment variable template
```
