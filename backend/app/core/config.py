"""Central configuration — 12-factor, environment-driven.
All values come from environment variables or .env. No secrets in code.
"""

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _database_url_env_shim() -> None:
    """Map platform-standard env vars to AEGIS_* names when unset.

    Many PostgreSQL providers inject a standard unprefixed DATABASE_URL
    (Railway, Heroku, Render, managed Postgres, generic Docker). AEGIS reads
    AEGIS_DATABASE_URL (env_prefix="AEGIS_"). If only the unprefixed form exists,
    adopt it — the explicitly-prefixed form always wins when set. This keeps the
    app deployment-agnostic: configuration comes from env, code knows no provider.
    No secrets are logged or written; this only re-points an env var reference.
    """
    if not os.environ.get("AEGIS_DATABASE_URL") and os.environ.get("DATABASE_URL"):
        os.environ["AEGIS_DATABASE_URL"] = os.environ["DATABASE_URL"]
        os.environ.setdefault("AEGIS_DB_DRIVER", "postgres")


_database_url_env_shim()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AEGIS_", extra="ignore")

    VERSION: str = "2.0.0"
    ENV: Literal["development", "staging", "production"] = "development"
    # API docs/OpenAPI are disabled by default (attack-surface reduction);
    # enable explicitly via AEGIS_ENABLE_DOCS=true in dev only.
    ENABLE_DOCS: bool = False
    WORKERS: int = 1
    PORT: int = 8000

    SECRET_KEY: str = Field(
        default="aegis-dev-only-secret-key-please-override-in-production",
        min_length=32,
    )
    OWNER_TOKEN: str = "aegis-dev-owner-token"
    DATA_DIR: str = "/tmp/aegis-data"
    DB_PATH: str = ""
    DB_DRIVER: str = "postgres"  # PostgreSQL only — no SQLite driver exists
    DATABASE_URL: str = ""  # postgresql://user:pass@host:5432/db — runtime (least-privilege aegis_app)
    # Optional superuser/owner connection used ONLY by pgdb.migrate() to create
    # roles/schema (migration 008 creates aegis_app itself). If empty, migrate()
    # falls back to DATABASE_URL (works for pre-migrated databases).
    DATABASE_ADMIN_URL: str = ""
    LEGACY_SECRET: str = ""
    PUBLIC_URL: str = "http://localhost:8000"

    # Auth
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TTL_SEC: int = 3600
    MERCHANT_JWT_TTL_SEC: int = 86400

    # ML thresholds
    ML_THRESHOLD_BLOCK: float = 0.90
    ML_THRESHOLD_REVIEW: float = 0.65

    # Decision thresholds
    DECISION_THRESHOLD_CHALLENGE: float = 0.35
    DECISION_THRESHOLD_REVIEW: float = 0.60
    DECISION_THRESHOLD_BLOCK: float = 0.80

    # Risk fusion weights
    WEIGHT_RULES: float = 0.35
    WEIGHT_ML: float = 0.25
    WEIGHT_GRAPH: float = 0.15
    WEIGHT_AML: float = 0.15
    WEIGHT_BEHAVIOR: float = 0.10

    # Rate limit
    RATE_LIMIT_PER_MIN: int = 240
    CORS_ORIGINS: str = "http://localhost:8000"

    # FX / multi-currency (risk reference layer)
    REFERENCE_CURRENCY: str = "USD"  # single decision reference (FATF-equivalent)
    DISPLAY_CURRENCY: str = "YER"  # local display/policy reference (derived, not stored truth)
    FX_DEFAULT_REGION: str = "global"  # data-driven; Yemen regions live in fx_rates rows
    FX_STALE_HOURS: int = 24  # rate older than this => FX_STALE
    FX_DIVERGENCE_PCT: float = 3.0  # institution rate deviation => FX_DIVERGENT flag
    FX_MISSING_DECISION: str = "review"  # unknown currency => never silent ALLOW, never blind BLOCK
    FX_INSTITUTION_TRUST_PCT: float = 6.0  # institution rate trusted if within this % of platform reference


    # Observability
    OTEL_ENDPOINT: str = ""
    LOG_LEVEL: str = "INFO"

    # AI (optional)
    AI_ENABLED: bool = True
    AI_MIN_SCORE: float = 0.45
    OPENROUTER_TIMEOUT_SEC: float = 12.0

    # Investigator bootstrap (first-run convenience — set via env in production)
    INVESTIGATOR_EMAIL: str = ""
    PLATFORM_ADMIN_EMAIL: str = ""
    PLATFORM_ADMIN_PASSWORD: str = ""
    INVESTIGATOR_PASSWORD: str = ""
    INVESTIGATOR_NAME: str = "محقق الاحتيال"
    NOTIFICATION_PROVIDER: Literal["console", "webhook", "smtp"] = "console"
    NOTIFICATION_WEBHOOK_URL: str = ""
    NOTIFICATION_WEBHOOK_SECRET: str = ""
    NOTIFICATION_TIMEOUT_SEC: float = 5.0
    NOTIFICATION_RETRIES: int = 2
    NOTIFICATION_SMTP_HOST: str = ""
    NOTIFICATION_SMTP_PORT: int = 587
    NOTIFICATION_SMTP_USER: str = ""
    NOTIFICATION_SMTP_PASSWORD: str = ""
    NOTIFICATION_SMTP_FROM: str = ""
    NOTIFICATION_SMTP_TO: str = ""
    NOTIFICATION_SMTP_USE_TLS: bool = True

    @property
    def db_path(self) -> str:
        return self.DB_PATH or f"{self.DATA_DIR}/aegis.db"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def openrouter_keys(self) -> list[str]:
        import os

        raw = os.environ.get("OPENROUTER_KEYS", "").strip()
        if not raw or raw.startswith("your-"):
            return []
        return [
            k.strip() for k in raw.split(",") if k.strip() and not k.strip().startswith("your-")
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()


settings = get_settings()
