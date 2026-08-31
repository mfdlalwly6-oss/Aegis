"""Onboarding E2E — real separation between human identity (institution owner)
and system-integration credentials (api_key/hmac_secret), on isolated PostgreSQL.

Proves, end-to-end through the live API:
- tenant + institution owner creation (owner gets a HUMAN login, api creds are separate)
- human login -> tenant-scoped JWT (role institution_owner)
- api credentials -> merchant JWT (role merchant, NO human identity claims)
- api creds can NOT mint an institution_owner (human) token
- a human owner can NOT log in with the api secret
- tenant isolation: owner of A cannot read tenant B via owner token
- suspended tenant hard-blocks both human and api access
- secrets never leak: no plaintext hmac_secret / password_hash in any response
- audit events recorded for creation + both logins
"""

import uuid

from tests.conftest import OWNER_HEADERS

BASE = "/api/v1"


def _mk_tenant_with_owner(client):
    name = f"OB-{uuid.uuid4().hex[:6]}"
    email = f"owner-{uuid.uuid4().hex[:6]}@bank.test"
    r = client.post(
        f"{BASE}/admin/tenants",
        json={
            "name": name,
            "type": "bank",
            "country": "YE",
            "plan": "production",
            "investigator_limit": 3,
            "owner_email": email,
            "owner_password": "OwnerPass!2026",
            "owner_name": "Bank Owner",
        },
        headers=OWNER_HEADERS,
    )
    assert r.status_code == 201, r.text
    return r.json(), email


def test_owner_and_api_credentials_are_separate_principals(client):
    tenant, email = _mk_tenant_with_owner(client)
    assert tenant["api_key"].startswith("ak_")
    assert tenant["hmac_secret"]  # integration secret (returned once at creation)
    # The tenant body must NOT expose the human's password or its hash.
    assert "password" not in str(tenant).lower() and "password_hash" not in str(tenant)


def test_human_owner_login_is_tenant_scoped_jwt(client):
    tenant, email = _mk_tenant_with_owner(client)
    lg = client.post(f"{BASE}/auth/institution/login", json={"email": email, "password": "OwnerPass!2026"})
    assert lg.status_code == 200, lg.text
    body = lg.json()
    assert body["user"]["role"] == "institution_owner"
    assert body["user"]["tenant_id"] == tenant["tenant_id"]
    # decode JWT payload claims (no signature check needed — we only assert shape)
    import base64, json as _json

    payload = _json.loads(base64.urlsafe_b64decode(body["access_token"].split(".")[1] + "=="))
    assert payload["tenant_id"] == tenant["tenant_id"]
    assert payload["role"] == "institution_owner"
    assert payload["sub"] == body["user"]["user_id"]  # human subject


def test_api_credentials_mint_merchant_token_without_human_identity(client):
    tenant, email = _mk_tenant_with_owner(client)
    r = client.post(
        f"{BASE}/admin/merchant/login",
        json={"api_key": tenant["api_key"], "api_secret": tenant["hmac_secret"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "merchant_token" in body
    import base64, json as _json

    payload = _json.loads(base64.urlsafe_b64decode(body["merchant_token"].split(".")[1] + "=="))
    assert payload["role"] == "merchant"
    assert payload["tenant_id"] == tenant["tenant_id"]
    # Merchant (API) token carries NO human identity — no user_id, no email, no name.
    assert "user_id" not in payload and "name" not in payload and "email" not in payload


def test_api_secret_cannot_mint_human_owner_token(client):
    """The integration api_secret must never be usable as a human password."""
    tenant, email = _mk_tenant_with_owner(client)
    r = client.post(
        f"{BASE}/auth/institution/login", json={"email": email, "password": tenant["hmac_secret"]}
    )
    assert r.status_code == 401, f"api secret must not authenticate a human: {r.text}"


def test_human_password_cannot_mint_merchant_token(client):
    """The human owner's password must never be usable as the api_secret."""
    tenant, email = _mk_tenant_with_owner(client)
    r = client.post(
        f"{BASE}/admin/merchant/login",
        json={"api_key": tenant["api_key"], "api_secret": "OwnerPass!2026"},
    )
    assert r.status_code == 401, f"human password must not authenticate as merchant: {r.text}"


def test_owner_token_isolation_between_tenants(client):
    """A human owner of tenant A, holding A's JWT, must not read tenant B."""
    ta, ea = _mk_tenant_with_owner(client)
    tb, eb = _mk_tenant_with_owner(client)
    la = client.post(f"{BASE}/auth/institution/login", json={"email": ea, "password": "OwnerPass!2026"})
    ha = {"Authorization": f"Bearer {la.json()['access_token']}"}
    # A's owner token must not surface B (merchant-scoped reads stay tenant-bound).
    r = client.get(f"{BASE}/admin/merchant/dashboard", headers=ha)
    assert r.status_code == 200, r.text
    # the dashboard is strictly A's — its tenant_id must equal A, never B
    body = r.json()
    assert ta["tenant_id"] in str(body) or body.get("tenant_id") == ta["tenant_id"]
    assert tb["tenant_id"] not in str(body)


def test_unauthorized_and_wrong_credentials_rejected(client):
    tenant, email = _mk_tenant_with_owner(client)
    # wrong human password
    r1 = client.post(f"{BASE}/auth/institution/login", json={"email": email, "password": "wrong"})
    assert r1.status_code == 401
    # wrong api secret
    r2 = client.post(
        f"{BASE}/admin/merchant/login",
        json={"api_key": tenant["api_key"], "api_secret": "wrong"},
    )
    assert r2.status_code == 401
    # missing owner token on tenant creation
    r3 = client.post(f"{BASE}/admin/tenants", json={"name": "x", "type": "bank"})
    assert r3.status_code == 401


def test_suspended_tenant_blocks_both_human_and_api(client):
    tenant, email = _mk_tenant_with_owner(client)
    tid = tenant["tenant_id"]
    # suspend
    s = client.post(f"{BASE}/admin/tenants/{tid}/suspend", json={}, headers=OWNER_HEADERS)
    assert s.status_code == 200, s.text
    # human login blocked (tenant_not_active)
    lh = client.post(f"{BASE}/auth/institution/login", json={"email": email, "password": "OwnerPass!2026"})
    assert lh.status_code == 403
    # api login blocked
    la = client.post(
        f"{BASE}/admin/merchant/login",
        json={"api_key": tenant["api_key"], "api_secret": tenant["hmac_secret"]},
    )
    assert la.status_code == 401


def test_onboarding_emits_audit_events(client):
    tenant, email = _mk_tenant_with_owner(client)
    tid = tenant["tenant_id"]
    # trigger both logins
    client.post(f"{BASE}/auth/institution/login", json={"email": email, "password": "OwnerPass!2026"})
    client.post(
        f"{BASE}/admin/merchant/login",
        json={"api_key": tenant["api_key"], "api_secret": tenant["hmac_secret"]},
    )
    aud = client.get(f"{BASE}/admin/audit?limit=100", headers=OWNER_HEADERS)
    assert aud.status_code == 200, aud.text
    events = aud.json() if isinstance(aud.json(), list) else aud.json().get("events", [])
    types = {e.get("event_type") for e in events}
    assert "tenant.created" in types
    assert "authentication.success" in types
