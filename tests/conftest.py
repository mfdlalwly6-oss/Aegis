"""Shared pytest fixtures — fresh ephemeral DB per session, owner token preset."""
import os
import sys
import tempfile

_DATA = tempfile.mkdtemp(prefix="aegis-test-")
os.environ["AEGIS_ENV"] = "development"
os.environ["AEGIS_DATA_DIR"] = _DATA
os.environ["AEGIS_DB_PATH"] = os.path.join(_DATA, "aegis.db")
os.environ["AEGIS_SECRET_KEY"] = "test-secret-key-0123456789abcdef"
os.environ["AEGIS_OWNER_TOKEN"] = "test-owner-token"
os.environ["AEGIS_PUBLIC_URL"] = "http://localhost:8000"
os.environ["AEGIS_INVESTIGATOR_EMAIL"] = ""
os.environ["AEGIS_INVESTIGATOR_PASSWORD"] = ""
os.environ["AEGIS_INVESTIGATOR_NAME"] = ""

for m in list(sys.modules):
    if m.startswith("app"):
        del sys.modules[m]
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient

OWNER_HEADERS = {"X-Owner-Token": "test-owner-token"}


@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


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
