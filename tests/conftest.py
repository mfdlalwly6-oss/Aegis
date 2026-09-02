"""Shared test fixtures — isolated PostgreSQL database per test, real FastAPI client.

PostgreSQL-only testing: each test builds a FRESH database `aegis_test` from the
real migrations, runs against it, and drops it. The live `aegis` database is
NEVER touched: tests connect to the `postgres` maintenance DB to create/drop
`aegis_test`, then point the app at `aegis_test` via AEGIS_DATABASE_URL.
Safety: the fixture hard-fails if the configured URL does not point at the
isolated test database name.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]

_TEST_DB = "aegis_test"


def _load_admin_url() -> str:
    """Resolve the admin connection used ONLY to create/drop the isolated test
    database. Order: explicit AEGIS_TEST_ADMIN_URL, then AEGIS_DATABASE_URL,
    then the repo .env. The docker-network hostname 'postgres' is rewritten to
    127.0.0.1 because pytest runs on the host, not inside the compose network."""
    url = os.environ.get("AEGIS_TEST_ADMIN_URL") or os.environ.get("AEGIS_DATABASE_URL")
    if not url:
        env_file = ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("AEGIS_DATABASE_URL=") or line.startswith("DATABASE_URL="):
                    url = line.split("=", 1)[1].strip()
                    break
    if not url:
        raise RuntimeError(
            "No PostgreSQL URL found for tests. Set AEGIS_TEST_ADMIN_URL or "
            "AEGIS_DATABASE_URL (or define AEGIS_DATABASE_URL in .env)."
        )
    # The compose service name is unreachable only when pytest runs on the
    # HOST. Inside the test container (compose network) "postgres" resolves,
    # so an explicit AEGIS_TEST_ADMIN_URL is used as-is. Heuristic: if the
    # URL targets the compose host and we are not on the host, keep it.
    in_container = Path("/.dockerenv").exists()
    if in_container or os.environ.get("AEGIS_TEST_ADMIN_URL"):
        return url
    return url.replace("@postgres:", "@127.0.0.1:").replace("@postgres/", "@127.0.0.1/")


_ADMIN_URL = _load_admin_url()
# Derive the test URL by swapping the database name in the admin URL.
def _test_url(admin_url: str) -> str:
    base = admin_url.rsplit("/", 1)[0]
    return f"{base}/{_TEST_DB}"


def _ensure_test_db(fresh: bool = True):
    """Ensure the isolated aegis_test database exists.

    fresh=True  -> drop + recreate (per-test isolation for app/client tests).
    fresh=False -> create only if missing (for secondary connections to the
                   SAME migrated test DB, e.g. restart-persistence checks)."""
    import psycopg

    with psycopg.connect(_ADMIN_URL.rsplit("/", 1)[0] + "/postgres", autocommit=True) as conn:
        if fresh:
            conn.execute(f"DROP DATABASE IF EXISTS {_TEST_DB} WITH (FORCE)")
            conn.execute(f"CREATE DATABASE {_TEST_DB}")
        else:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname=%s", (_TEST_DB,)
            ).fetchone()
            if not exists:
                conn.execute(f"CREATE DATABASE {_TEST_DB}")


def test_db_url() -> str:
    """The isolated test database URL (for direct PGDatabase connections)."""
    return _test_url(_ADMIN_URL)


def _drop_test_db():
    import psycopg

    with psycopg.connect(_ADMIN_URL.rsplit("/", 1)[0] + "/postgres", autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {_TEST_DB} WITH (FORCE)")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_url = _test_url(_ADMIN_URL)
    # Hard safety: refuse to run if the resolved URL is not the isolated test DB.
    assert test_url.rstrip("/").endswith("/" + _TEST_DB), (
        f"test DB isolation violated: {test_url!r} does not target {_TEST_DB!r}"
    )
    _ensure_test_db()

    monkeypatch.setenv("AEGIS_ENV", "development")
    monkeypatch.setenv("AEGIS_OWNER_TOKEN", "test-owner-token-2026")
    monkeypatch.setenv("AEGIS_SECRET_KEY", "test-secret-key-that-is-long-enough-for-hs256")
    monkeypatch.setenv("AEGIS_DB_DRIVER", "postgres")
    monkeypatch.setenv("AEGIS_DATABASE_URL", test_url)
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

    _drop_test_db()


OWNER_HEADERS = {"X-Owner-Token": "test-owner-token-2026"}


def make_test_db(monkeypatch=None, fresh: bool = True):
    """Create a Database backed by the isolated PostgreSQL test database.

    Used by tests that previously built a local SQLite file directly. Forces
    postgres driver + the isolated test URL, so nothing can touch live data.
    Creates the fresh test DB if it does not already exist.
    """
    test_url = _test_url(_ADMIN_URL)
    assert test_url.rstrip("/").endswith("/" + _TEST_DB), "isolation violated"
    if monkeypatch is not None:
        monkeypatch.setenv("AEGIS_DB_DRIVER", "postgres")
        monkeypatch.setenv("AEGIS_DATABASE_URL", test_url)
    else:
        os.environ["AEGIS_DB_DRIVER"] = "postgres"
        os.environ["AEGIS_DATABASE_URL"] = test_url
    _ensure_test_db(fresh=fresh)
    from app.db import Database

    return Database(test_url)


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
