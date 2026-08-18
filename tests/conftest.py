"""Shared test fixtures — isolated SQLite per test, real FastAPI TestClient.
Clears app.* modules between tests so each test gets fresh settings from env.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_ENV", "development")
    monkeypatch.setenv("AEGIS_OWNER_TOKEN", "test-owner-token-2026")
    monkeypatch.setenv("AEGIS_SECRET_KEY", "test-secret-key-that-is-long-enough-for-hs256")
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AEGIS_DB_PATH", str(tmp_path / "aegis-test.db"))
    monkeypatch.setenv("AEGIS_PUBLIC_URL", "http://testserver")
    monkeypatch.setenv("AEGIS_LEGACY_SECRET", "")
    monkeypatch.setenv("OPENROUTER_KEYS", "")
    monkeypatch.setenv("AI_ENABLED", "false")

    # Remove cached app modules so settings reload from the new env vars
    for name in [k for k in sys.modules if k.startswith("app.") or k == "app"]:
        del sys.modules[name]

    from app.main import app

    with TestClient(app) as c:
        c.owner_headers = {"X-Owner-Token": "test-owner-token-2026"}
        yield c


def create_tenant(client, name="Test Wallet"):
    r = client.post("/api/v1/admin/tenants", headers=client.owner_headers,
                    json={"name": name, "type": "wallet", "country": "YE"})
    assert r.status_code == 201, r.text
    return r.json()


def sign(secret: str, payload: dict) -> tuple[str, bytes]:
    import hashlib, hmac, json
    body = json.dumps(payload, separators=(",", ":")).encode()
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(), body


def merchant_token(client, tenant):
    r = client.post("/api/v1/admin/merchant/login",
                    json={"api_key": tenant["api_key"], "api_secret": tenant["hmac_secret"]})
    assert r.status_code == 200, r.text
    return r.json()["merchant_token"]
