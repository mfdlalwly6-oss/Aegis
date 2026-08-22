"""AEGIS live red-team suite — runs against the live HTTP webhook (HMAC).
Reads credentials from .env at runtime; prints NO secrets.
"""
import json, hmac, hashlib, urllib.request, re, urllib.error
from datetime import datetime, timezone, timedelta

env = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(".env").read(), re.M))
OWNER = env.get("AEGIS_OWNER_TOKEN", "")
BASE = "http://localhost:8000/api/v1"

def call(method, path, body=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method,
        data=(json.dumps(body).encode() if body is not None else None),
        headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}

s, T = call("POST", "/admin/tenants",
            {"name": "REDTEAM-BANK", "type": "bank", "country": "YE"},
            {"X-Owner-Token": OWNER})
ak, sk = T["api_key"], T["hmac_secret"]

def hook(amount, ccy, sender, ben, key, region="aden", ts=None, device=None, fx=None):
    tx = {"tx_id": key, "amount": amount, "currency": ccy,
          "sender_account_id": sender, "beneficiary_account_id": ben, "region": region}
    if ts: tx["timestamp"] = ts
    if device: tx["device"] = device
    if fx: tx["fx"] = fx
    body = json.dumps({"transaction": tx}).encode()
    sig = hmac.new(sk.encode(), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(BASE + "/wallet/webhook", data=body, method="POST",
        headers={"Content-Type": "application/json", "x-api-key": ak,
                 "x-wallet-signature": sig, "x-idempotency-key": key})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code}

def show(tag, r):
    m = r.get("money") or {}
    dec = r.get("decision", "?")
    risk = r.get("risk_score", "?")
    ref = m.get("reference_amount")
    fx = m.get("fx_status", "-")
    typ = r.get("typology", "-")
    print("%-34s dec=%-9s risk=%-7s ref=%-9s fx=%-13s typ=%s" % (tag, dec, risk, ref, fx, typ))

print("=== P11 RED TEAM (live) ===")
print("-- A. currency is context, not verdict: same number 9500 in 3 currencies --")
show("9500 USD", hook(9500, "USD", "atk1", "b1", "rt-1"))
show("9500 SAR", hook(9500, "SAR", "atk1", "b1", "rt-2"))
show("9500 YER (~6 USD trivial)", hook(9500, "YER", "atk1", "b1", "rt-3"))

print("-- B. cross-currency structuring: 4x ~9300 USD split across USD/SAR/YER --")
for i, (a, c) in enumerate([(9300, "USD"), (34875, "SAR"), (14601000, "YER"), (9400, "USD")]):
    show("structuring tx%d %s" % (i + 1, c), hook(a, c, "ring1", "bX", "rt-s%d" % i))

print("-- C. FX manipulation: fake low institution rate on 20M YER --")
show("fake fx rate", hook(20000000, "YER", "atk2", "offshore", "rt-fx", fx={"rate": 0.0000001}))

print("-- D. timestamp manipulation: +5 days future --")
future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
show("future timestamp", hook(9000, "USD", "atk3", "b3", "rt-ts", ts=future))

print("-- E. replay / idempotency abuse --")
hook(500, "USD", "atk4", "b4", "rt-replay")
r = hook(500, "USD", "atk4", "b4", "rt-replay")
print("replay duplicate flag:", r.get("duplicate"))

print("-- F. VPN + brand-new device + new beneficiary + 9000 USD --")
show("vpn+newdev+newben", hook(9000, "USD", "atk5", "newben", "rt-vpn",
                               device={"device_id": "brandNewDev", "vpn": True}))

print("-- G. unknown currency --")
show("unknown ZZZ", hook(10000, "ZZZ", "atk6", "b6", "rt-unk"))

print("-- H. normal Yemeni user: small daily amounts across currencies --")
show("5000 YER grocery", hook(5000, "YER", "normal1", "grocery", "rt-n1"))
show("150 SAR rent", hook(150, "SAR", "normal1", "landlord", "rt-n2"))
show("100 USD family", hook(100, "USD", "normal1", "family", "rt-n3"))
print("=== DONE ===")
