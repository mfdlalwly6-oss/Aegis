#!/usr/bin/env python3
"""Live Policy Versioning verification on real AEGIS (laptop).
Steps: create tenant -> PUT policy v1 -> signed tx -> decision carries v1 stamp
-> PUT policy v2 -> signed tx -> decision carries v2 stamp
-> old decision row UNCHANGED (historical integrity)
-> unauthorized access to version endpoints -> 401
"""
import hashlib, hmac, json, os, sys, urllib.request
from datetime import UTC, datetime
from uuid import uuid4

BASE = os.environ.get("AEGIS_BASE_URL", "http://localhost:8000")
TOKEN = os.environ.get("OWNER_TOKEN") or open("/home/zr0/Aegis/.env").read().split("AEGIS_OWNER_TOKEN=")[1].split("\n")[0].strip()
PASS = FAIL = 0

def ok(m):
    global PASS; PASS += 1; print(f"PASS  {m}")

def no(m, d=""):
    global FAIL; FAIL += 1; print(f"FAIL  {m} -> {d}")

def req(method, path, body=None, headers=None, raw=None):
    url = BASE + path
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

OWNER = {"X-Owner-Token": TOKEN}

# 1) create tenant
st, body = req("POST", "/api/v1/admin/tenants",
               {"name": f"TXPV-{uuid4().hex[:6]}", "type": "wallet", "country": "YE",
                "plan": "sandbox", "investigator_limit": 2}, OWNER)
assert st in (200, 201), body
t = json.loads(body)
tid, key, sec = t["tenant_id"], t["api_key"], t["hmac_secret"]
print("tenant", tid)

def put_policy(block, note):
    st, b = req("PUT", f"/api/v1/admin/tenants/{tid}/policy",
                {"thresholds": {"challenge": 0.35, "review": 0.60, "block": block}, "note": note}, OWNER)
    assert st == 200, b
    return json.loads(b)

def send_tx(tag):
    payload = {"tx_id": f"{tag}-{uuid4().hex[:8]}", "tenant_id": tid, "amount": 5000,
               "currency": "USD", "channel": "wallet", "sender_account_id": "s1",
               "beneficiary_account_id": "b1", "timestamp": datetime.now(UTC).isoformat(),
               "device": {"device_id": "d1"}}
    raw = json.dumps(payload).encode()
    sig = hmac.new(sec.encode(), raw, hashlib.sha256).hexdigest()
    st, b = req("POST", "/api/v1/wallet/webhook", None,
                {"x-api-key": key, "x-wallet-signature": sig}, raw=raw)
    d = json.loads(b) if b else {}
    return st, payload["tx_id"], d

def decision_stamp(tx_id):
    """Read the decision's policy_version stamp via the owner API (works for any
    AEGIS_BASE_URL — local Docker or Railway — no direct DB access needed)."""
    st, b = req("GET", "/api/v1/admin/decisions/recent?limit=50", None, OWNER)
    rows = json.loads(b); rows = rows if isinstance(rows, list) else rows.get("decisions", [])
    r = next((x for x in rows if x.get("tx_id") == tx_id), None)
    return (r.get("rule_set_version") or "") if r else ""

# 2) policy v1 -> tx1 stamps v1
r = put_policy(0.85, "v1")
ok(f"v1 recorded: policy_version={r.get('policy_version')} hash={r.get('policy_hash','')[:8]}")
st, tx1, d1 = send_tx("PV-LIVE1")
stamp1 = decision_stamp(tx1)
if st == 200 and "#v1:" in stamp1:
    ok(f"tx1 decision={d1.get('decision')} stamp={stamp1}")
else:
    no("tx1 stamp", f"http={st} stamp={stamp1!r} resp={str(d1)[:150]}")

# 3) policy v2 -> tx2 stamps v2
r2 = put_policy(0.92, "v2")
ok(f"v2 recorded: policy_version={r2.get('policy_version')}")
st, tx2, d2 = send_tx("PV-LIVE2")
stamp2 = decision_stamp(tx2)
if st == 200 and "#v2:" in stamp2:
    ok(f"tx2 decision={d2.get('decision')} stamp={stamp2}")
else:
    no("tx2 stamp", f"http={st} stamp={stamp2!r} resp={str(d2)[:150]}")

# 4) historical integrity: tx1 row still v1 after v2 became active
stamp1_after = decision_stamp(tx1)
if stamp1_after == stamp1 and "#v1:" in stamp1_after:
    ok(f"historical integrity: tx1 still stamped {stamp1_after}")
else:
    no("historical integrity", f"before={stamp1} after={stamp1_after}")

# 5) version content immutability via API
st, b = req("GET", f"/api/v1/admin/tenants/{tid}/policy/versions/1", None, OWNER)
v1 = json.loads(b)
if st == 200 and abs(v1["policy"]["thresholds"]["block"] - 0.85) < 1e-9:
    ok(f"v1 content intact (block=0.85, status={v1['status']})")
else:
    no("v1 immutability", b[:150])

# 6) authorization: endpoints reject missing/wrong owner token
st_no, _ = req("GET", f"/api/v1/admin/tenants/{tid}/policy/versions")
st_bad, _ = req("GET", f"/api/v1/admin/tenants/{tid}/policy/versions", None, {"X-Owner-Token": "wrong"})
st_act, _ = req("POST", f"/api/v1/admin/tenants/{tid}/policy/versions/1/activate")
if st_no == 401 and st_bad == 401 and st_act == 401:
    ok("version endpoints protected (no-token=401 bad-token=401 activate-no-token=401)")
else:
    no("authorization", f"{st_no},{st_bad},{st_act}")

print(f"\nRESULT: PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
