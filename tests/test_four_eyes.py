"""Four-eyes (dual approval) — backend-enforced dual sign-off for high/critical
alert resolutions, plus investigator logout stamping (migration 018).

Covers: pending-request creation, self-approval forbidden, second-investigator
approval resolves the alert, rejection keeps it open, pending queue listing,
cross-tenant approval isolation, and logout stamping last_logout_at.
"""

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime

from tests.conftest import OWNER_HEADERS, create_tenant

BASE = "/api/v1"


def _mk_investigator(client, tid, tag):
    email = f"fe-{tag}-{uuid.uuid4().hex[:6]}@t.test"
    r = client.post(
        f"{BASE}/admin/tenants/{tid}/investigators",
        json={"email": email, "name": f"FE-{tag}", "password": "InvPass!2026"},
        headers=OWNER_HEADERS,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _login(client, email):
    lg = client.post(f"{BASE}/investigator/login", json={"email": email, "password": "InvPass!2026"})
    assert lg.status_code == 200, lg.text
    return {"Authorization": f"Bearer {lg.json()['access_token']}"}


def _signed_tx(client, tenant, tx_id, currency="XXX", amount=500):
    body = {
        "tx_id": tx_id,
        "amount": amount,
        "currency": currency,
        "sender_account_id": "a1",
        "beneficiary_account_id": "b1",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()
    sig = hmac.new(tenant["hmac_secret"].encode(), raw, hashlib.sha256).hexdigest()
    return client.post(
        f"{BASE}/wallet/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "x-api-key": tenant["api_key"],
            "x-wallet-signature": sig,
            "x-idempotency-key": tx_id,
        },
    )


def _alert_for_tx(client, tid, tx_id):
    r = client.get(f"{BASE}/admin/tenants/{tid}/alerts", headers=OWNER_HEADERS)
    assert r.status_code == 200, r.text
    alerts = r.json() if isinstance(r.json(), list) else r.json().get("alerts", [])
    match = [a for a in alerts if a.get("tx_id") == tx_id]
    assert match, f"alert for {tx_id} not found"
    return match[0]


def _setup_high_alert(client):
    """Unknown currency -> review decision -> HIGH severity alert."""
    t = create_tenant(client, name=f"FE-{uuid.uuid4().hex[:6]}", investigator_limit=3)
    inv1 = _mk_investigator(client, t["tenant_id"], "one")
    inv2 = _mk_investigator(client, t["tenant_id"], "two")
    tx_id = f"fe-{uuid.uuid4().hex[:8]}"
    r = _signed_tx(client, t, tx_id, currency="XXX")
    assert r.status_code == 200 and r.json()["decision"] == "review", r.text
    alert = _alert_for_tx(client, t["tenant_id"], tx_id)
    assert alert["severity"] == "high", f"expected high severity, got {alert['severity']}"
    return t, inv1, inv2, alert["alert_id"]


def test_high_severity_resolve_requires_second_approver(client):
    t, inv1, inv2, alert_id = _setup_high_alert(client)
    h1 = _login(client, inv1["email"])

    # First resolve attempt -> 409 pending request, alert NOT resolved.
    r = client.post(
        f"{BASE}/investigator/alerts/{alert_id}/resolve",
        json={"resolution": "resolved_false_positive", "note": "legit merchant"},
        headers=h1,
    )
    assert r.status_code == 409 and "four_eyes_pending" in r.json()["detail"], r.text

    still = _alert_for_tx_by_id(client, t["tenant_id"], alert_id)
    assert still["status"] not in ("resolved_true_positive", "resolved_false_positive")


def _alert_for_tx_by_id(client, tid, alert_id):
    r = client.get(f"{BASE}/admin/tenants/{tid}/alerts", headers=OWNER_HEADERS)
    alerts = r.json() if isinstance(r.json(), list) else r.json().get("alerts", [])
    return next(a for a in alerts if a["alert_id"] == alert_id)


def test_self_approval_is_forbidden_and_second_approver_resolves(client):
    t, inv1, inv2, alert_id = _setup_high_alert(client)
    h1 = _login(client, inv1["email"])
    h2 = _login(client, inv2["email"])

    client.post(
        f"{BASE}/investigator/alerts/{alert_id}/resolve",
        json={"resolution": "resolved_false_positive", "note": "ok"},
        headers=h1,
    )
    pending = client.post(f"{BASE}/investigator/approvals", headers=h2).json()
    mine = [p for p in pending if p["alert_id"] == alert_id]
    assert len(mine) == 1, f"expected one pending approval, got {pending}"
    approval_id = mine[0]["approval_id"]

    # Requester cannot approve own request.
    self_approve = client.post(
        f"{BASE}/investigator/approvals/{approval_id}/decide", json={"approve": True}, headers=h1
    )
    assert self_approve.status_code == 403
    assert "four_eyes_self_approval_forbidden" in self_approve.json()["detail"]

    # Second investigator approves -> alert resolved.
    ok = client.post(
        f"{BASE}/investigator/approvals/{approval_id}/decide", json={"approve": True}, headers=h2
    )
    assert ok.status_code == 200 and ok.json()["status"] == "approved", ok.text
    final = _alert_for_tx_by_id(client, t["tenant_id"], alert_id)
    assert final["status"] == "resolved_false_positive"

    # Approval record is terminal — a second decide is rejected.
    again = client.post(
        f"{BASE}/investigator/approvals/{approval_id}/decide", json={"approve": True}, headers=h2
    )
    assert again.status_code == 409


def test_rejection_keeps_alert_open_and_closes_request(client):
    t, inv1, inv2, alert_id = _setup_high_alert(client)
    h1 = _login(client, inv1["email"])
    h2 = _login(client, inv2["email"])

    client.post(
        f"{BASE}/investigator/alerts/{alert_id}/resolve",
        json={"resolution": "resolved_true_positive", "note": "fraud"},
        headers=h1,
    )
    pending = client.post(f"{BASE}/investigator/approvals", headers=h2).json()
    approval_id = next(p["approval_id"] for p in pending if p["alert_id"] == alert_id)

    rej = client.post(
        f"{BASE}/investigator/approvals/{approval_id}/decide", json={"approve": False}, headers=h2
    )
    assert rej.status_code == 200 and rej.json()["status"] == "rejected", rej.text
    alert = _alert_for_tx_by_id(client, t["tenant_id"], alert_id)
    assert alert["status"] not in ("resolved_true_positive", "resolved_false_positive")

    # A fresh resolve attempt after rejection creates a NEW pending request.
    r2 = client.post(
        f"{BASE}/investigator/alerts/{alert_id}/resolve",
        json={"resolution": "resolved_true_positive", "note": "retry"},
        headers=h1,
    )
    assert r2.status_code == 409 and "four_eyes_pending" in r2.json()["detail"]


def test_second_pending_request_not_duplicated(client):
    t, inv1, inv2, alert_id = _setup_high_alert(client)
    h1 = _login(client, inv1["email"])
    client.post(
        f"{BASE}/investigator/alerts/{alert_id}/resolve",
        json={"resolution": "resolved_false_positive"},
        headers=h1,
    )
    # Second attempt while one is pending -> 409, no new row created.
    r = client.post(
        f"{BASE}/investigator/alerts/{alert_id}/resolve",
        json={"resolution": "resolved_true_positive"},
        headers=h1,
    )
    assert r.status_code == 409 and "already awaits" in r.json()["detail"]


def test_approvals_are_tenant_isolated(client):
    t, inv1, inv2, alert_id = _setup_high_alert(client)
    other = create_tenant(client, name=f"FE-X-{uuid.uuid4().hex[:6]}", investigator_limit=2)
    inv_x = _mk_investigator(client, other["tenant_id"], "x")

    h1 = _login(client, inv1["email"])
    client.post(
        f"{BASE}/investigator/alerts/{alert_id}/resolve",
        json={"resolution": "resolved_false_positive"},
        headers=h1,
    )
    pending = client.post(f"{BASE}/investigator/approvals", headers=h2_headers(client, inv1)).json()
    approval_id = next(p["approval_id"] for p in pending if p["alert_id"] == alert_id)

    # Investigator of ANOTHER tenant cannot see or decide this approval.
    hx = _login(client, inv_x["email"])
    queue_x = client.post(f"{BASE}/investigator/approvals", headers=hx).json()
    assert all(p["approval_id"] != approval_id for p in queue_x)
    decide_x = client.post(
        f"{BASE}/investigator/approvals/{approval_id}/decide", json={"approve": True}, headers=hx
    )
    assert decide_x.status_code == 404


def h2_headers(client, inv):
    return _login(client, inv["email"])


def test_logout_stamps_last_logout(client):
    t = create_tenant(client, name=f"FE-L-{uuid.uuid4().hex[:6]}", investigator_limit=2)
    inv = _mk_investigator(client, t["tenant_id"], "lo")
    hdr = _login(client, inv["email"])

    before = client.get(f"{BASE}/investigator/me", headers=hdr)
    assert before.status_code == 200

    out = client.post(f"{BASE}/investigator/logout", headers=hdr)
    assert out.status_code == 200 and out.json().get("ok"), out.text

    # Verify last_logout_at stamped via owner-side investigator listing.
    lst = client.get(
        f"{BASE}/admin/tenants/{t['tenant_id']}/investigators", headers=OWNER_HEADERS
    )
    rows = lst.json() if isinstance(lst.json(), list) else lst.json().get("investigators", [])
    mine = next(r for r in rows if r["email"] == inv["email"])
    assert mine.get("last_login_at"), "last_login_at missing"
    assert mine.get("last_logout_at"), "last_logout_at missing"
    assert mine["last_logout_at"] >= mine["last_login_at"]
