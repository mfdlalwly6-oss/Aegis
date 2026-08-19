"""Investigator workflow tests — auth, queue, alerts, cases, TENANT-SCOPED RBAC."""
import json

from tests.conftest import create_investigator, create_tenant, merchant_token, sign


def _make_investigator(client, email="inv@aegis.local", password="inv-pass-2026", tenant=None):
    tenant = tenant or create_tenant(client)
    return create_investigator(client, tenant["tenant_id"], email=email, password=password)


def _login(client, email="inv@aegis.local", password="inv-pass-2026"):
    r = client.post("/api/v1/investigator/login",
                    json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _inv_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _send_review_tx(client, tenant):
    payload = {
        "transaction": {
            "tx_id": "tx-review-1", "amount": 5000, "currency": "USD",
            "sender_account_id": "acct-a", "beneficiary_account_id": "acct-b",
            "device": {"device_id": "dev-new-1"},
        },
        "context": {"impossible_travel": True, "account_age_days": 2},
    }
    sig, body = sign(tenant["hmac_secret"], payload)
    r = client.post("/api/v1/wallet/webhook",
                    headers={"X-API-Key": tenant["api_key"],
                             "x-wallet-signature": sig,
                             "Content-Type": "application/json"},
                    content=body)
    assert r.status_code == 200, r.text
    return r.json()


# ─────────────── Auth & RBAC ───────────────

def test_investigator_routes_require_auth(client):
    assert client.get("/api/v1/investigator/queue").status_code == 401
    assert client.get("/api/v1/investigator/alerts").status_code == 401
    assert client.get("/api/v1/investigator/cases").status_code == 401
    assert client.get("/api/v1/investigator/decisions/recent").status_code == 401
    assert client.get("/api/v1/investigator/stats").status_code == 401
    assert client.get("/api/v1/investigator/graph/insights").status_code == 401


def test_investigator_login_me_and_tenant(client):
    tenant = create_tenant(client)
    inv = _make_investigator(client, tenant=tenant)
    token = _login(client)
    r = client.get("/api/v1/investigator/me", headers=_inv_headers(token))
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "inv@aegis.local"
    assert body["tenant_id"] == tenant["tenant_id"]


def test_investigator_wrong_password(client):
    _make_investigator(client)
    r = client.post("/api/v1/investigator/login",
                    json={"email": "inv@aegis.local", "password": "wrong-pass"})
    assert r.status_code == 401


def test_investigator_management_requires_owner(client):
    assert client.get("/api/v1/admin/investigators").status_code == 401
    assert client.post("/api/v1/admin/investigators",
                       json={"email": "a@b.c", "name": "x", "password": "12345678"}
                       ).status_code == 401


def test_merchant_token_cannot_access_investigator_routes(client):
    tenant = create_tenant(client)
    mtok = merchant_token(client, tenant)
    r = client.get("/api/v1/investigator/queue",
                   headers={"Authorization": f"Bearer {mtok}"})
    assert r.status_code == 403


# ─────────────── Review queue & alerts lifecycle ───────────────

def test_review_queue_and_alert_lifecycle(client):
    tenant = create_tenant(client)
    _make_investigator(client, tenant=tenant)
    token = _login(client)
    res = _send_review_tx(client, tenant)
    assert res["decision"] in ("review", "block", "challenge")
    if res["decision"] == "review":
        assert res.get("review_message")  # customer-friendly message present

    queue = client.get("/api/v1/investigator/queue", headers=_inv_headers(token))
    assert queue.status_code == 200

    alerts = client.get("/api/v1/investigator/alerts", headers=_inv_headers(token))
    assert alerts.status_code == 200
    assert len(alerts.json()) >= 1
    alert = alerts.json()[0]
    aid = alert["alert_id"]

    r = client.post(f"/api/v1/investigator/alerts/{aid}/assign",
                    headers=_inv_headers(token))
    assert r.status_code == 200
    assert r.json()["status"] == "assigned"
    assert r.json()["assignee"] == "inv@aegis.local"

    r = client.post(f"/api/v1/investigator/alerts/{aid}/notes",
                    headers=_inv_headers(token), json={"text": "ملاحظة تحقق أولى"})
    assert r.status_code == 200
    assert any("ملاحظة" in n["text"] for n in r.json()["notes"])

    r = client.post(f"/api/v1/investigator/alerts/{aid}/status",
                    headers=_inv_headers(token), json={"status": "in_review"})
    assert r.status_code == 200
    assert r.json()["status"] == "in_review"

    r = client.post(f"/api/v1/investigator/alerts/{aid}/status",
                    headers=_inv_headers(token), json={"status": "bogus"})
    assert r.status_code == 400

    r = client.get(f"/api/v1/investigator/alerts/{aid}", headers=_inv_headers(token))
    assert r.status_code == 200
    body = r.json()
    assert body["transaction"] is not None
    assert len(body["history"]) >= 1

    r = client.post(f"/api/v1/investigator/alerts/{aid}/resolve",
                    headers=_inv_headers(token),
                    json={"resolution": "resolved_false_positive",
                          "note": "إنذار كاذب بعد المراجعة"})
    assert r.status_code == 200
    assert r.json()["status"] == "resolved_false_positive"


def test_alert_escalation_creates_case(client):
    tenant = create_tenant(client)
    _make_investigator(client, tenant=tenant)
    token = _login(client)
    _send_review_tx(client, tenant)
    alerts = client.get("/api/v1/investigator/alerts",
                        headers=_inv_headers(token)).json()
    aid = alerts[0]["alert_id"]
    r = client.post(f"/api/v1/investigator/alerts/{aid}/escalate-to-case",
                    headers=_inv_headers(token), json={"priority": "high"})
    assert r.status_code == 200
    case = r.json()
    assert aid in case["alert_ids"]

    r = client.get(f"/api/v1/investigator/cases/{case['case_id']}",
                   headers=_inv_headers(token))
    assert r.status_code == 200
    assert len(r.json()["alerts"]) == 1
    assert len(r.json()["transactions"]) == 1


def test_case_lifecycle_and_fraud_marking(client):
    tenant = create_tenant(client)
    _make_investigator(client, tenant=tenant)
    token = _login(client)
    _send_review_tx(client, tenant)
    alerts = client.get("/api/v1/investigator/alerts",
                        headers=_inv_headers(token)).json()
    case = client.post(
        f"/api/v1/investigator/alerts/{alerts[0]['alert_id']}/escalate-to-case",
        headers=_inv_headers(token), json={}).json()
    cid = case["case_id"]

    r = client.post(f"/api/v1/investigator/cases/{cid}/assign",
                    headers=_inv_headers(token))
    assert r.json()["assignee"] == "inv@aegis.local"

    r = client.post(f"/api/v1/investigator/cases/{cid}/notes",
                    headers=_inv_headers(token), json={"text": "أدلة الاحتيال"})
    assert r.status_code == 200

    r = client.post(f"/api/v1/investigator/cases/{cid}/resolve",
                    headers=_inv_headers(token),
                    json={"resolution": "confirmed_fraud", "note": "احتيال مؤكد"})
    assert r.status_code == 200
    assert r.json()["status"] == "closed"

    r = client.get("/api/v1/investigator/graph/account/acct-a",
                   headers=_inv_headers(token))
    assert r.status_code == 200
    assert r.json()["is_known_fraud"] is True


def test_investigator_suspension_blocks_login_and_reactivation_allows(client):
    tenant = create_tenant(client)
    _make_investigator(client, tenant=tenant)
    assert _login(client)
    # suspend via owner
    r = client.post(f"/api/v1/admin/tenants/{tenant['tenant_id']}/investigators/"
                    f"inv-suspend/suspend", headers=client.owner_headers)
    # find the real investigator id first
    invs = client.get(f"/api/v1/admin/tenants/{tenant['tenant_id']}/investigators",
                      headers=client.owner_headers).json()
    iid = invs["investigators"][0]["investigator_id"]
    r = client.post(f"/api/v1/admin/tenants/{tenant['tenant_id']}/investigators/{iid}/suspend",
                    headers=client.owner_headers)
    assert r.status_code == 200
    r = client.post("/api/v1/investigator/login",
                    json={"email": "inv@aegis.local", "password": "inv-pass-2026"})
    assert r.status_code == 401
    # reactivate
    r = client.post(f"/api/v1/admin/tenants/{tenant['tenant_id']}/investigators/{iid}/activate",
                    headers=client.owner_headers)
    assert r.status_code == 200
    assert _login(client)
