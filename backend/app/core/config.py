"""Central configuration — 12-factor, environment-driven.
All values come from environment variables or .env. No secrets in code.
"""

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _database_url_env_shim() -> None:
    """Map platform-standard env vars to AEGIS_* names when unset."""
    if not os.environ.get("AEGIS_DATABASE_URL") and os.environ.get("DATABASE_URL"):
        os.environ["AEGIS_DATABASE_URL"] = os.environ["DATABASE_URL"]
        os.environ.setdefault("AEGIS_DB_DRIVER", "postgres")


_database_url_env_shim()

# Known development-only database passwords — must never be valid in production.
_DEV_DB_PASSWORDS = ("AegisPg2026Dev", "AegisApp2026Dev")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AEGIS_", extra="ignore")

    VERSION: str = "2.0.0"
    ENV: Literal["development", "staging", "production"] = "development"
    ENABLE_DOCS: bool = False
    WORKERS: int = 1
    PORT: int = 8000

    SECRET_KEY: str = Field(
        default="aegis-dev-only-secret-key-please-override-in-production",
        min_length=32,
    )
    OWNER_TOKEN: str = "aegis-dev-owner-token"

    # Production hardening: when REQUIRE_HTTPS_PROXY is true the app asserts it
    # sits behind a TLS-terminating proxy and requires TRUSTED_PROXIES to be set.
    REQUIRE_HTTPS_PROXY: bool = False
    TRUSTED_PROXIES: str = ""

    @model_validator(mode="after")
    def _reject_default_secrets_outside_dev(self):
        # The development fallbacks above must be IMPOSSIBLE outside dev: a
        # staging/production boot with a well-known SECRET_KEY (JWT forgery) or
        # OWNER_TOKEN (platform takeover) refuses to start instead of failing open.
        if self.ENV in ("staging", "production"):
            insecure = []
            if self.SECRET_KEY.startswith("aegis-dev-only-secret-key"):
                insecure.append("SECRET_KEY")
            if self.OWNER_TOKEN == "aegis-dev-owner-token":
                insecure.append("OWNER_TOKEN")
            if insecure:
                raise RuntimeError(
                    f"refusing to start: ENV={self.ENV} with default/insecure "
                    f"{', '.join(insecure)} - set real values via AEGIS_* env vars"
                )
        # Production must use real, non-default database credentials. The
        # compose file no longer embeds dev passwords, so require an explicit
        # DATABASE_URL carrying credentials and reject the known dev passwords.
        if self.ENV == "production":
            db = self.DATABASE_URL or ""
            # Require an explicit password: user:password@host. The authority
            # part is the substring between "://" and the last "@"; it must
            # contain a non-empty password after "user:".
            authority = db.split("://", 1)[-1].rsplit("@", 1)[0] if "@" in db else ""
            has_password = ":" in authority and bool(authority.split(":", 1)[1])
            if (not db) or (not has_password) or any(p in db for p in _DEV_DB_PASSWORDS):
                raise RuntimeError(
                    "refusing to start: ENV=production requires a real "
                    "AEGIS_DATABASE_URL with an explicit password "
                    "(postgresql://user:password@host/db; no empty/default/dev credentials)"
                )
            if self.REQUIRE_HTTPS_PROXY and not self.TRUSTED_PROXIES:
                raise RuntimeError(
                    "refusing to start: REQUIRE_HTTPS_PROXY=true requires TRUSTED_PROXIES"
                )
        return self

    DATA_DIR: str = "/tmp/aegis-data"
    DB_PATH: str = ""
    DB_DRIVER: str = "postgres"
    DATABASE_URL: str = ""
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

    # Rate limit (global per-IP)
    RATE_LIMIT_PER_MIN: int = 240
    CORS_ORIGINS: str = "http://localhost:8000"

    # FX / multi-currency
    REFERENCE_CURRENCY: str = "USD"
    DISPLAY_CURRENCY: str = "YER"
    FX_DEFAULT_REGION: str = "global"
    FX_STALE_HOURS: int = 24
    FX_DIVERGENCE_PCT: float = 3.0
    FX_MISSING_DECISION: str = "review"
    FX_INSTITUTION_TRUST_PCT: float = 6.0

    # Observability
    OTEL_ENDPOINT: str = ""
    LOG_LEVEL: str = "INFO"

    # AI (optional)
    AI_ENABLED: bool = True
    AI_MIN_SCORE: float = 0.45
    OPENROUTER_TIMEOUT_SEC: float = 12.0

    # Investigator bootstrap
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
