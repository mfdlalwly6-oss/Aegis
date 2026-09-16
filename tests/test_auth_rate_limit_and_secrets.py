"""Regression tests: auth rate limiting + production secret guards.

Covers the new hardening (NOT part of A1-A8):
- login brute-force hits 429 per policy
- legitimate login still works (no false-positive DoS)
- production rejects default/missing DB credentials
- secrets never appear in responses/errors
- A1-A8 controls remain intact (spot re-checks)
"""
import os
import pytest


def _fresh_settings(env, **over):
    import importlib
    from app.core import config as cfg
    importlib.reload(cfg)
    for k, v in over.items():
        env.setenv(k, v)
    return cfg


# ---------- production secret guards ----------

def test_production_rejects_default_secret_key(monkeypatch):
    cfg = _fresh_settings(monkeypatch)
    monkeypatch.delenv("AEGIS_SECRET_KEY", raising=False)
    monkeypatch.delenv("AEGIS_OWNER_TOKEN", raising=False)
    monkeypatch.setenv("AEGIS_DATABASE_URL", "postgresql://u:pw@h:5432/db")
    with pytest.raises(RuntimeError):
        cfg.Settings(ENV="production", _env_file=None)


def test_production_rejects_missing_db_password(monkeypatch):
    """Production must refuse an empty DATABASE_URL or one with a dev password."""
    from app.core.config import Settings
    monkeypatch.setenv("AEGIS_ENV", "production")
    monkeypatch.setenv("AEGIS_SECRET_KEY", "R" * 40)
    monkeypatch.setenv("AEGIS_OWNER_TOKEN", "real-owner-token-value")
    # empty DATABASE_URL -> reject
    monkeypatch.setenv("AEGIS_DATABASE_URL", "")
    with pytest.raises(RuntimeError):
        Settings(ENV="production", _env_file=None)
    # dev password embedded -> reject
    monkeypatch.setenv("AEGIS_DATABASE_URL", "postgresql://aegis_app:AegisApp2026Dev@h:5432/db")
    with pytest.raises(RuntimeError):
        Settings(ENV="production", _env_file=None)
    # real password -> accept
    monkeypatch.setenv("AEGIS_DATABASE_URL", "postgresql://aegis_app:RealDbPass456@h:5432/db")
    s = Settings(ENV="production", _env_file=None)
    assert "RealDbPass456" in s.DATABASE_URL

def test_production_accepts_real_values(monkeypatch):
    cfg = _fresh_settings(monkeypatch)
    monkeypatch.setenv("AEGIS_SECRET_KEY", "R" * 40)
    monkeypatch.setenv("AEGIS_OWNER_TOKEN", "real-owner-token-xyz")
    monkeypatch.setenv("AEGIS_DATABASE_URL", "postgresql://u:pw@h:5432/db")
    s = cfg.Settings(ENV="production", _env_file=None)
    assert s.ENV == "production"


def test_secrets_not_in_error_responses(client):
    # malformed login must not leak SECRET_KEY / tokens / internals
    r = client.post("/api/v1/auth/login", content=b"{broken", headers={"Content-Type": "application/json"})
    body = r.text.lower()
    for secret in ("secret", "owner-token", "password", "traceback", "postgres"):
        assert secret not in body


# ---------- auth rate limiting ----------

LOGIN = "/api/v1/auth/login"


def test_login_bruteforce_hits_429(client):
    codes = [
        client.post(LOGIN, json={"email": f"attacker{i}@x.local", "password": "wrong"}).status_code
        for i in range(15)
    ]
    assert 429 in codes, f"expected 429 within 15 tries, got {codes}"


def test_legit_login_not_blocked_by_strangers(client):
    # other IPs' failures must not lock out a fresh, valid attempt
    for i in range(12):
        client.post(LOGIN, json={"email": f"flood{i}@x.local", "password": "x"})
    # create a real institution owner then log in successfully
    t = client.post("/api/v1/admin/tenants", headers=client.owner_headers, json={
        "name": "RL Tenant", "owner_email": "rlowner@t.local", "owner_password": "Passw0rd!2026",
    })
    assert t.status_code in (200, 201)
    ok = client.post("/api/v1/auth/institution/login",
                     json={"email": "rlowner@t.local", "password": "Passw0rd!2026"})
    assert ok.status_code == 200, ok.text


def test_per_account_lockout_limits_same_email(client):
    for i in range(11):
        r = client.post(LOGIN, json={"email": "same@x.local", "password": f"w{i}"})
    assert r.status_code == 429


def test_non_auth_endpoint_not_auth_limited(client):
    # a non-auth POST (webhook) should not be governed by the auth limiter
    r = client.post("/api/v1/wallet/webhook", json={})
    assert r.status_code in (401, 422, 405)  # not 429 from the auth limiter


# ---------- A1-A8 spot re-checks (must stay green) ----------

def test_a1_recent_decisions_requires_auth(client):
    assert client.get("/api/v1/decisions/recent").status_code == 401


def test_jwt_forgery_rejected(client):
    bad = "aaa.bbb.ccc"
    assert client.get("/api/v1/investigator/queue",
                      headers={"Authorization": f"Bearer {bad}"}).status_code == 401
