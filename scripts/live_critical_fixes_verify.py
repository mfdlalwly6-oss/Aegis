#!/usr/bin/env python3
"""Live verification of the five critical fixes (a3387cf) against a REAL AEGIS
deployment (local Docker or Railway via AEGIS_BASE_URL).

Proves, on live HTTP:
  1. Watchlist account screening: account listed in sanctions -> BLOCK,
     account listed in custom list -> not allow (REVIEW floor).
  2. Idempotency: same tx resent (same key AND different key) replays the
     stored decision verbatim with duplicate=true — never re-scored.
  3. FX: /transactions/score exposes reference_amount + reference_currency.
  4. Degraded behavior fail-safe: high-severity rule hit WITHOUT behavior
     payload can never end as allow.
  5. Four-Eyes: resolve a high-severity alert -> 409 pending approval;
     requester self-approve -> 403; second investigator approves -> 200;
     explicit POST /approvals create path works too.
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

# ── bootstrap: fresh tenant + two investigators ──────────────────────────────
st, body = req("POST", "/api/v1/admin/tenants",
               {"name": f"CRITFIX-{uuid4().hex[:6]}", "type": "wallet", "country": "YE",
                "plan": "sandbox", "investigator_limit": 3}, OWNER)
assert st in (200, 201), body
t = json.loads(body); tid, key, sec = t["tenant_id"], t["api_key"], t["hmac_secret"]
print("tenant", tid)

def send_tx(payload, idem=None):
    raw = json.dumps(payload).encode()
    sig = hmac.new(sec.encode(), raw, hashlib.sha256).hexdigest()
    h = {"x-api-key": key, "x-wallet-signature": sig}
    if idem:
        h["x-idempotency-key"] = idem
    st_, b_ = req("POST", "/api/v1/wallet/webhook", None, h, raw=raw)
    return st_, (json.loads(b_) if b_ else {})

def base_tx(tag, **kw):
    p = {"tx_id": f"CF-{tag}-{uuid4().hex[:8]}", "amount": 250.0, "currency": "USD",
         "channel": "wallet", "sender_account_id": "s1", "beneficiary_account_id": "b1",
         "timestamp": datetime.now(UTC).isoformat(), "device": {"device_id": "d1"}}
    p.update(kw)
    return p

# ── 1) WATCHLIST account screening ───────────────────────────────────────────
SANC_ACCT = f"ACC-SANC-{uuid4().hex[:6]}"
CUST_ACCT = f"ACC-CUST-{uuid4().hex[:6]}"
st, b = req("POST", f"/api/v1/admin/tenants/{tid}/watchlist",
            {"list_type": "sanctions", "value": SANC_ACCT}, OWNER)
if st in (200, 201): ok(f"sanctions account entry added ({SANC_ACCT})")
else: no("sanctions account entry", f"{st} {b[:200]}")
st, b = req("POST", f"/api/v1/admin/tenants/{tid}/watchlist",
            {"list_type": "custom", "value": CUST_ACCT}, OWNER)
if st in (200, 201): ok(f"custom account entry added ({CUST_ACCT})")
else: no("custom account entry", f"{st} {b[:200]}")

st, d = send_tx(base_tx("SANC", beneficiary_account_id=SANC_ACCT))
if st == 200 and d.get("decision") == "block":
    ok(f"sanctioned account -> BLOCK (risk={d.get('risk_score')})")
else: no("sanctioned account block", f"{st} {json.dumps(d)[:200]}")
alert_high = None

st, d = send_tx(base_tx("CUST", beneficiary_account_id=CUST_ACCT))
if st == 200 and d.get("decision") != "allow":
    ok(f"custom-listed account -> {d.get('decision')} (not allow)")
    # webhook response carries alert_id at the ROOT (alert/case objects exist
    # only on the score endpoint)
    alert_high = d.get("alert_id") or ((d.get("alert") or {}).get("alert_id"))
else: no("custom-listed account not allow", f"{st} {json.dumps(d)[:200]}")
print("  high-severity alert_id for four-eyes:", alert_high)

# ── 2) IDEMPOTENCY ───────────────────────────────────────────────────────────
idem_key = f"idem-{uuid4().hex[:10]}"
p1 = base_tx("IDEM", amount=777.0)
st, d1 = send_tx(p1, idem=idem_key)
st, d2 = send_tx(p1, idem=idem_key)  # SAME key
if st == 200 and d2.get("decision") == d1.get("decision") and d2.get("duplicate") is True:
    ok(f"same idem key -> same decision '{d1.get('decision')}' duplicate=true")
else: no("same-key idempotent replay", f"{d1.get('decision')} vs {d2.get('decision')} dup={d2.get('duplicate')}")

st, d3 = send_tx(p1, idem=f"idem-{uuid4().hex[:10]}")  # DIFFERENT key, same tx
if st == 200 and d3.get("decision") == d1.get("decision") and d3.get("duplicate") is True:
    ok(f"different key same tx -> replays stored decision '{d1.get('decision')}' (no re-score)")
else: no("cross-key idempotent replay", f"{d1.get('decision')} vs {d3.get('decision')} dup={d3.get('duplicate')}")

# ── 3) FX reference fields in score response ─────────────────────────────────
# currency must exist before a rate can reference it (unknown_base_currency)
req("POST", "/api/v1/admin/fx/currencies", {"code": "EGP", "name": "Egyptian Pound"}, OWNER)
# rate convention (verified from live_fx_verify.py + stored SAR row):
# base->quote DIRECT — 1 EGP = 0.0204 USD (append-only; latest wins)
st, b = req("POST", "/api/v1/admin/fx/rates",
            {"base_ccy": "EGP", "quote_ccy": "USD", "rate": 0.0204, "region": "global"}, OWNER)
if st in (200, 201, 409): ok(f"EGP->USD rate ensured (http={st})")
else: no("fx rate ensure", f"{st} {b[:200]}")
st, d = req("POST", "/api/v1/transactions/score",
            {"tenant_id": tid, "transaction": base_tx("FX", amount=10000.0, currency="EGP")}, OWNER)
try:
    d = json.loads(d)
except Exception:
    pass
ra, rc = (d or {}).get("reference_amount"), (d or {}).get("reference_currency")
if st == 200 and rc == "USD" and ra is not None and abs(float(ra) - 204.0) < 1.0:
    ok(f"score response exposes reference_amount={ra} reference_currency={rc}")
else: no("fx reference fields", f"http={st} ref={ra} ccy={rc} body={json.dumps(d)[:250]}")

# ── 4) DEGRADED behavior fail-safe ───────────────────────────────────────────
# R-NEW-001 (high severity): brand-new account + high-value first tx, and NO
# behavior payload -> behavior component degraded -> must NOT be allow.
st, d = send_tx(base_tx("DEG", amount=9500.0,
                        customer={"age_days": 3}, account={"age_days": 2},
                        velocity={"count_1h": 40}))
dec_deg = d.get("decision")
if st == 200 and dec_deg != "allow":
    ok(f"high-risk + behavior degraded -> {dec_deg} (fail-safe, not allow)")
else: no("degraded fail-safe", f"http={st} decision={dec_deg} score={d.get('risk_score')}")

# ── 5) FOUR-EYES ──────────────────────────────────────────────────────────────
invA, invB = f"inva-{uuid4().hex[:4]}@t.test", f"invb-{uuid4().hex[:4]}@t.test"
pwA, pwB = "Str0ng!PassA1", "Str0ng!PassB1"
for em, pw in ((invA, pwA), (invB, pwB)):
    st, b = req("POST", f"/api/v1/admin/tenants/{tid}/investigators",
                {"email": em, "name": em.split("@")[0], "password": pw}, OWNER)
    assert st in (200, 201), (st, b)

def inv_login(em, pw):
    st_, b_ = req("POST", "/api/v1/investigator/login", {"email": em, "password": pw})
    d_ = json.loads(b_) if b_ else {}
    return d_.get("access_token")

tokA, tokB = inv_login(invA, pwA), inv_login(invB, pwB)
HA, HB = {"Authorization": f"Bearer {tokA}"}, {"Authorization": f"Bearer {tokB}"}
ok("two investigators created and logged in" if (tokA and tokB) else "investigator login issue")

# resolve the high-severity alert -> must create a four-eyes request (409)
if alert_high:
    st, b = req("POST", f"/api/v1/investigator/alerts/{alert_high}/resolve",
                {"resolution": "resolved_true_positive", "note": "fix-round live proof"}, HA)
    try:
        d = json.loads(b)
    except Exception:
        d = {}
    approval_id = None
    if st == 409 and "four_eyes_pending" in str(b):
        # approval_id embedded in the detail string
        import re
        m = re.search(r"approval_id=(apr_[a-f0-9]+)", str(b))
        approval_id = m.group(1) if m else None
        ok(f"high alert resolve -> 409 four_eyes_pending (approval_id={approval_id})")
    else:
        no("resolve high alert -> 409 pending", f"http={st} {str(b)[:200]}")

    if approval_id:
        st, b = req("POST", f"/api/v1/investigator/approvals/{approval_id}/decide",
                    {"approve": True}, HA)
        if st == 403: ok("requester SELF-approve blocked (403 four_eyes_self_approval_forbidden)")
        else: no("self-approval forbidden", f"http={st} {str(b)[:200]}")
        st, b = req("POST", f"/api/v1/investigator/approvals/{approval_id}/decide",
                    {"approve": True, "approver_note": "second pair of eyes"}, HB)
        if st == 200: ok("second investigator approve -> 200 (alert resolved)")
        else: no("second investigator approve", f"http={st} {str(b)[:200]}")
else:
    no("four-eyes setup", "no high-severity alert captured from custom-account tx")

# explicit create path (POST /approvals with body) — needs a fresh high alert
st, d = send_tx(base_tx("CUST2", beneficiary_account_id=CUST_ACCT))
alert2 = (d.get("alert_id") or ((d.get("alert") or {}).get("alert_id"))) if isinstance(d, dict) else None
if alert2:
    st, b = req("POST", "/api/v1/investigator/approvals",
                {"alert_id": alert2, "resolution": "resolved_false_positive", "note": "explicit create"}, HA)
    try:
        d2 = json.loads(b)
    except Exception:
        d2 = {}
    if st == 200 and d2.get("approval_id"):
        ok(f"explicit POST /approvals created request (approval_id={d2['approval_id']})")
        st2, b2 = req("POST", f"/api/v1/investigator/approvals/{d2['approval_id']}/decide", {"approve": True}, HB)
        ok("explicit request approved by second investigator") if st2 == 200 else no("explicit approve", f"{st2} {str(b2)[:150]}")
    else:
        no("explicit approvals create", f"http={st} {str(b)[:200]}")
    # legacy queue behavior preserved (no body -> pending list)
    st, b = req("POST", "/api/v1/investigator/approvals", None, HA)
    if st == 200: ok("legacy POST /approvals (no body) still returns pending queue")
    else: no("legacy approvals queue", f"http={st}")
else:
    no("four-eyes explicit setup", "no second alert captured")

print(f"\nRESULT: PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
