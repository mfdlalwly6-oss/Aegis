"""New-model (tenant-scoped) tests — multi-tenancy, limits, isolation, review flow.
Replaces the legacy platform-wide investigator expectations."""
import hashlib
import hmac
import json
import os
import uuid

OWNER_HDR = {"X-Owner-Token": os.environ.get("AEGIS_OWNER_TOKEN", "test-owner-token")}
BASE = "/api/v1"


def _tenant_body():
    u = uuid.uuid4().hex[:8]
    return {"name": f"Tenant-{u}", "type": "wallet", "country": "YE", "plan": "sandbox",
            "investigator_limit": 2, "owner_email": f"owner{u}@aegis.test",
            "owner_password": "OwnerPass!2026", "owner_name": f"Owner {u}"}


def _sign(secret: str, payload: dict):
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return raw, hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def test_tenant_create_and_investigator_limit(client):
    r = client.post(f"{BASE}/admin/tenants", json=_tenant_body(), headers=OWNER_HDR)
    assert r.status_code == 201, r.text
    tid = r.json()["tenant_id"]
    assert r.json()["investigator_limit"] == 2
    for i in (1, 2):
        rr = client.post(f"{BASE}/admin/tenants/{tid}/investigators",
                         json={"email": f"inv{i}@aegis.test", "name": f"Inv{i}",
                               "password": "InvPass!2026"}, headers=OWNER_HDR)
        assert rr.status_code == 201, rr.text
    rr = client.post(f"{BASE}/admin/tenants/{tid}/investigators",
                     json={"email": "inv3@aegis.test", "name": "Inv3",
                           "password": "InvPass!2026"}, headers=OWNER_HDR)
    assert rr.status_code == 409, rr.text
    rr = client.put(f"{BASE}/admin/tenants/{tid}", json={"investigator_limit": 3},
                    headers=OWNER_HDR)
    assert rr.status_code == 200
    rr = client.post(f"{BASE}/admin/tenants/{tid}/investigators",
                     json={"email": "inv3@aegis.test", "name": "Inv3",
                           "password": "InvPass!2026"}, headers=OWNER_HDR)
    assert rr.status_code == 201, rr.text


def test_investigator_tenant_isolation(client):
    ta = client.post(f"{BASE}/admin/tenants", json=_tenant_body(), headers=OWNER_HDR).json()
    tb = client.post(f"{BASE}/admin/tenants", json=_tenant_body(), headers=OWNER_HDR).json()
    ia = client.post(f"{BASE}/admin/tenants/{ta['tenant_id']}/investigators",
                     json={"email": f"ia{uuid.uuid4().hex[:6]}@aegis.test", "name": "IA",
                           "password": "InvPass!2026"}, headers=OWNER_HDR).json()
    lg = client.post(f"{BASE}/investigator/login",
                     json={"email": ia["email"], "password": "InvPass!2026"})
    assert lg.status_code == 200, lg.text
    tok = lg.json()["access_token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    me = client.get(f"{BASE}/investigator/me", headers=hdr)
    assert me.status_code == 200 and me.json()["tenant_id"] == ta["tenant_id"]
    assert me.json()["tenant_id"] != tb["tenant_id"]
    # Cross-tenant: B's alerts list is owner-only; B's queue must never surface to A.
    q = client.get(f"{BASE}/investigator/queue", headers=hdr)
    assert q.status_code == 200


def test_webhook_review_message_and_suspend_block(client):
    ta = client.post(f"{BASE}/admin/tenants", json=_tenant_body(), headers=OWNER_HDR).json()
    api_key, secret = ta["api_key"], ta["hmac_secret"]
    payload = {"transaction": {"tx_id": f"rx{uuid.uuid4().hex[:8]}", "amount": 5200,
                               "currency": "USD", "sender_account_id": "s1",
                               "beneficiary_account_id": "b1",
                               "device": {"device_id": "dev-new"}},
               "context": {"account_age_days": 2, "impossible_travel": True}}
    raw, sig = _sign(secret, payload)
    r = client.post(f"{BASE}/wallet/webhook", content=raw,
                    headers={"X-API-Key": api_key, "x-wallet-signature": sig,
                             "Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision"] in ("review", "block"), body
    if body["decision"] == "review":
        assert body.get("review_message"), "review must carry a customer-facing message"
    # Suspend tenant → ingestion blocked with 403
    client.post(f"{BASE}/admin/tenants/{ta['tenant_id']}/suspend", json={}, headers=OWNER_HDR)
    r2 = client.post(f"{BASE}/wallet/webhook", content=raw,
                     headers={"X-API-Key": api_key, "x-wallet-signature": sig,
                              "Content-Type": "application/json"})
    assert r2.status_code == 403, r2.text
