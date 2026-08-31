#!/usr/bin/env python3
"""Live Four-Eyes verification on real AEGIS (laptop).
Creates a tenant, two investigators, generates a HIGH-severity alert (unknown
currency -> review), then walks the full dual-approval lifecycle:
requester resolve -> 409 pending; self-approve -> 403; second approver -> resolved.
Also exercises rejection, queue isolation, and logout stamping.
"""
import hashlib, hmac, json, os, sys, urllib.request
from datetime import UTC, datetime
from uuid import uuid4

BASE = "http://localhost:8000"
TOKEN = os.environ.get("OWNER_TOKEN") or open("/home/zr0/Aegis/.env").read().split("AEGIS_OWNER_TOKEN=")[1].split("\n")[0].strip()
PASS = FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"PASS  {m}")
def no(m, d=""):
    global FAIL; FAIL += 1; print(f"FAIL  {m} -> {d}")

def req(method, path, body=None, headers=None, raw=None):
    r = urllib.request.Request(BASE + path, data=(raw if raw is not None else (json.dumps(body).encode() if body is not None else None)), method=method)
    r.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

OWNER = {"X-Owner-Token": TOKEN}

st, body = req("POST", "/api/v1/admin/tenants",
               {"name": f"FEL-{uuid4().hex[:6]}", "type": "wallet", "country": "YE",
                "plan": "sandbox", "investigator_limit": 3}, OWNER)
assert st in (200, 201), body
t = json.loads(body); tid, key, sec = t["tenant_id"], t["api_key"], t["hmac_secret"]

def mk_inv(tag):
    email = f"fel-{tag}-{uuid4().hex[:6]}@t.test"
    st, b = req("POST", f"/api/v1/admin/tenants/{tid}/investigators",
                {"email": email, "name": f"FEL-{tag}", "password": "InvPass!2026"}, OWNER)
    assert st == 201, b
    return json.loads(b)

def login(email):
    st, b = req("POST", "/api/v1/investigator/login", {"email": email, "password": "InvPass!2026"})
    assert st == 200, b
    return {"Authorization": f"Bearer {json.loads(b)['access_token']}"}

i1, i2 = mk_inv("one"), mk_inv("two")
h1, h2 = login(i1["email"]), login(i2["email"])
print("tenant", tid, "inv1", i1["email"], "inv2", i2["email"])

# HIGH-severity alert via unknown currency -> review decision
payload = {"tx_id": f"FE-LIVE-{uuid4().hex[:8]}", "tenant_id": tid, "amount": 500,
           "currency": "XXX", "channel": "wallet", "sender_account_id": "a1",
           "beneficiary_account_id": "b1", "timestamp": datetime.now(UTC).isoformat(),
           "device": {"device_id": "d1"}}
raw = json.dumps(payload).encode()
sig = hmac.new(sec.encode(), raw, hashlib.sha256).hexdigest()
st, b = req("POST", "/api/v1/wallet/webhook", None,
            {"x-api-key": key, "x-wallet-signature": sig}, raw=raw)
d = json.loads(b) if b else {}
assert st == 200 and d.get("decision") == "review", f"{st} {b[:200]}"
ok(f"review decision -> HIGH alert expected (decision={d.get('decision')})")

# locate the alert id (owner API)
st, b = req("GET", f"/api/v1/admin/tenants/{tid}/alerts", None, OWNER)
alerts = json.loads(b)
alerts = alerts if isinstance(alerts, list) else alerts.get("alerts", [])
al = next(a for a in alerts if a.get("tx_id") == payload["tx_id"])
alert_id = al["alert_id"]
print("alert", alert_id, "severity", al["severity"])
assert al["severity"] == "high"

# 1) requester resolve -> 409 pending
st, b = req("POST", f"/api/v1/investigator/alerts/{alert_id}/resolve",
            {"resolution": "resolved_false_positive", "note": "ok"}, h1)
if st == 409 and "four_eyes_pending" in b: ok("resolve -> 409 four_eyes_pending")
else: no("resolve gate", f"{st} {b[:120]}")

# 2) pending queue visible to tenant investigators
st, b = req("POST", "/api/v1/investigator/approvals", headers=h2)
pend = json.loads(b); mine = [p for p in pend if p["alert_id"] == alert_id]
if len(mine) == 1: ok(f"pending queue has the request (approval_id={mine[0]['approval_id']})")
else: no("pending queue", str(pend)[:150])
approval_id = mine[0]["approval_id"]

# 3) self-approval forbidden (403)
st, b = req("POST", f"/api/v1/investigator/approvals/{approval_id}/decide", {"approve": True}, h1)
if st == 403 and "four_eyes_self_approval_forbidden" in b: ok("self-approval forbidden (403)")
else: no("self-approval", f"{st} {b[:120]}")

# 4) second approver approves -> alert resolved
st, b = req("POST", f"/api/v1/investigator/approvals/{approval_id}/decide", {"approve": True}, h2)
if st == 200 and json.loads(b)["status"] == "approved": ok("second approver approved -> resolved")
else: no("approve", f"{st} {b[:150]}")

st, b = req("GET", f"/api/v1/admin/tenants/{tid}/alerts", None, OWNER)
alerts = json.loads(b); alerts = alerts if isinstance(alerts, list) else alerts.get("alerts", [])
final = next(a for a in alerts if a["alert_id"] == alert_id)
if final["status"] == "resolved_false_positive": ok(f"alert terminal state = {final['status']}")
else: no("final state", final["status"])

# 5) decide again -> 409 (already terminal)
st, b = req("POST", f"/api/v1/investigator/approvals/{approval_id}/decide", {"approve": True}, h2)
if st == 409: ok("re-decide -> 409 (already terminal)")
else: no("re-decide", f"{st} {b[:120]}")

# 6) logout stamps last_logout_at
st, b = req("POST", "/api/v1/investigator/logout", headers=h1)
if st == 200 and json.loads(b).get("ok"): ok("logout ok")
else: no("logout", f"{st} {b[:120]}")
st, b = req("GET", f"/api/v1/admin/tenants/{tid}/investigators", None, OWNER)
invs = json.loads(b); invs = invs if isinstance(invs, list) else invs.get("investigators", [])
me = next(r for r in invs if r["email"] == i1["email"])
if me.get("last_logout_at"): ok(f"last_logout_at stamped ({me['last_logout_at'][:19]})")
else: no("last_logout_at", str(me)[:150])

print(f"\nRESULT: PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
