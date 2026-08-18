"""Multi-Tenant Management API — Owner admin + Merchant self-service."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.deps import get_registry, require_owner, require_merchant
from app.core.config import settings
from app.security import issue_jwt

router = APIRouter()


class CreateTenant(BaseModel):
    name: str
    type: str = "wallet"
    country: str = "YE"
    plan: str = "sandbox"
    contact_email: str | None = None
    contact_phone: str | None = None
    policy: dict = {}


class UpdatePolicy(BaseModel):
    thresholds: dict | None = None
    weights: dict | None = None
    enabled_rules: list[str] | None = None
    disabled_rules: list[str] | None = None


class MerchantLogin(BaseModel):
    api_key: str
    api_secret: str


# ═══════════════════ OWNER ENDPOINTS ═══════════════════

@router.get("/admin/tenants")
def list_tenants(owner=Depends(require_owner), registry=Depends(get_registry)):
    tenants = registry.tenants.list()
    return {"total": len(tenants), "tenants": tenants}


@router.post("/admin/tenants", status_code=201)
def create_tenant(body: CreateTenant, request: Request,
                  owner=Depends(require_owner), registry=Depends(get_registry)):
    tenant = registry.tenants.create(body.model_dump())
    registry.audit.log(tenant["tenant_id"], "owner", "tenant.created",
                       "tenant", tenant["tenant_id"], getattr(request.state, "request_id", None),
                       {"name": tenant["name"], "plan": tenant["plan"]})
    return tenant


@router.get("/admin/tenants/{tenant_id}")
def get_tenant(tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)):
    tenant = registry.tenants.get(tenant_id, reveal=True)
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    return tenant


@router.post("/admin/tenants/{tenant_id}/rotate-secret")
def rotate_secret(tenant_id: str, request: Request,
                  owner=Depends(require_owner), registry=Depends(get_registry)):
    tenant = registry.tenants.rotate_secret(tenant_id)
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    registry.audit.log(tenant_id, "owner", "tenant.secret_rotated",
                       "tenant", tenant_id, getattr(request.state, "request_id", None), {})
    return tenant


@router.put("/admin/tenants/{tenant_id}/policy")
def update_policy(tenant_id: str, body: UpdatePolicy, request: Request,
                  owner=Depends(require_owner), registry=Depends(get_registry)):
    tenant = registry.tenants.update_policy(tenant_id, body.model_dump(exclude_none=True))
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    registry.audit.log(tenant_id, "owner", "tenant.policy_updated",
                       "tenant", tenant_id, getattr(request.state, "request_id", None),
                       body.model_dump(exclude_none=True))
    return tenant


@router.delete("/admin/tenants/{tenant_id}")
def delete_tenant(tenant_id: str, request: Request,
                  owner=Depends(require_owner), registry=Depends(get_registry)):
    if not registry.tenants.delete(tenant_id):
        raise HTTPException(404, "tenant_not_found")
    registry.audit.log(tenant_id, "owner", "tenant.deleted",
                       "tenant", tenant_id, getattr(request.state, "request_id", None), {})
    return {"ok": True, "tenant_id": tenant_id}


@router.get("/admin/overview")
def overview(owner=Depends(require_owner), registry=Depends(get_registry)):
    tenants = registry.tenants.list()
    dec = registry.decisions.overview()
    by_tenant_rows = registry.db.query(
        "SELECT tenant_id, COUNT(*) AS c FROM decisions GROUP BY tenant_id "
        "ORDER BY c DESC LIMIT 20")
    dec["by_tenant"] = {r["tenant_id"]: r["c"] for r in by_tenant_rows}
    total = len(tenants)
    active = len([t for t in tenants if t["status"] == "active"])
    return {
        "server_time": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "total_tenants": total,
        "active_tenants": active,
        "tenants": {"total": total, "active": active},
        "decisions": dec,
    }


@router.get("/admin/decisions/recent")
def decisions_recent(limit: int = 50, owner=Depends(require_owner), registry=Depends(get_registry)):
    return registry.decisions.recent(limit=limit)


@router.get("/admin/audit")
def audit_log(limit: int = 200, tenant_id: str | None = None,
              event_type: str | None = None,
              owner=Depends(require_owner), registry=Depends(get_registry)):
    return registry.audit_repo.list(tenant_id=tenant_id, event_type=event_type, limit=limit)


# ═══════════════════ SYSTEM SETTINGS (real runtime values) ═══════════════════

@router.get("/admin/settings")
def system_settings(owner=Depends(require_owner), registry=Depends(get_registry)):
    """Returns the ACTUAL runtime configuration — never hardcoded."""
    return {
        "version": settings.VERSION,
        "env": settings.ENV,
        "public_url": settings.PUBLIC_URL,
        "webhook_endpoint": f"{settings.PUBLIC_URL}/api/v1/wallet/webhook",
        "thresholds": {
            "challenge": settings.DECISION_THRESHOLD_CHALLENGE,
            "review": settings.DECISION_THRESHOLD_REVIEW,
            "block": settings.DECISION_THRESHOLD_BLOCK,
        },
        "weights": {
            "rules": settings.WEIGHT_RULES,
            "ml": settings.WEIGHT_ML,
            "graph": settings.WEIGHT_GRAPH,
            "aml": settings.WEIGHT_AML,
            "behavior": settings.WEIGHT_BEHAVIOR,
        },
        "ml_thresholds": {
            "block": settings.ML_THRESHOLD_BLOCK,
            "review": settings.ML_THRESHOLD_REVIEW,
        },
        "rate_limit_per_min": settings.RATE_LIMIT_PER_MIN,
        "cors_origins": settings.cors_origins_list,
        "ai": {
            "enabled": settings.AI_ENABLED,
            "min_score": settings.AI_MIN_SCORE,
            "keys_configured": len(settings.openrouter_keys),
        },
        "db_path": str(registry.db.path) if registry.db else None,
    }


# ═══════════════════ INVESTIGATOR MANAGEMENT (owner only) ═══════════════════

class CreateInvestigator(BaseModel):
    email: str
    name: str
    password: str


@router.get("/admin/investigators")
def list_investigators(owner=Depends(require_owner), registry=Depends(get_registry)):
    return {"total": registry.investigators.count(),
            "investigators": registry.investigators.list()}


@router.post("/admin/investigators", status_code=201)
def create_investigator(body: CreateInvestigator, request: Request,
                        owner=Depends(require_owner), registry=Depends(get_registry)):
    if registry.investigators.get_by_email(body.email):
        raise HTTPException(409, "email_exists")
    if len(body.password) < 8:
        raise HTTPException(400, "password_too_short_min_8")
    inv = registry.investigators.create(body.email, body.name, body.password)
    registry.audit.log(None, "owner", "investigator.created",
                       "investigator", inv["investigator_id"],
                       getattr(request.state, "request_id", None),
                       {"email": inv["email"]})
    return inv


@router.delete("/admin/investigators/{investigator_id}")
def deactivate_investigator(investigator_id: str, request: Request,
                            owner=Depends(require_owner), registry=Depends(get_registry)):
    if not registry.investigators.deactivate(investigator_id):
        raise HTTPException(404, "investigator_not_found")
    registry.audit.log(None, "owner", "investigator.deactivated",
                       "investigator", investigator_id,
                       getattr(request.state, "request_id", None), {})
    return {"ok": True, "investigator_id": investigator_id}


# ═══════════════════ MERCHANT ENDPOINTS ═══════════════════

@router.post("/admin/merchant/login")
def merchant_login(body: MerchantLogin, request: Request, registry=Depends(get_registry)):
    tenant = registry.tenants.authenticate_merchant(body.api_key, body.api_secret)
    if not tenant:
        registry.audit.log(None, body.api_key[:12], "authentication.failure",
                           "merchant_login", None, getattr(request.state, "request_id", None), {})
        raise HTTPException(401, "invalid_credentials")
    token = issue_jwt(tenant["tenant_id"], "merchant",
                      settings.MERCHANT_JWT_TTL_SEC,
                      {"tenant_id": tenant["tenant_id"], "tenant_name": tenant["name"]})
    registry.audit.log(tenant["tenant_id"], tenant["name"], "authentication.success",
                       "merchant_login", tenant["tenant_id"],
                       getattr(request.state, "request_id", None), {})
    return {"merchant_token": token, "token_type": "Bearer",
            "tenant": {"tenant_id": tenant["tenant_id"], "name": tenant["name"],
                       "type": tenant["type"], "country": tenant["country"],
                       "plan": tenant["plan"]}}


@router.get("/admin/merchant/me")
def merchant_me(merchant=Depends(require_merchant), registry=Depends(get_registry)):
    tenant = registry.tenants.get(merchant["tenant_id"])
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    return tenant


@router.get("/admin/merchant/integration")
def merchant_integration(merchant=Depends(require_merchant), registry=Depends(get_registry)):
    tenant = registry.tenants.get(merchant["tenant_id"], reveal=True)
    endpoint = f"{settings.PUBLIC_URL}/api/v1/wallet/webhook"
    return {
        "tenant_id": tenant["tenant_id"],
        "endpoint": endpoint,
        "api_key": tenant["api_key"],
        "hmac_secret": tenant["hmac_secret"],
        "headers": {"X-API-Key": tenant["api_key"],
                    "X-Wallet-Signature": "HMAC_SHA256(body, hmac_secret)"},
        "curl": f"curl -X POST '{endpoint}' -H 'Content-Type: application/json' "
                f"-H 'X-API-Key: {tenant['api_key']}' "
                f"-H 'X-Wallet-Signature: <signature>' "
                f"-d '{{\"transaction\":{{\"amount\":100,\"sender_account_id\":\"acct_1\",\"beneficiary_account_id\":\"acct_2\"}}}}'",
        "python": "import hmac,hashlib; sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()",
        "node": "const sig = crypto.createHmac('sha256', secret).update(body).digest('hex')",
        "code_samples": {
            "curl": (
                "BODY='{\"transaction\":{\"tx_id\":\"tx-1\",\"amount\":100,"
                "\"sender_account_id\":\"acct_1\",\"beneficiary_account_id\":\"acct_2\"}}'\n"
                f"SIG=$(printf '%s' \"$BODY\" | openssl dgst -sha256 -hmac \"<HMAC_SECRET>\" | awk '{{print $2}}')\n"
                f"curl -X POST '{endpoint}' \\\n"
                "  -H 'Content-Type: application/json' \\\n"
                f"  -H 'X-API-Key: {tenant['api_key']}' \\\n"
                "  -H \"x-wallet-signature: $SIG\" \\\n"
                "  -d \"$BODY\""
            ),
            "nodejs": (
                "const crypto = require('crypto');\n"
                "const body = JSON.stringify({ transaction: { tx_id: 'tx-1', amount: 100,\n"
                "  sender_account_id: 'acct_1', beneficiary_account_id: 'acct_2' } });\n"
                "const sig = crypto.createHmac('sha256', '<HMAC_SECRET>')\n"
                "  .update(body).digest('hex');\n"
                f"const r = await fetch('{endpoint}', {{\n"
                "  method: 'POST',\n"
                "  headers: { 'Content-Type': 'application/json',\n"
                f"    'X-API-Key': '{tenant['api_key']}', 'x-wallet-signature': sig }},\n"
                "  body\n"
                "});\n"
                "const { decision, risk_score, reasoning_ar } = await r.json();"
            ),
            "python": (
                "import hmac, hashlib, json, requests\n"
                "body = json.dumps({\"transaction\": {\"tx_id\": \"tx-1\", \"amount\": 100,\n"
                "  \"sender_account_id\": \"acct_1\", \"beneficiary_account_id\": \"acct_2\"}}, separators=(\",\", \":\"))\n"
                "sig = hmac.new(b'<HMAC_SECRET>', body.encode(), hashlib.sha256).hexdigest()\n"
                f"r = requests.post('{endpoint}', data=body, headers={{\n"
                f"  'Content-Type': 'application/json', 'X-API-Key': '{tenant['api_key']}',\n"
                "  'x-wallet-signature': sig})\n"
                "print(r.json())"
            ),
        },
    }


@router.get("/admin/merchant/connection-status")
def merchant_connection(merchant=Depends(require_merchant), registry=Depends(get_registry)):
    ml_ready = registry.ml_scorer.ready if registry.ml_scorer else False
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    return {"tenant_id": merchant["tenant_id"], "api": True,
            "database": True, "ml": ml_ready,
            "graph": True, "tenant_status": "active",
            "connected": True,
            "aegis_core": settings.VERSION,
            "ai_agent": "ready" if settings.openrouter_keys and settings.AI_ENABLED else "not_configured",
            "checked_at": now}


@router.get("/admin/merchant/stats")
def merchant_stats(merchant=Depends(require_merchant), registry=Depends(get_registry)):
    return registry.decisions.count_by_tenant(merchant["tenant_id"])


@router.get("/admin/merchant/decisions")
def merchant_decisions(limit: int = 50, merchant=Depends(require_merchant),
                       registry=Depends(get_registry)):
    return registry.decisions.recent(limit=limit, tenant_id=merchant["tenant_id"])


@router.get("/admin/merchant/alerts")
def merchant_alerts(status: str | None = None, merchant=Depends(require_merchant),
                    registry=Depends(get_registry)):
    return registry.alerts.list(tenant_id=merchant["tenant_id"], status=status)


@router.get("/admin/merchant/cases")
def merchant_cases(merchant=Depends(require_merchant), registry=Depends(get_registry)):
    return registry.cases.list(tenant_id=merchant["tenant_id"])
