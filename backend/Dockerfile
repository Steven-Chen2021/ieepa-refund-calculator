# ── Stage 1: Base ────────────────────────────────────────
FROM python:3.11-slim AS base
WORKDIR /app

# System dependencies (Tesseract + poppler for OCR fallback, WeasyPrint deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-chi-sim \
    poppler-utils \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-xlib-2.0-0 \
    libffi-dev \
    curl \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Development ─────────────────────────────────
FROM base AS development
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .
EXPOSE 8000

# ── Stage 3: Production ──────────────────────────────────
FROM base AS production
# Run as non-root for security
RUN groupadd -r appuser && useradd -r -g appuser appuser
COPY . .
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
