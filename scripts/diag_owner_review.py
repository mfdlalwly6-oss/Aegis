"""Diagnose owner-review flow end-to-end against the live server (clean, isolated tenant)."""
import hashlib, hmac, json, time
import httpx

BASE = "http://localhost:8000"
OWNER = "flLPeQtZ68SfzY3ofo_3PLoZpa0-iKn0kmCc4f4ceUz6E61KAxwD5C7m0gcor68N"
OH = {"X-Owner-Token": OWNER}
c = httpx.Client(base_url=BASE, timeout=30)
ts = int(time.time())

r = c.post("/api/v1/admin/tenants", headers=OH, json={
    "name": f"Diag {ts}", "type": "bank", "country": "YE", "plan": "production",
    "investigator_limit": 5, "owner_email": f"diag{ts}@d.test",
    "owner_password": "OwnerPass!2026", "owner_name": "DiagOwner",
    "timezone": "Asia/Aden"})
print("create tenant:", r.status_code)
t = r.json(); TID, AK, HS = t["tenant_id"], t["api_key"], t["hmac_secret"]

r = c.post("/api/v1/auth/institution/login", json={"email": f"diag{ts}@d.test", "password": "OwnerPass!2026"})
print("owner login:", r.status_code)
TOK = r.json()["access_token"]; H = {"Authorization": f"Bearer {TOK}"}

body = {"transaction": {"tx_id": f"diag-tx-{ts}", "amount": 5200, "currency": "USD",
        "sender_account_id": "sd1", "beneficiary_account_id": "bd1",
        "device": {"device_id": "dd1"}},
        "context": {"account_age_days": 5, "impossible_travel": True}}
payload = json.dumps(body, separators=(",", ":"))
sig = hmac.new(HS.encode(), payload.encode(), hashlib.sha256).hexdigest()
r = c.post("/api/v1/wallet/webhook", headers={"X-API-Key": AK, "x-wallet-signature": sig}, content=payload)
print("webhook status:", r.status_code, "decision:", r.json().get("decision"))

r = c.get("/api/v1/admin/merchant/feed?filter=all", headers=H)
print("feed:", r.status_code, "counts=", r.json().get("counts"))
txs = r.json().get("transactions", [])
alrtx = [x for x in txs if x.get("alert_id")]
print("rows with alert_id:", len(alrtx))
if alrtx:
    aid = alrtx[0]["alert_id"]
    r = c.post(f"/api/v1/admin/merchant/reviews/{aid}/decision", headers=H,
               json={"decision": "allow", "note": "diag approve"})
    print("owner review POST:", r.status_code, r.text[:300])
    r = c.get("/api/v1/admin/merchant/manual-reviews", headers=H)
    j = r.json()
    print("manual-reviews:", r.status_code,
          "first_actor_type=" + (j[0].get("actor_type") if j else "<empty list>"),
          "decided_by=" + (j[0].get("decided_by") if j else "-"))
else:
    print("NO ALERT -> owner review path not exercisable with this tx (decision likely challenge)")
