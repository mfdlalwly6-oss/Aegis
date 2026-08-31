#!/usr/bin/env python3
"""Live Onboarding verification on real AEGIS (laptop): human identity vs API
credentials separation, tenant isolation, suspension blocking, audit events."""
import base64, json, os, sys, urllib.request
from uuid import uuid4

BASE = os.environ.get("AEGIS_BASE_URL", "http://localhost:8000")
TOKEN = os.environ.get("OWNER_TOKEN") or open("/home/zr0/Aegis/.env").read().split("AEGIS_OWNER_TOKEN=")[1].split("\n")[0].strip()
PASS = FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"PASS  {m}")
def no(m, d=""):
    global FAIL; FAIL += 1; print(f"FAIL  {m} -> {d}")

def req(method, path, body=None, headers=None):
    r = urllib.request.Request(BASE + path, data=(json.dumps(body).encode() if body is not None else None), method=method)
    r.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

def decode_jwt(tok):
    return json.loads(base64.urlsafe_b64decode(tok.split(".")[1] + "=="))

OWNER = {"X-Owner-Token": TOKEN}

def mk_tenant(tag):
    email = f"ob-{tag}-{uuid4().hex[:6]}@bank.test"
    st, b = req("POST", "/api/v1/admin/tenants",
                {"name": f"OBL-{tag}-{uuid4().hex[:4]}", "type": "bank", "country": "YE",
                 "plan": "production", "investigator_limit": 3,
                 "owner_email": email, "owner_password": "OwnerPass!2026", "owner_name": "Bank Owner"}, OWNER)
    assert st in (200, 201), b
    return json.loads(b), email

ta, ea = mk_tenant("a")
tb, eb = mk_tenant("b")
print("tenants", ta["tenant_id"], tb["tenant_id"])

# 1) separate principals, no secret leak in tenant body
if ta["api_key"].startswith("ak_") and "password_hash" not in str(ta).lower():
    ok("tenant has api_key, no password_hash leaked")
else:
    no("principal separation", str(ta)[:150])

# 2) human login -> tenant-scoped JWT (institution_owner, sub=user_id)
st, b = req("POST", "/api/v1/auth/institution/login", {"email": ea, "password": "OwnerPass!2026"})
if st == 200:
    body = json.loads(b); claims = decode_jwt(body["access_token"])
    if body["user"]["role"] == "institution_owner" and claims["tenant_id"] == ta["tenant_id"] and claims["sub"] == body["user"]["user_id"]:
        ok("human login -> institution_owner JWT (tenant-scoped, sub=user_id)")
    else:
        no("human jwt claims", json.dumps(claims)[:150])
else:
    no("human login", f"{st} {b[:150]}")

# 3) api creds -> merchant JWT, NO human identity claims
st, b = req("POST", "/api/v1/admin/merchant/login", {"api_key": ta["api_key"], "api_secret": ta["hmac_secret"]})
if st == 200:
    body = json.loads(b); claims = decode_jwt(body["merchant_token"])
    if claims["role"] == "merchant" and "user_id" not in claims and "name" not in claims and "email" not in claims:
        ok("api creds -> merchant JWT (no human identity claims)")
    else:
        no("merchant jwt claims", json.dumps(claims)[:150])
else:
    no("merchant login", f"{st} {b[:150]}")

# 4) api secret cannot mint human token; human password cannot mint merchant token
st1, _ = req("POST", "/api/v1/auth/institution/login", {"email": ea, "password": ta["hmac_secret"]})
st2, _ = req("POST", "/api/v1/admin/merchant/login", {"api_key": ta["api_key"], "api_secret": "OwnerPass!2026"})
if st1 == 401 and st2 == 401:
    ok("cross-credential misuse rejected (api_secret!=human 401, human_password!=merchant 401)")
else:
    no("cross-credential", f"{st1},{st2}")

# 5) tenant isolation: A's owner dashboard never exposes B
st, b = req("POST", "/api/v1/auth/institution/login", {"email": ea, "password": "OwnerPass!2026"})
ha = {"Authorization": f"Bearer {json.loads(b)['access_token']}"}
st, b = req("GET", "/api/v1/admin/merchant/dashboard", None, ha)
if st == 200 and tb["tenant_id"] not in b:
    ok("tenant isolation: A's dashboard does not expose B")
else:
    no("tenant isolation", f"{st} {b[:150]}")

# 6) suspended tenant blocks BOTH human and api access
req("POST", f"/api/v1/admin/tenants/{tb['tenant_id']}/suspend", {}, OWNER)
sth, _ = req("POST", "/api/v1/auth/institution/login", {"email": eb, "password": "OwnerPass!2026"})
sta, _ = req("POST", "/api/v1/admin/merchant/login", {"api_key": tb["api_key"], "api_secret": tb["hmac_secret"]})
if sth == 403 and sta == 401:
    ok("suspended tenant blocks human (403) and api (401) access")
else:
    no("suspension blocking", f"human={sth} api={sta}")

# 7) audit events recorded
st, b = req("GET", "/api/v1/admin/audit?limit=100", None, OWNER)
events = json.loads(b); events = events if isinstance(events, list) else events.get("events", [])
types = {e.get("event_type") for e in events}
if "tenant.created" in types and "authentication.success" in types:
    ok("audit events present (tenant.created + authentication.success)")
else:
    no("audit events", str(sorted(types))[:150])

print(f"\nRESULT: PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
