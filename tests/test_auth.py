"""Authentication & authorization tests."""
from tests.conftest import create_tenant, merchant_token


def test_owner_endpoints_require_token(client):
    assert client.get("/api/v1/admin/tenants").status_code == 401
    assert client.post("/api/v1/admin/tenants", json={"name": "x"}).status_code == 401


def test_rules_reload_requires_owner(client):
    assert client.post("/api/v1/rules/reload", json={"rules": []}).status_code == 401
    r = client.post("/api/v1/rules/reload", headers=client.owner_headers, json={"rules": []})
    assert r.status_code == 200


def test_score_endpoint_requires_owner(client):
    assert client.post("/api/v1/transactions/score", json={}).status_code == 401


def test_merchant_login_and_token(client):
    tenant = create_tenant(client)
    token = merchant_token(client, tenant)
    r = client.get("/api/v1/admin/merchant/me",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["tenant_id"] == tenant["tenant_id"]


def test_merchant_bad_credentials(client):
    tenant = create_tenant(client)
    r = client.post("/api/v1/admin/merchant/login",
                    json={"api_key": tenant["api_key"], "api_secret": "wrong"})
    assert r.status_code == 401


def test_merchant_cannot_use_invalid_jwt(client):
    r = client.get("/api/v1/admin/merchant/me",
                   headers={"Authorization": "Bearer invalid.jwt.token"})
    assert r.status_code == 401
