# 🚀 Production Deployment Guide
### IEEPA Tariff Refund Calculator — Dimerco Express Group

> **Who is this for?** Junior IT engineers deploying this system for the first time.  
> **Read every step carefully. Do not skip sections.**  
> If anything is unclear, stop and ask your team lead before continuing.

---

## 📋 Table of Contents

1. [What You Are Deploying](#1-what-you-are-deploying)
2. [Server Requirements](#2-server-requirements)
3. [Software Prerequisites](#3-software-prerequisites)
4. [Get the Source Code](#4-get-the-source-code)
5. [Create the Data Directories](#5-create-the-data-directories)
6. [Generate the Encryption Key](#6-generate-the-encryption-key)
7. [Set Up Google Cloud Credentials](#7-set-up-google-cloud-credentials)
8. [Configure Environment Variables](#8-configure-environment-variables)
9. [Configure Nginx (Reverse Proxy)](#9-configure-nginx-reverse-proxy)
10. [Create the Production Docker Compose File](#10-create-the-production-docker-compose-file)
11. [Build the Docker Images](#11-build-the-docker-images)
12. [Start All Services](#12-start-all-services)
13. [Run Database Migrations](#13-run-database-migrations)
14. [Verify Everything Is Working](#14-verify-everything-is-working)
15. [SSL / HTTPS Setup](#15-ssl--https-setup)
16. [Ongoing Maintenance](#16-ongoing-maintenance)
17. [Troubleshooting Common Issues](#17-troubleshooting-common-issues)

---

## 1. What You Are Deploying

This system has **6 components** that all run together via Docker:

| Component | What it does |
|-----------|-------------|
| **api** | The FastAPI backend — handles all HTTP requests |
| **worker** | Celery worker — processes document extraction and calculations in the background |
| **beat** | Celery Beat — runs scheduled tasks (e.g., deletes old uploaded files every hour) |
| **db** | PostgreSQL 15 database — stores all application data |
| **redis** | Redis 7 — message queue between the API and workers |
| **nginx** | Reverse proxy — serves the frontend and routes API traffic |

**How they connect:**

```
User's Browser
      │
      ▼
   [ Nginx :443 ]  ◄─── SSL termination, serves React frontend
      │
      ├──── /api/*  ──────► [ FastAPI :8000 ]
      │                            │
      │                     [ Redis :6379 ] ◄──► [ Celery Worker ]
      │                            │                     │
      │                     [ PostgreSQL :5432 ] ◄───────┘
      │
      └──── /*  ──────────► [ React Static Files ]
```

---

## 2. Server Requirements

Your production server must meet these minimum specifications:

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Disk | 40 GB SSD | 100 GB SSD |
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |
| Network | Public IP with port 80 and 443 open | Static IP |

> ⚠️ **Firewall rules required:** Open ports **80** (HTTP) and **443** (HTTPS) to the public internet.  
> Ports 5432 (PostgreSQL), 6379 (Redis), and 8000 (API) must **NOT** be publicly accessible.

---

## 3. Software Prerequisites

Log in to your server and install the following. Run each command one at a time.

### 3.1 Update the system

```bash
sudo apt-get update && sudo apt-get upgrade -y
```

### 3.2 Install Docker

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Allow your user to run Docker without sudo
sudo usermod -aG docker $USER

# Log out and back in, then verify Docker is working
docker --version
# Expected output: Docker version 24.x.x or higher
```

### 3.3 Install Docker Compose

```bash
sudo apt-get install -y docker-compose-plugin

# Verify
docker compose version
# Expected output: Docker Compose version v2.x.x or higher
```

### 3.4 Install Git

```bash
sudo apt-get install -y git

# Verify
git --version
```

---

## 4. Get the Source Code

```bash
# Go to the directory where you want to install the app
cd /opt

# Clone the repository (replace with your actual repo URL)
sudo git clone https://github.com/Steven-Chen2021/ieepa-refund-calculator.git

# Rename the folder for convenience
sudo mv ieepa-refund-calculator refundcal

# Give your user ownership of the folder
sudo chown -R $USER:$USER /opt/refundcal

# Enter the project directory
cd /opt/refundcal
```

> 📌 From this point on, **all commands assume you are inside `/opt/refundcal`** unless stated otherwise.

---

## 5. Create the Data Directories

The application stores uploaded files, generated reports, and encryption keys in a `/data` folder.  
These folders must exist **before** starting Docker.

```bash
# Create all required directories
mkdir -p data/uploads
mkdir -p data/reports
mkdir -p data/keys
mkdir -p backend/credentials

# Restrict permissions on the keys folder — only the current user can read it
chmod 700 data/keys
```

Verify the structure looks like this:

```
data/
├── keys/        ← encryption key will go here (Step 6)
├── reports/     ← generated PDF reports stored here
└── uploads/     ← user-uploaded Form 7501 files stored here

backend/
└── credentials/ ← Google Cloud JSON key file goes here (Step 7)
```

---

## 6. Generate the Encryption Key

The application encrypts all uploaded files and sensitive database fields (PII) using a secret key.  
You must generate this key **once** and keep it safe.

```bash
# Generate the encryption key
python3 -c "
from cryptography.fernet import Fernet
key = Fernet.generate_key()
open('data/keys/app_secret.key', 'wb').write(key)
print('✅ Encryption key generated successfully')
"

# Restrict access — only root/app user should read this file
chmod 600 data/keys/app_secret.key

# Verify the file was created
ls -la data/keys/
# Expected: -rw------- 1 youruser youruser 44 ... app_secret.key
```

> 🔴 **CRITICAL — Back up this key immediately!**  
> - Copy `data/keys/app_secret.key` to a secure offline location (e.g., an encrypted USB drive or your company's password manager).  
> - **If this key is lost, all encrypted data in the database becomes permanently unreadable.**  
> - This key must NEVER be committed to Git.

---

## 7. Set Up Google Cloud Credentials

The application uses Google Document AI to extract data from uploaded PDF files.

### 7.1 Get the service account JSON file

Ask your team lead or GCP administrator for the Google Cloud service account JSON key file.  
It will be named something like `dimerco-ieepa-sa-key.json`.

### 7.2 Place it in the project

```bash
# Copy the file into the credentials folder
cp /path/to/dimerco-ieepa-sa-key.json backend/credentials/google_service_account.json

# Restrict permissions
chmod 600 backend/credentials/google_service_account.json
```

### 7.3 Verify the file is valid JSON

```bash
python3 -c "import json; json.load(open('backend/credentials/google_service_account.json')); print('✅ Valid JSON')"
```

> If you see `✅ Valid JSON`, you are good. If you see an error, the file is corrupted — ask for the key again.

---

## 8. Configure Environment Variables

The application reads its configuration from a file called `.env` inside the `backend/` folder.

### 8.1 Create the .env file from the template

```bash
cp backend/.env.example backend/.env
```

### 8.2 Edit the .env file

```bash
nano backend/.env
```

You need to fill in every value that says `REPLACE_WITH_...`. Here is a guide for each one:

---

#### 🔧 Basic Settings

```env
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
APP_HOST=0.0.0.0
APP_PORT=8000
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
```

> Replace `yourdomain.com` with your actual domain name (e.g., `ieepa.dimerco.com`).

---

#### 🔑 Secret Keys

These are random strings used to sign JWT tokens and encrypt session data.  
Generate them with the commands below:

```bash
# Generate SECRET_KEY (run this in your terminal, copy the output)
python3 -c "import secrets; print(secrets.token_hex(32))"

# Generate JWT_SECRET_KEY (run this separately, copy the output)
python3 -c "import secrets; print(secrets.token_hex(64))"
```

Then paste the generated values into your `.env`:

```env
SECRET_KEY=<paste the 64-character output from the first command>
JWT_SECRET_KEY=<paste the 128-character output from the second command>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
```

---

#### 🗄️ Database

```env
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=ieepa_refund_db
POSTGRES_USER=ieepa_app
POSTGRES_PASSWORD=<create a strong password, e.g., use: python3 -c "import secrets; print(secrets.token_urlsafe(32))">
DATABASE_URL=postgresql+asyncpg://ieepa_app:<your_password>@db:5432/ieepa_refund_db
```

> ⚠️ Use the same password in both `POSTGRES_PASSWORD` and inside `DATABASE_URL`.

---

#### 📦 Redis

```env
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=<create another strong password>
REDIS_URL=redis://:<your_redis_password>@redis:6379/0
CELERY_BROKER_URL=redis://:<your_redis_password>@redis:6379/0
CELERY_RESULT_BACKEND=redis://:<your_redis_password>@redis:6379/0
CACHE_TTL_SECONDS=3600
```

---

#### 📁 File Storage

```env
DATA_ROOT=/data
UPLOAD_DIR=/data/uploads
REPORTS_DIR=/data/reports
KEYS_DIR=/data/keys
FERNET_KEY_PATH=/data/keys/app_secret.key
MAX_UPLOAD_SIZE_MB=20
ALLOWED_EXTENSIONS=pdf,jpg,jpeg,png
DOWNLOAD_TOKEN_EXPIRE_MINUTES=15
```

> These paths refer to the paths **inside the Docker container**. Leave them as-is.

---

#### 🌐 CORS (Cross-Origin)

```env
CORS_ORIGINS=https://yourdomain.com
CORS_ALLOW_CREDENTIALS=true
```

> Replace `yourdomain.com` with your actual domain. This must match exactly what users type in their browser.

---

#### 🤖 Google Document AI

```env
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/google_service_account.json
GOOGLE_DOC_AI_PROJECT_ID=<your GCP project ID, e.g.: dimerco-ieepa-prod>
GOOGLE_DOC_AI_LOCATION=us
GOOGLE_DOC_AI_PROCESSOR_ID=<your processor ID from the GCP Console>
TESSERACT_CMD=/usr/bin/tesseract
OCR_FALLBACK_ENABLED=true
OCR_CONFIDENCE_THRESHOLD=0.80
```

> Ask your GCP administrator for the Project ID and Processor ID.

---

#### 📧 Email (SMTP)

```env
SMTP_HOST=smtp.internal.dimerco.local
SMTP_PORT=587
SMTP_USERNAME=<your SMTP username>
SMTP_PASSWORD=<your SMTP password>
SMTP_USE_TLS=true
SMTP_FROM_ADDRESS=noreply@ieepa.dimerco.com
SMTP_FROM_NAME=Dimerco IEEPA Portal
```

---

#### 🔗 CRM Integration

```env
ENABLE_CRM_SYNC=true
CRM_WEBHOOK_URL=<CRM API endpoint URL>
CRM_API_KEY=<CRM API key>
```

---

#### ⏱️ Scheduled Cleanup

```env
FILE_CLEANUP_TTL_HOURS=24
REPORT_CLEANUP_TTL_DAYS=90
CLEANUP_SCHEDULE_CRON=0 * * * *
```

---

#### 🔒 Rate Limiting

```env
RATE_LIMIT_UPLOAD=10/hour
RATE_LIMIT_CALCULATE=10/minute
RATE_LIMIT_LOGIN=5/minute
RATE_LIMIT_GET=60/minute
```

---

### 8.3 Save and protect the .env file

Press `Ctrl+X`, then `Y`, then `Enter` to save in nano.

```bash
# Restrict the .env file so only your user can read it
chmod 600 backend/.env

# Verify no placeholder values remain
grep "REPLACE_WITH" backend/.env
# This command should return NO output. If it shows any lines, go back and fill them in.
```

---

## 9. Configure Nginx (Reverse Proxy)

Nginx acts as the front door — it serves the React frontend and forwards API requests to FastAPI.

```bash
# Open the nginx config file
nano nginx/nginx.conf
```

Paste the following content (replace `yourdomain.com` with your actual domain):

```nginx
# nginx/nginx.conf — Production

# Redirect all HTTP traffic to HTTPS
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# Main HTTPS server
server {
    listen 443 ssl;
    server_name yourdomain.com www.yourdomain.com;

    # SSL certificates (generated in Step 15)
    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # File upload size limit (must match MAX_UPLOAD_SIZE_MB in .env)
    client_max_body_size 21M;

    # ── API requests → FastAPI backend ──
    location /api/ {
        proxy_pass         http://api:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    # ── Everything else → React frontend ──
    location / {
        root  /usr/share/nginx/html;
        index index.html;
        # Required for React Router (single-page app)
        try_files $uri $uri/ /index.html;
    }
}
```

Save the file (`Ctrl+X`, `Y`, `Enter`).

---

## 10. Create the Production Docker Compose File

The existing `docker-compose.yml` is for development only. Create a separate production one:

```bash
nano docker-compose.prod.yml
```

Paste the following:

```yaml
# docker-compose.prod.yml — Production
# Usage: docker compose -f docker-compose.prod.yml up -d

services:

  # ── FastAPI Backend ──────────────────────────────────────
  api:
    build:
      context: ./backend
      target: production          # uses the hardened production stage
    restart: always
    volumes:
      - ./data:/data
      - ./backend/credentials:/app/credentials:ro
    env_file:
      - ./backend/.env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    # No ports exposed — nginx proxies to this container internally

  # ── Celery Worker ────────────────────────────────────────
  worker:
    build:
      context: ./backend
      target: production
    restart: always
    command: celery -A app.celery_app worker --loglevel=info --concurrency=4
    volumes:
      - ./data:/data
      - ./backend/credentials:/app/credentials:ro
    env_file:
      - ./backend/.env
    depends_on:
      - redis
      - db

  # ── Celery Beat (Scheduler) ──────────────────────────────
  beat:
    build:
      context: ./backend
      target: production
    restart: always
    command: celery -A app.celery_app beat --loglevel=info
    volumes:
      - ./data:/data
    env_file:
      - ./backend/.env
    depends_on:
      - redis

  # ── PostgreSQL 15 ────────────────────────────────────────
  db:
    image: postgres:15-alpine
    restart: always
    environment:
      POSTGRES_DB: ieepa_refund_db
      POSTGRES_USER: ieepa_app
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    # No ports exposed to host — only accessible internally
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ieepa_app -d ieepa_refund_db"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ── Redis 7 ──────────────────────────────────────────────
  redis:
    image: redis:7-alpine
    restart: always
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    # No ports exposed to host
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ── Nginx + React Frontend ───────────────────────────────
  nginx:
    image: nginx:1.25-alpine
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./nginx/certs:/etc/nginx/certs:ro
      - frontend_build:/usr/share/nginx/html:ro
    depends_on:
      - api

  # ── Frontend Build (runs once, then exits) ───────────────
  frontend-builder:
    build:
      context: ./frontend
    volumes:
      - frontend_build:/app/dist
    profiles:
      - build    # only runs when explicitly called

volumes:
  postgres_data:
  redis_data:
  frontend_build:
```

Save the file (`Ctrl+X`, `Y`, `Enter`).

---

## 11. Build the Docker Images

### 11.1 Build the React frontend

The frontend must be compiled into static files first:

```bash
# Build the frontend (this may take 2–5 minutes)
cd frontend
npm install
npm run build

# The output is in frontend/dist/
ls dist/
# You should see: index.html, assets/

cd ..
```

Copy the build output to where nginx can find it:

```bash
# Create a named Docker volume for the frontend files
docker volume create refundcal_frontend_build

# Use a temporary container to copy the built files into the volume
docker run --rm \
  -v $(pwd)/frontend/dist:/source:ro \
  -v refundcal_frontend_build:/dest \
  alpine sh -c "cp -r /source/. /dest/"

echo "✅ Frontend files copied to Docker volume"
```

### 11.2 Build the backend Docker images

```bash
# Build all backend images (this may take 5–10 minutes on first run)
docker compose -f docker-compose.prod.yml build

# You should see output ending with:
# ✅ Successfully built ...
# ✅ Successfully tagged ...
```

> ☕ This step downloads base images and installs all Python dependencies. It takes a while the first time. Subsequent builds are much faster.

---

## 12. Start All Services

```bash
# Start all services in the background
docker compose -f docker-compose.prod.yml up -d

# Watch the startup logs (press Ctrl+C to stop watching — services keep running)
docker compose -f docker-compose.prod.yml logs -f
```

Wait about 30 seconds, then check that all containers are running:

```bash
docker compose -f docker-compose.prod.yml ps
```

Expected output — every service should show `running` or `healthy`:

```
NAME                    STATUS          PORTS
refundcal-api-1         running (healthy)
refundcal-worker-1      running
refundcal-beat-1        running
refundcal-db-1          running (healthy)
refundcal-redis-1       running (healthy)
refundcal-nginx-1       running          0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
```

> 🔴 If any container shows `Exit` or `restarting`, jump to [Section 17 — Troubleshooting](#17-troubleshooting-common-issues).

---

## 13. Run Database Migrations

The database tables need to be created before the app can work. This is called "running migrations".

```bash
# Apply all database migrations
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

Expected output:

```
INFO  [alembic.runtime.migration] Context impl PostgreSQLImpl.
INFO  [alembic.runtime.migration] Will assume non-transactive DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial_schema, initial schema
INFO  [alembic.runtime.migration] Running upgrade  -> 0002_add_document_error_code
INFO  [alembic.runtime.migration] Running upgrade  -> 0003_add_document_extraction_method
```

> ⚠️ You must run migrations every time you deploy an update that includes database changes.

---

## 14. Verify Everything Is Working

Run through this checklist top to bottom.

### ✅ 14.1 Check the API health endpoint

```bash
curl http://localhost:8000/health
# Expected: {"status":"ok"}
```

### ✅ 14.2 Check the database connection

```bash
docker compose -f docker-compose.prod.yml exec api python3 -c "
import asyncio
from app.db.session import engine
from sqlalchemy import text

async def check():
    async with engine.connect() as conn:
        result = await conn.execute(text('SELECT 1'))
        print('✅ Database connected:', result.fetchone())

asyncio.run(check())
"
```

### ✅ 14.3 Check the Redis connection

```bash
docker compose -f docker-compose.prod.yml exec redis redis-cli -a $REDIS_PASSWORD ping
# Expected: PONG
```

### ✅ 14.4 Check the Celery worker

```bash
docker compose -f docker-compose.prod.yml exec worker celery -A app.celery_app inspect ping
# Expected: {"celery@...": {"ok": "pong"}}
```

### ✅ 14.5 Check the encryption key is readable

```bash
docker compose -f docker-compose.prod.yml exec api python3 -c "
from cryptography.fernet import Fernet
key = open('/data/keys/app_secret.key', 'rb').read()
f = Fernet(key)
test = f.encrypt(b'hello')
assert f.decrypt(test) == b'hello'
print('✅ Encryption key is valid and working')
"
```

### ✅ 14.6 Check the website loads

Open your browser and go to `http://yourdomain.com`.  
You should see the IEEPA Refund Calculator homepage.

> If you see an Nginx error page, check [Section 17](#17-troubleshooting-common-issues).

---

## 15. SSL / HTTPS Setup

Users must access the site over HTTPS. Here is how to get a free SSL certificate using Let's Encrypt.

### 15.1 Install Certbot

```bash
sudo apt-get install -y certbot
```

### 15.2 Temporarily stop Nginx (it needs port 80)

```bash
docker compose -f docker-compose.prod.yml stop nginx
```

### 15.3 Get the certificate

```bash
sudo certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com \
  --email your-email@dimerco.com \
  --agree-tos \
  --non-interactive
```

### 15.4 Copy the certificates into the project

```bash
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem nginx/certs/fullchain.pem
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem nginx/certs/privkey.pem

# Fix ownership
sudo chown $USER:$USER nginx/certs/*.pem
chmod 600 nginx/certs/privkey.pem
```

### 15.5 Restart Nginx

```bash
docker compose -f docker-compose.prod.yml start nginx
```

### 15.6 Verify HTTPS

Open `https://yourdomain.com` in your browser. You should see a padlock icon in the address bar.

### 15.7 Set up automatic certificate renewal

SSL certificates expire every 90 days. Set up a cron job to renew automatically:

```bash
# Open the cron editor
crontab -e

# Add this line at the bottom (renews at 3 AM on the 1st and 15th of each month):
0 3 1,15 * * certbot renew --quiet && cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem /opt/refundcal/nginx/certs/fullchain.pem && cp /etc/letsencrypt/live/yourdomain.com/privkey.pem /opt/refundcal/nginx/certs/privkey.pem && docker compose -f /opt/refundcal/docker-compose.prod.yml exec nginx nginx -s reload
```

---

## 16. Ongoing Maintenance

### 🔄 Deploying an Update

When a new version of the code is released:

```bash
cd /opt/refundcal

# 1. Pull the latest code
git pull origin main

# 2. Rebuild the frontend
cd frontend && npm install && npm run build && cd ..

# 3. Copy new frontend files to Docker volume
docker run --rm \
  -v $(pwd)/frontend/dist:/source:ro \
  -v refundcal_frontend_build:/dest \
  alpine sh -c "rm -rf /dest/* && cp -r /source/. /dest/"

# 4. Rebuild the backend images
docker compose -f docker-compose.prod.yml build api worker beat

# 5. Restart services (zero-downtime rolling restart)
docker compose -f docker-compose.prod.yml up -d --no-deps api worker beat

# 6. Run any new database migrations
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

### 📊 Viewing Logs

```bash
# See all logs (live)
docker compose -f docker-compose.prod.yml logs -f

# See logs for just one service (e.g., the API)
docker compose -f docker-compose.prod.yml logs -f api

# See the last 100 lines of worker logs
docker compose -f docker-compose.prod.yml logs --tail=100 worker
```

### 💾 Backing Up the Database

```bash
# Create a database backup (replace YYYY-MM-DD with today's date)
docker compose -f docker-compose.prod.yml exec db \
  pg_dump -U ieepa_app ieepa_refund_db \
  > backups/db_backup_YYYY-MM-DD.sql

# Verify the backup file was created
ls -lh backups/
```

> Set up a daily cron job for backups and copy them to an off-site location (e.g., company NAS or cloud storage).

### 🔑 Backing Up the Encryption Key

```bash
# Copy the key to a USB drive or secure storage immediately after deployment
cp data/keys/app_secret.key /path/to/secure/offline/storage/
```

### 🛑 Stopping All Services

```bash
docker compose -f docker-compose.prod.yml down
```

### 🔁 Restarting a Single Service

```bash
# Example: restart just the API
docker compose -f docker-compose.prod.yml restart api
```

---

## 17. Troubleshooting Common Issues

### ❌ A container keeps restarting

```bash
# Check what error it is showing
docker compose -f docker-compose.prod.yml logs api
```

Look at the last few lines for the error message and refer to the sections below.

---

### ❌ "REPLACE_WITH" error on startup

**Symptom:** Logs show `ValidationError` or `ValueError` mentioning a config field.  
**Cause:** You missed filling in a placeholder value in `backend/.env`.

```bash
# Find any remaining placeholders
grep "REPLACE_WITH" backend/.env
```

Edit `backend/.env`, fill in the missing values, then restart:

```bash
docker compose -f docker-compose.prod.yml up -d
```

---

### ❌ Database connection refused

**Symptom:** `FATAL: password authentication failed for user "ieepa_app"`  
**Cause:** The `POSTGRES_PASSWORD` in `.env` doesn't match the one the database was initialised with.

```bash
# Nuclear option: delete the DB volume and start fresh (⚠️ DELETES ALL DATA)
docker compose -f docker-compose.prod.yml down -v
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

---

### ❌ Redis authentication error

**Symptom:** `WRONGPASS invalid username-password pair`  
**Cause:** The `REDIS_PASSWORD` in `.env` doesn't match what redis was started with.

Check that `REDIS_PASSWORD` in `.env` and the password in `docker-compose.prod.yml` `redis.command` match exactly. Restart Redis after any change:

```bash
docker compose -f docker-compose.prod.yml restart redis
```

---

### ❌ Nginx shows "502 Bad Gateway"

**Symptom:** The website loads but shows a 502 error.  
**Cause:** Nginx can reach the server but the FastAPI API container is not running or not healthy.

```bash
# Check if the API is running
docker compose -f docker-compose.prod.yml ps api

# Check API logs for errors
docker compose -f docker-compose.prod.yml logs --tail=50 api
```

---

### ❌ File uploads fail with "500 Internal Server Error"

**Symptom:** Uploading a Form 7501 returns an error.  
**Cause:** Often the encryption key or the `data/uploads` directory is missing or has wrong permissions.

```bash
# Check the data directories exist and are writable
docker compose -f docker-compose.prod.yml exec api ls -la /data/
docker compose -f docker-compose.prod.yml exec api ls -la /data/keys/

# If the key is missing, re-run Step 6 on the host and restart
```

---

### ❌ Google Document AI returns errors

**Symptom:** Document processing fails; worker logs show `google.auth.exceptions.DefaultCredentialsError`  
**Cause:** The GCP credentials file is missing or incorrectly placed.

```bash
# Check the file exists inside the container
docker compose -f docker-compose.prod.yml exec api ls -la /app/credentials/

# Verify the env var is set
docker compose -f docker-compose.prod.yml exec api printenv GOOGLE_APPLICATION_CREDENTIALS
```

---

### ❌ Frontend shows blank page

**Symptom:** The page loads but is completely white.  
**Cause:** The React build files were not copied to the Docker volume, or the Nginx config `root` path is wrong.

```bash
# Check if frontend files exist in the volume
docker run --rm -v refundcal_frontend_build:/data alpine ls /data/
# You should see: index.html, assets/

# If empty, re-run the frontend build steps in Section 11.1
```

---

## 📞 Support Contacts

| Issue Type | Contact |
|------------|---------|
| GCP / Document AI credentials | IT Infrastructure Team |
| Domain / DNS / SSL | Network Team |
| Application bugs | Development Team |
| Database backups | DBA / IT Ops |
| CRM API key | CRM Administrator |

---

*Document maintained by Dimerco Express Group — IT Engineering*  
*Last updated: 2026-03-25*
