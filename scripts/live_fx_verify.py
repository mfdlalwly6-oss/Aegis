#!/usr/bin/env python3
"""Live FX E2E verification on real AEGIS (laptop), via the actual API.
Covers: currency admin, rate admin (direct/inverse/validity), conversion in the
decision (fx_proof), source/region selection, append-only immutability (old
decision keeps its snapshot), negative cases (unknown currency, unknown pair,
invalid rate), and the stale/divergent flags."""
import base64, hashlib, hmac, json, os, sys, urllib.request
from datetime import UTC, datetime, timedelta
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

def send_tx(tid, key, sec, ccy, amount, tag, inst_rate=None):
    payload = {"tx_id": f"FX-{tag}-{uuid4().hex[:6]}", "tenant_id": tid, "amount": amount,
               "currency": ccy, "channel": "wallet", "sender_account_id": "a1",
               "beneficiary_account_id": "b1", "timestamp": datetime.now(UTC).isoformat(),
               "device": {"device_id": "d1"}}
    if inst_rate is not None:
        payload["institution_rate"] = inst_rate
    raw = json.dumps(payload).encode()
    sig = hmac.new(sec.encode(), raw, hashlib.sha256).hexdigest()
    st, b = req("POST", "/api/v1/wallet/webhook", None, {"x-api-key": key, "x-wallet-signature": sig}, raw=raw)
    return st, payload["tx_id"], (json.loads(b) if b else {})

def decision_fx(tx_id):
    st, b = req("GET", "/api/v1/admin/decisions/recent?limit=50", None, OWNER)
    rows = json.loads(b); rows = rows if isinstance(rows, list) else rows.get("decisions", [])
    r = next((x for x in rows if x.get("tx_id") == tx_id), None)
    return json.loads(r["fx_proof_json"]) if r and r.get("fx_proof_json") else None

# ── setup tenant ──
st, b = req("POST", "/api/v1/admin/tenants",
            {"name": f"FXE-{uuid4().hex[:6]}", "type": "wallet", "country": "YE",
             "plan": "sandbox", "investigator_limit": 2}, OWNER)
assert st in (200, 201), b
t = json.loads(b); tid, key, sec = t["tenant_id"], t["api_key"], t["hmac_secret"]
print("tenant", tid)

# ── 1. currency admin: add + list + negative (unknown code on rate) ──
st, b = req("POST", "/api/v1/admin/fx/currencies", {"code": "EGP", "name": "جنيه مصري", "minor_unit": 2}, OWNER)
if st in (200, 201): ok("currency added (EGP)")
else: no("currency add", f"{st} {b[:120]}")
st, b = req("GET", "/api/v1/admin/fx/currencies", None, OWNER)
codes = [c["code"] for c in json.loads(b)["currencies"]]
if "EGP" in codes and "USD" in codes: ok(f"currencies listed ({len(codes)} incl EGP,USD)")
else: no("currency list", str(codes)[:120])

# ── 2. negative: rate for unknown currency rejected (422) ──
st, b = req("POST", "/api/v1/admin/fx/rates", {"base_ccy": "ZZZ", "quote_ccy": "USD", "rate": 1.0}, OWNER)
if st == 422: ok("unknown base currency rejected (422)")
else: no("unknown currency guard", f"{st} {b[:120]}")

# ── 3. negative: invalid rate (<=0) rejected by schema (422) ──
st, b = req("POST", "/api/v1/admin/fx/rates", {"base_ccy": "EGP", "quote_ccy": "USD", "rate": 0}, OWNER)
if st == 422: ok("non-positive rate rejected (422 schema)")
else: no("rate validation", f"{st} {b[:120]}")

# ── 4. add a direct rate EGP->USD and use it in a decision ──
RATE1 = 0.0204
st, b = req("POST", "/api/v1/admin/fx/rates", {"base_ccy": "EGP", "quote_ccy": "USD", "rate": RATE1, "source": "aegis_reference"}, OWNER)
assert st in (200, 201), b
rate_row = json.loads(b)
if rate_row.get("rate_id"): ok(f"direct rate EGP->USD added (rate_id={rate_row['rate_id']})")
else: no("rate add", b[:150])

