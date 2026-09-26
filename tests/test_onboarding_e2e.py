"""Onboarding E2E — separation between human identity (institution owner) and
system-integration credentials (api_key/hmac_secret), on isolated PostgreSQL.

After the key-login removal, the ONLY human sign-in is owner email+password.
API Key / HMAC remain strictly integration (webhook) credentials.

Proves end-to-end through the live API:
- tenant + institution owner creation (owner gets a HUMAN login; api creds separate)
- human login -> tenant-scoped JWT (role institution_owner)
- the legacy key-login endpoint is GONE (404) — no human API-key login exists
- api creds can NOT mint a human token, and a human password is NOT an api secret
- tenant isolation: owner of A cannot read tenant B via owner token
- suspended tenant hard-blocks the human login
- secrets never leak: no plaintext hmac_secret / password_hash in any response
- integration credentials are MASKED by default and revealed only via password step-up
- audit events recorded for creation + login
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


def _login(client, email, pw="OwnerPass!2026"):
    return client.post(f"{BASE}/auth/institution/login", json={"email": email, "password": pw})


def test_owner_and_api_credentials_are_separate_principals(client):
    tenant, email = _mk_tenant_with_owner(client)
    assert tenant["api_key"].startswith("ak_")
    assert tenant["hmac_secret"]  # integration secret (returned once at creation)
    # The tenant body must NOT expose the human's password or its hash.
    assert "password" not in str(tenant).lower() and "password_hash" not in str(tenant)


def test_human_owner_login_is_tenant_scoped_jwt(client):
    tenant, email = _mk_tenant_with_owner(client)
    lg = _login(client, email)
    assert lg.status_code == 200, lg.text
    body = lg.json()
    assert body["user"]["role"] == "institution_owner"
    assert body["user"]["tenant_id"] == tenant["tenant_id"]
    import base64, json as _json

    payload = _json.loads(base64.urlsafe_b64decode(body["access_token"].split(".")[1] + "=="))
    assert payload["tenant_id"] == tenant["tenant_id"]
    assert payload["role"] == "institution_owner"
    assert payload["sub"] == body["user"]["user_id"]  # human subject


def test_legacy_key_login_endpoint_removed(client):
    """The human 'API key + secret' login endpoint must no longer exist."""
    tenant, email = _mk_tenant_with_owner(client)
    r = client.post(
        f"{BASE}/admin/merchant/login",
        json={"api_key": tenant["api_key"], "api_secret": tenant["hmac_secret"]},
    )
    assert r.status_code == 404, f"key-login endpoint must be removed, got {r.status_code}: {r.text}"


def test_api_secret_cannot_mint_human_owner_token(client):
    """The integration api_secret must never be usable as a human password."""
    tenant, email = _mk_tenant_with_owner(client)
    r = _login(client, email, tenant["hmac_secret"])
    assert r.status_code == 401, f"api secret must not authenticate a human: {r.text}"


def test_owner_token_isolation_between_tenants(client):
    """A human owner of tenant A, holding A's JWT, must not read tenant B."""
    ta, ea = _mk_tenant_with_owner(client)
    tb, eb = _mk_tenant_with_owner(client)
    la = _login(client, ea)
    ha = {"Authorization": f"Bearer {la.json()['access_token']}"}
    r = client.get(f"{BASE}/admin/merchant/dashboard", headers=ha)
    assert r.status_code == 200, r.text
    body = r.json()
    assert ta["tenant_id"] in str(body) or body.get("tenant_id") == ta["tenant_id"]
    assert tb["tenant_id"] not in str(body)


def test_unauthorized_and_wrong_credentials_rejected(client):
    tenant, email = _mk_tenant_with_owner(client)
    # wrong human password
    r1 = _login(client, email, "wrong")
    assert r1.status_code == 401
    # missing owner token on tenant creation
    r3 = client.post(f"{BASE}/admin/tenants", json={"name": "x", "type": "bank"})
    assert r3.status_code == 401


def test_suspended_tenant_blocks_human_login(client):
    tenant, email = _mk_tenant_with_owner(client)
    tid = tenant["tenant_id"]
    s = client.post(f"{BASE}/admin/tenants/{tid}/suspend", json={}, headers=OWNER_HEADERS)
    assert s.status_code == 200, s.text
    lh = _login(client, email)
    assert lh.status_code == 403


