#!/usr/bin/env python3
"""Live decision-confidence verification on real AEGIS (laptop).
Sends transactions under different component-health conditions and asserts the
persisted + returned confidence reflects exactly the healthy/degraded/unavailable
state of the components at decision time (never retroactively recomputed)."""
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
               {"name": f"CONF-{uuid4().hex[:6]}", "type": "wallet", "country": "YE",
                "plan": "sandbox", "investigator_limit": 2}, OWNER)
assert st in (200, 201), body
t = json.loads(body); tid, key, sec = t["tenant_id"], t["api_key"], t["hmac_secret"]
print("tenant", tid)

def send_tx(tag, behavior=None):
    payload = {"tx_id": f"{tag}-{uuid4().hex[:8]}", "tenant_id": tid, "amount": 1200,
               "currency": "USD", "channel": "wallet", "sender_account_id": "a1",
               "beneficiary_account_id": "b1", "timestamp": datetime.now(UTC).isoformat(),
               "device": {"device_id": "d1"}}
    if behavior:
        payload["behavior"] = behavior
    raw = json.dumps(payload).encode()
    sig = hmac.new(sec.encode(), raw, hashlib.sha256).hexdigest()
    st, b = req("POST", "/api/v1/wallet/webhook", None, {"x-api-key": key, "x-wallet-signature": sig}, raw=raw)
    return st, payload["tx_id"], (json.loads(b) if b else {})

def persisted_conf(tx_id):
    st, b = req("GET", "/api/v1/admin/decisions/recent?limit=50", None, OWNER)
    rows = json.loads(b); rows = rows if isinstance(rows, list) else rows.get("decisions", [])
    r = next((x for x in rows if x.get("tx_id") == tx_id), None)
    return (float(r["confidence"]) if r and r.get("confidence") is not None else None), r

GOOD_BEHAVIOR = {"biometric_match_score": 0.95, "keystroke_entropy": 3.0, "session_duration_ms": 60000}

# 1) Full health -> confidence 1.0 (ML is trained on the laptop: ml_ready=true)
st, tx1, d1 = send_tx("CONF-FULL", GOOD_BEHAVIOR)
c1 = d1.get("confidence")
if st == 200 and c1 == 1.0: ok(f"all-healthy -> confidence=1.0 (decision={d1.get('decision')})")
else: no("full health confidence", f"http={st} conf={c1} resp={str(d1)[:200]}")

# 2) No behavior payload -> behavior degraded -> confidence ~0.95
st, tx2, d2 = send_tx("CONF-NOBH")
c2 = d2.get("confidence")
if st == 200 and abs((c2 or 0) - 0.95) < 1e-3: ok(f"behavior degraded -> confidence≈0.95 (got {c2})")
else: no("degraded confidence", f"http={st} conf={c2}")

# 3) persisted == returned (stored, not recomputed)
pc2, _ = persisted_conf(tx2)
if pc2 is not None and abs(pc2 - c2) < 1e-6: ok(f"confidence persisted verbatim ({pc2} == response)")
else: no("persisted confidence", f"persisted={pc2} response={c2}")

# 4) historical integrity: tx1 (full-health) keeps 1.0 even after tx2 ran
pc1, _ = persisted_conf(tx1)
if pc1 == 1.0: ok("historical integrity: earlier full-health decision still 1.0")
else: no("historical integrity", f"tx1 confidence now {pc1}")

# 5) reconstructible from component_health (auditable, not a black box)
health = d2.get("component_health", {})
W = {"rules": 0.35, "ml": 0.25, "graph": 0.15, "aml": 0.15, "behavior": 0.10}
frac = {"healthy": 1.0, "degraded": 0.5, "unavailable": 0.0}
expected = round(min(1.0, max(0.0, sum(frac.get(health.get(k, {}).get("status", "unavailable"), 0.0) * W[k] for k in W))), 4)
if abs((c2 or 0) - expected) < 1e-3: ok(f"confidence reconstructible from component_health (expected {expected})")
else: no("reconstructible", f"conf={c2} expected={expected} health={health}")

print(f"\nRESULT: PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