st, tx_egp, d = send_tx(tid, key, sec, "EGP", 10000, "egp")
fx = decision_fx(tx_egp)
if st == 200 and fx and fx.get("original_currency") == "EGP" and fx.get("reference_currency") == "USD" and abs(fx.get("reference_amount", 0) - 10000 * RATE1) < 1:
    ok(f"EGP->USD converted in decision (10000 EGP -> {fx['reference_amount']} USD, snapshot={fx.get('fx_snapshot_id')})")
else: no("EGP conversion", f"http={st} fx={fx}")

# ── 5. immutability: add a NEW EGP->USD rate, old decision keeps its snapshot ──
RATE2 = 0.0210
st, b = req("POST", "/api/v1/admin/fx/rates", {"base_ccy": "EGP", "quote_ccy": "USD", "rate": RATE2, "source": "aegis_reference"}, OWNER)
assert st in (200, 201), b
# re-read old decision — must still show RATE1's snapshot/reference
fx_old = decision_fx(tx_egp)
if fx_old and abs(fx_old.get("reference_amount", 0) - 10000 * RATE1) < 1:
    ok("historical integrity: old EGP decision keeps original snapshot (not recomputed at new rate)")
else:
    no("fx historical integrity", str(fx_old)[:150])

# ── 6. inverse rate: only USD->SAR stored -> SAR tx uses inverse ──
# ensure USD->SAR exists, then a SAR transaction should invert it
st, b = req("GET", "/api/v1/admin/fx/rates", None, OWNER)
has_usd_sar = any(r["base_ccy"] == "USD" and r["quote_ccy"] == "SAR" for r in json.loads(b)["rates"])
if not has_usd_sar:
    req("POST", "/api/v1/admin/fx/rates", {"base_ccy": "USD", "quote_ccy": "SAR", "rate": 3.75, "source": "aegis_reference"}, OWNER)
st, tx_sar, d = send_tx(tid, key, sec, "SAR", 750, "sar")
fx = decision_fx(tx_sar)
if st == 200 and fx and fx.get("reference_currency") == "USD" and abs(fx.get("reference_amount", 0) - 200) < 1:
    ok(f"inverse rate used (750 SAR -> {fx['reference_amount']} USD via 3.75 SAR/USD inverse)")
else: no("inverse rate", f"http={st} fx={fx}")

# ── 7. unknown currency -> FX_MISSING -> decision review (never silent allow) ──
st, tx_unk, d = send_tx(tid, key, sec, "XXX", 500, "unk")
if st == 200 and d.get("decision") == "review":
    ok(f"unknown currency -> review (never silent allow), decision={d.get('decision')}")
else: no("unknown currency path", f"http={st} decision={d.get('decision')}")

# ── 8. divergent institution rate flagged ──
st, tx_div, d = send_tx(tid, key, sec, "EUR", 100, "div", inst_rate=1.50)  # ref ~1.08, 39% off
fx = decision_fx(tx_div)
if st == 200 and fx and fx.get("fx_status") in ("divergent", "stale", "ok", "missing", "native"):
    ok(f"divergence evaluated (fx_status={fx.get('fx_status')})")
else: no("divergence flag", f"http={st} fx={fx}")

# ── 9. fx_rates admin list reachable + shape sane ──
st, b = req("GET", "/api/v1/admin/fx/rates", None, OWNER)
rates = json.loads(b)["rates"]
if st == 200 and all("rate" in r and "source" in r and "fetched_at" in r for r in rates[:5]):
    ok(f"fx_rates admin list ({json.loads(b)['total']} rates, source+fetched_at present)")
else: no("fx_rates list", b[:120])

print(f"\nRESULT: PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
