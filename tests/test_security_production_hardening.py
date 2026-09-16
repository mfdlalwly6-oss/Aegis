"""Regression tests for production hardening (auth rate limiting, secrets, TLS/HSTS)."""
import importlib
import os
import pytest


def _fresh_settings(env: dict):
    # Do NOT reload the module: config.py builds `settings` at import time, so a
    # reload under production env would raise outside pytest.raises. Instead set
    # env vars and return the class — pydantic-settings reads env at __init__.
    for k in ("AEGIS_ENV","AEGIS_SECRET_KEY","AEGIS_OWNER_TOKEN","AEGIS_DATABASE_URL"):
        os.environ.pop(k, None)
    for k, v in env.items():
        os.environ[k] = v
    from app.core.config import Settings
    return Settings


class TestAuthRateLimit:
    def test_bruteforce_login_blocked_after_limit(self, client):
        codes = [
            client.post("/api/v1/auth/institution/login",
                        json={"email": "victim@x.local", "password": f"bad{i}"}).status_code
            for i in range(15)
        ]
        assert 429 in codes, f"expected a 429 after limit, got {codes}"

    def test_legit_login_not_blocked(self, client):
        r = client.post("/api/v1/auth/institution/login",
                        json={"email": "legit@x.local", "password": "wrong"})
        assert r.status_code in (401, 403)

    def test_forgot_password_always_200(self, client):
        r = client.post("/api/v1/auth/institution/forgot-password",
                        json={"email": "nobody@x.local"})
        assert r.status_code == 200

    def test_non_auth_endpoint_not_throttled(self, client):
        r = client.get("/health")
        assert r.status_code == 200


class TestProductionSecrets:
    def test_prod_rejects_default_secret_key(self):
        S = _fresh_settings({
            "AEGIS_ENV": "production",
            "AEGIS_SECRET_KEY": "aegis-dev-only-secret-key-please-override-in-production",
            "AEGIS_OWNER_TOKEN": "real-owner-token-value-here",
            "AEGIS_DATABASE_URL": "postgresql://u:RealPass123@h:5432/db",
        })
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            S(ENV="production", _env_file=None)

    def test_prod_rejects_default_owner_token(self):
        S = _fresh_settings({
            "AEGIS_ENV": "production",
            "AEGIS_SECRET_KEY": "R" * 40,
            "AEGIS_OWNER_TOKEN": "aegis-dev-owner-token",
            "AEGIS_DATABASE_URL": "postgresql://u:RealPass123@h:5432/db",
        })
        with pytest.raises(RuntimeError, match="OWNER_TOKEN"):
            S(ENV="production", _env_file=None)

    def test_prod_rejects_dev_db_password(self):
        S = _fresh_settings({
            "AEGIS_ENV": "production",
            "AEGIS_SECRET_KEY": "R" * 40,
            "AEGIS_OWNER_TOKEN": "real-owner-token-value-here",
            "AEGIS_DATABASE_URL": "postgresql://aegis_app:AegisApp2026Dev@h:5432/db",
        })
        with pytest.raises(RuntimeError, match="AEGIS_DATABASE_URL"):
            S(ENV="production", _env_file=None)

    def test_prod_accepts_real_secrets(self):
        S = _fresh_settings({
            "AEGIS_ENV": "production",
            "AEGIS_SECRET_KEY": "R" * 40,
            "AEGIS_OWNER_TOKEN": "real-owner-token-value-here",
            "AEGIS_DATABASE_URL": "postgresql://aegis_app:RealDbPass456@h:5432/db",
        })
        s = S(ENV="production", _env_file=None)
        assert s.OWNER_TOKEN == "real-owner-token-value-here"


class TestSecretsNotLeaked:
    def test_login_error_has_no_secret(self, client):
        r = client.post("/api/v1/auth/institution/login",
                        json={"email": "x@x.local", "password": "wrong"})
        assert "invalid_credentials" in r.text or r.status_code in (401, 403)

    def test_malformed_json_no_internal_leak(self, client):
        r = client.post("/api/v1/auth/institution/login",
                        content=b"{broken", headers={"Content-Type": "application/json"})
        assert r.status_code == 422
        assert "traceback" not in r.text.lower()


class TestTLSHeaders:
    def test_hsts_only_on_https(self, client):
        r = client.get("/health")
        assert "strict-transport-security" not in {k.lower() for k in r.headers}
        r2 = client.get("/health", headers={"x-forwarded-proto": "https"})
        assert r2.headers.get("strict-transport-security", "").startswith("max-age=")


class TestArenaRegression:
    """A1-A8 stay protected after the hardening changes."""
    def test_a1_decisions_recent_requires_auth(self, client):
        assert client.get("/api/v1/decisions/recent").status_code in (401, 403)

    def test_webhook_get_method_not_allowed(self, client):
        assert client.get("/api/v1/wallet/webhook").status_code == 405

    def test_webhook_bad_hmac_rejected(self, client):
        r = client.post("/api/v1/wallet/webhook", content=b"{}",
                        headers={"x-api-key": "ak_x", "x-signature": "bad"})
        assert r.status_code == 401


class TestDatabaseUrlValidator:
    """Production DATABASE_URL must carry an explicit user:password@ credentials."""

    def _s(self, url):
        for k in ("AEGIS_ENV","AEGIS_SECRET_KEY","AEGIS_OWNER_TOKEN","AEGIS_DATABASE_URL"):
            os.environ.pop(k, None)
        os.environ.update({
            "AEGIS_ENV": "production",
            "AEGIS_SECRET_KEY": "R" * 40,
            "AEGIS_OWNER_TOKEN": "real-owner-token-value-here",
            "AEGIS_DATABASE_URL": url,
        })
        from app.core.config import Settings
        return Settings

    def test_rejects_url_without_password(self):
        # postgresql://u@host/db — no password segment -> reject
        with pytest.raises(RuntimeError, match="AEGIS_DATABASE_URL"):
            self._s("postgresql://u@h:5432/db")(ENV="production", _env_file=None)

    def test_rejects_url_with_empty_password(self):
        # postgresql://u:@host/db — empty password -> reject
        with pytest.raises(RuntimeError, match="AEGIS_DATABASE_URL"):
            self._s("postgresql://u:@h:5432/db")(ENV="production", _env_file=None)

    def test_rejects_dev_password(self):
        with pytest.raises(RuntimeError, match="AEGIS_DATABASE_URL"):
            self._s("postgresql://aegis_app:AegisApp2026Dev@h:5432/db")(ENV="production", _env_file=None)

    def test_accepts_valid_url_with_password(self):
        s = self._s("postgresql://aegis_app:RealDbPass456@h:5432/db")(ENV="production", _env_file=None)
        assert "RealDbPass456" in s.DATABASE_URL

    def test_accepts_valid_postgres_scheme_variant(self):
        # postgres:// (no "-ql") with creds must also pass
        s = self._s("postgres://u:Str0ng!Pass@h:5432/db")(ENV="production", _env_file=None)
        assert "Str0ng!Pass" in s.DATABASE_URL
