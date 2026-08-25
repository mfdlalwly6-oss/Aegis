"""Shared test fixtures — isolated SQLite per test, real FastAPI TestClient.
Each test gets a fresh DB and a freshly imported app (settings reloaded from env).
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
    monkeypatch.setenv("AEGIS_DB_DRIVER", "sqlite")  # hard isolation: tests never touch live PG
    monkeypatch.setenv("AEGIS_PUBLIC_URL", "http://testserver")
    monkeypatch.setenv("AEGIS_LEGACY_SECRET", "")
    monkeypatch.setenv("OPENROUTER_KEYS", "")
    monkeypatch.setenv("AI_ENABLED", "false")
    monkeypatch.setenv("AEGIS_INVESTIGATOR_EMAIL", "")
    monkeypatch.setenv("AEGIS_INVESTIGATOR_PASSWORD", "")
    monkeypatch.setenv("AEGIS_INVESTIGATOR_NAME", "")

    # Remove cached app modules so settings reload from the new env vars per test
    for name in [k for k in sys.modules if k.startswith("app.") or k == "app"]:
        del sys.modules[name]

    from app.main import app

    with TestClient(app) as c:
        c.owner_headers = {"X-Owner-Token": "test-owner-token-2026"}
        yield c


OWNER_HEADERS = {"X-Owner-Token": "test-owner-token-2026"}


def create_tenant(client, **kw):
    body = {
        "name": kw.get("name", "Test Tenant"),
        "type": kw.get("type", "wallet"),
        "country": kw.get("country", "YE"),
        "plan": kw.get("plan", "sandbox"),
        "investigator_limit": kw.get("investigator_limit", 5),
        "timezone": kw.get("timezone", "Asia/Aden"),
        "owner_email": kw.get("owner_email"),
        "owner_password": kw.get("owner_password"),
        "owner_name": kw.get("owner_name"),
    }
    body = {k: v for k, v in body.items() if v is not None}
    r = client.post("/api/v1/admin/tenants", json=body, headers=OWNER_HEADERS)
    assert r.status_code == 201, r.text
    return r.json()