def test_integration_credentials_masked_by_default(client):
    """GET /integration must NOT return plaintext credentials."""
    tenant, email = _mk_tenant_with_owner(client)
    lg = _login(client, email)
    h = {"Authorization": f"Bearer {lg.json()['access_token']}"}
    r = client.get(f"{BASE}/admin/merchant/integration", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("credentials_masked") is True
    assert tenant["hmac_secret"] not in str(body)
    assert tenant["api_key"] not in str(body)


def test_integration_reveal_requires_password(client):
    tenant, email = _mk_tenant_with_owner(client)
    lg = _login(client, email)
    h = {"Authorization": f"Bearer {lg.json()['access_token']}"}
    # wrong password -> stays hidden
    bad = client.post(f"{BASE}/admin/merchant/integration/reveal", json={"password": "nope"}, headers=h)
    assert bad.status_code == 401
    # correct password -> revealed (and matches the issued credentials)
    ok = client.post(f"{BASE}/admin/merchant/integration/reveal",
                     json={"password": "OwnerPass!2026"}, headers=h)
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["api_key"] == tenant["api_key"]
    assert body["hmac_secret"] == tenant["hmac_secret"]


def test_institution_owner_cannot_rotate(client):
    """Rotation is a Platform Owner capability only. The owner-facing rotation
    endpoint is removed, so an institution owner gets 404 and NO change."""
    tenant, email = _mk_tenant_with_owner(client)
    lg = _login(client, email)
    h = {"Authorization": f"Bearer {lg.json()['access_token']}"}
    r = client.post(f"{BASE}/admin/merchant/integration/rotate",
                    json={"password": "OwnerPass!2026"}, headers=h)
    assert r.status_code in (403, 404), f"owner rotation must be denied, got {r.status_code}"
    # api_key unchanged after the denied attempt
    from app.main import app
    row = app.state.registry.db.query_one(
        "SELECT api_key FROM tenants WHERE tenant_id=?", (tenant["tenant_id"],))
    assert row["api_key"] == tenant["api_key"]


def test_platform_owner_rotates_and_invalidates_old_pair(client):
    """Platform Owner rotates the full pair atomically; old credentials die,
    new ones are active, and the audit event carries no secrets."""
    tenant, email = _mk_tenant_with_owner(client)
    r = client.post(f"{BASE}/admin/tenants/{tenant['tenant_id']}/rotate-secret",
                    json={}, headers=OWNER_HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["api_key"] != tenant["api_key"]
    assert body["hmac_secret"] != tenant["hmac_secret"]
    assert body["api_key"].startswith("ak_")
    # audit recorded the rotation without leaking the secret value
    aud = client.get(f"{BASE}/admin/audit?limit=100", headers=OWNER_HEADERS)
    events = aud.json() if isinstance(aud.json(), list) else aud.json().get("events", [])
    types = {e.get("event_type") for e in events}
    assert "owner.integration_credentials.rotated" in types
    blob = str(events)
    assert body["hmac_secret"] not in blob and tenant["hmac_secret"] not in blob


def test_change_owner_password_flow(client):
    tenant, email = _mk_tenant_with_owner(client)
    lg = _login(client, email)
    h = {"Authorization": f"Bearer {lg.json()['access_token']}"}
    # wrong current password -> rejected
    bad = client.post(f"{BASE}/admin/merchant/change-password",
                      json={"current_password": "nope", "new_password": "NewPass!999"}, headers=h)
    assert bad.status_code == 401
    # correct current password -> success
    ok = client.post(f"{BASE}/admin/merchant/change-password",
                     json={"current_password": "OwnerPass!2026", "new_password": "NewPass!999"}, headers=h)
    assert ok.status_code == 200, ok.text
    # old password now fails, new password works
    assert _login(client, email, "OwnerPass!2026").status_code == 401
    assert _login(client, email, "NewPass!999").status_code == 200


def test_onboarding_emits_audit_events(client):
    tenant, email = _mk_tenant_with_owner(client)
    _login(client, email)
    aud = client.get(f"{BASE}/admin/audit?limit=100", headers=OWNER_HEADERS)
    assert aud.status_code == 200, aud.text
    events = aud.json() if isinstance(aud.json(), list) else aud.json().get("events", [])
    types = {e.get("event_type") for e in events}
    assert "tenant.created" in types
    assert "authentication.success" in types
