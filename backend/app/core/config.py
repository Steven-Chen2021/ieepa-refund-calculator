"""
Application settings loaded from .env via pydantic-settings.
"""
from pathlib import Path

from pydantic import PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    SECRET_KEY: str = "insecure-dev-secret-change-me"
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"

    # ── CORS ─────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:5173"
    CORS_ALLOW_CREDENTIALS: bool = True

    # ── JWT ──────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "insecure-dev-jwt-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Database ─────────────────────────────────────────────
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "ieepa_refund_db"
    POSTGRES_USER: str = "ieepa_app"
    POSTGRES_PASSWORD: str = "dev_password_only"
    DATABASE_URL: str = ""

    @model_validator(mode="after")
    def assemble_db_url(self) -> "Settings":
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        return self

    # ── Redis ────────────────────────────────────────────────
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_URL: str = ""
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""
    CACHE_TTL_SECONDS: int = 3600

    @model_validator(mode="after")
    def assemble_redis_url(self) -> "Settings":
        if not self.REDIS_URL:
            auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
            self.REDIS_URL = f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/0"
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = self.REDIS_URL
        if not self.CELERY_RESULT_BACKEND:
            self.CELERY_RESULT_BACKEND = self.REDIS_URL
        return self

    # ── File Storage ─────────────────────────────────────────
    DATA_ROOT: str = "/data"
    UPLOAD_DIR: str = "/data/uploads"
    REPORTS_DIR: str = "/data/reports"
    KEYS_DIR: str = "/data/keys"
    FERNET_KEY_PATH: str = "/data/keys/app_secret.key"
    MAX_UPLOAD_SIZE_MB: int = 20
    ALLOWED_EXTENSIONS: str = "pdf,jpg,jpeg,png"
    DOWNLOAD_TOKEN_EXPIRE_MINUTES: int = 15

    # ── OCR ──────────────────────────────────────────────────
    GOOGLE_APPLICATION_CREDENTIALS: str = "/app/credentials/google_service_account.json"
    GOOGLE_DOC_AI_PROJECT_ID: str = ""
    GOOGLE_DOC_AI_LOCATION: str = "us"
    GOOGLE_DOC_AI_PROCESSOR_ID: str = ""
    TESSERACT_CMD: str = "/usr/bin/tesseract"
    OCR_FALLBACK_ENABLED: bool = True
    OCR_CONFIDENCE_THRESHOLD: float = 0.80

    # ── Email ────────────────────────────────────────────────
    SMTP_HOST: str = "mailhog"
    SMTP_PORT: int = 1025
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = False
    SMTP_FROM_ADDRESS: str = "noreply@ieepa.dimerco.com"
    SMTP_FROM_NAME: str = "Dimerco IEEPA Portal"

    # ── Rate Limiting ────────────────────────────────────────
    RATE_LIMIT_UPLOAD: str = "10/hour"
    RATE_LIMIT_CALCULATE: str = "10/minute"
    RATE_LIMIT_LOGIN: str = "5/minute"
    RATE_LIMIT_GET: str = "60/minute"

    # ── CRM ──────────────────────────────────────────────────
    ENABLE_CRM_SYNC: bool = False
    CRM_WEBHOOK_URL: str = ""
    CRM_API_KEY: str = ""

    # ── Features ─────────────────────────────────────────────
    ENABLE_BULK_UPLOAD: bool = True

    # ── Cleanup Schedule ─────────────────────────────────────
    FILE_CLEANUP_TTL_HOURS: int = 24
    REPORT_CLEANUP_TTL_DAYS: int = 90
    CLEANUP_SCHEDULE_CRON: str = "0 * * * *"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.ALLOWED_HOSTS.split(",") if h.strip()]

    @property
    def allowed_extensions_set(self) -> set[str]:
        return {e.strip().lower() for e in self.ALLOWED_EXTENSIONS.split(",") if e.strip()}


settings = Settings()
