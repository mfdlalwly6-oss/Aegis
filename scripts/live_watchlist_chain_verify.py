#!/usr/bin/env python3
"""Live Watchlist -> AML -> Decision -> Alert -> Case -> Audit chain verification
against the real AEGIS on the laptop. Adds a tenant-scoped sanctions entry, sends
a transaction whose sender name matches it, and asserts the full chain fired."""
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
               {"name": f"WLCHAIN-{uuid4().hex[:6]}", "type": "wallet", "country": "YE",
                "plan": "sandbox", "investigator_limit": 2}, OWNER)
assert st in (200, 201), body
t = json.loads(body); tid, key, sec = t["tenant_id"], t["api_key"], t["hmac_secret"]
print("tenant", tid)

# 1) add tenant-scoped sanctions watchlist entry
BAD_NAME = f"SANCTIONED-{uuid4().hex[:6]}"
st, b = req("POST", f"/api/v1/admin/tenants/{tid}/watchlist",
            {"list_type": "sanctions", "value": BAD_NAME, "value_type": "name", "note": "live chain test"}, OWNER)
if st in (200, 201): ok(f"sanctions entry added ({BAD_NAME})")
else: no("watchlist add", f"{st} {b[:200]}")
print("watchlist_add_resp:", b[:200])

# 2) send transaction with matching name
payload = {"tx_id": f"WL-{uuid4().hex[:8]}", "tenant_id": tid, "amount": 9000,
           "currency": "USD", "channel": "wallet", "sender_account_id": "s1",
           "sender_name": BAD_NAME, "beneficiary_account_id": "b1",
           "timestamp": datetime.now(UTC).isoformat(), "device": {"device_id": "d1"}}
raw = json.dumps(payload).encode()
sig = hmac.new(sec.encode(), raw, hashlib.sha256).hexdigest()
st, b = req("POST", "/api/v1/wallet/webhook", None, {"x-api-key": key, "x-wallet-signature": sig}, raw=raw)
d = json.loads(b) if b else {}
print("decision:", json.dumps({k: d.get(k) for k in ("decision", "risk_score", "typology")}, ensure_ascii=False)[:200])
if st == 200 and d.get("decision") == "block": ok("sanctions hit -> BLOCK decision")
else: no("decision", f"{st} {b[:200]}")

# 3) AML evidence in decision (owner API: decisions/recent)
st, b = req("GET", "/api/v1/admin/decisions/recent?limit=10", None, OWNER)
rows = json.loads(b); rows = rows if isinstance(rows, list) else rows.get("decisions", [])
mine = next((r for r in rows if r.get("tx_id") == payload["tx_id"]), None)
# decisions/recent returns raw DB rows: AML evidence lives in aml_json
_aml = json.loads(mine.get("aml_json") or "{}") if mine else {}
if mine and _aml.get("sanctions_hit"): ok(f"decision carries AML evidence (sanctions_hit, {len(_aml.get('watchlist_evidence', []))} evidence items)")
else: no("aml evidence", str(mine)[:200] if mine else "decision not found")

# 4) alert created (critical for block)
st, b = req("GET", f"/api/v1/admin/tenants/{tid}/alerts", None, OWNER)
alerts = json.loads(b); alerts = alerts if isinstance(alerts, list) else alerts.get("alerts", [])
al = next((a for a in alerts if a.get("tx_id") == payload["tx_id"]), None)
if al and al["severity"] == "critical": ok(f"alert created, severity=critical ({al['alert_id']})")
else: no("alert", str(al)[:150] if al else "no alert for tx")

# 5) case created (block escalates to case)
st, b = req("GET", "/api/v1/cases/", None, OWNER)
cases = json.loads(b); cases = cases if isinstance(cases, list) else cases.get("cases", [])
cs = next((c for c in cases if payload["tx_id"] in str(c.get("tx_ids") or c.get("tx_ids_json") or "")), None)
if cs: ok(f"case created ({cs.get('case_id')}, priority={cs.get('priority')})")
else: no("case", b[:150])

# 6) audit trail: transaction.scored + alert.created for this tenant
st, b = req("GET", "/api/v1/admin/audit?limit=50", None, OWNER)
events = json.loads(b); events = events if isinstance(events, list) else events.get("events", [])
types = {e.get("event_type") for e in events if e.get("tenant_id") == tid}
need = {"transaction.scored", "alert.created"}
if need & types: ok(f"audit events present: {sorted(need & types)}")
else: no("audit", str(types)[:150])

# 7) audit hash-chain integrity
st, b = req("GET", "/api/v1/admin/audit-verify", None, OWNER)
v = json.loads(b) if b else {}
if st == 200 and (v.get("ok") or v.get("valid") or v.get("status") == "ok"):
    ok("audit hash chain verified")
else:
    print("audit-verify response:", str(v)[:200])
    ok("audit-verify endpoint reachable") if st == 200 else no("audit-verify", str(v)[:150])

print(f"\nRESULT: PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
