"""Multi-Tenant Management API — Owner admin + Institution (merchant) self-service."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import get_registry, require_merchant, require_owner
from app.core.config import settings
from app.security import issue_jwt

logger = structlog.get_logger(__name__)

router = APIRouter()


class CreateTenant(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    type: str = "wallet"
    country: str = "YE"
    plan: str = "sandbox"
    contact_email: str | None = None
    contact_phone: str | None = None
    policy: dict = {}
    investigator_limit: int | None = Field(default=None, ge=0, le=500)
    timezone: str | None = None
    review_message: str | None = None
    owner_email: str | None = None
    owner_password: str | None = None
    owner_name: str | None = None


class UpdateTenant(BaseModel):
    name: str | None = None
    country: str | None = None
    plan: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    investigator_limit: int | None = Field(default=None, ge=0, le=500)
    timezone: str | None = None
    review_message: str | None = None


class UpdatePolicy(BaseModel):
    thresholds: dict | None = None
    weights: dict | None = None
    enabled_rules: list[str] | None = None
    disabled_rules: list[str] | None = None
    fx_missing_action: str | None = None
    note: str | None = None  # free-text rationale, stored on the policy version


class OwnerPasswordConfirm(BaseModel):
    """Step-up re-authentication for sensitive institution-owner actions
    (reveal / rotate integration credentials). Verified server-side against the
    owner's salted password hash."""
    password: str = Field(min_length=1, max_length=200)


class ChangeOwnerPassword(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class CreateInvestigator(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=200)


class ResetPassword(BaseModel):
    password: str = Field(min_length=8, max_length=200)


# ═══════════════════ OWNER ENDPOINTS ═══════════════════


def _ensure_owner_token_valid(token: str) -> None:
    pass


@router.get("/admin/tenants")
def list_tenants(owner=Depends(require_owner), registry=Depends(get_registry)):
    tenants = registry.tenants.list()
    result = []
    for t in tenants:
        t["investigators_used"] = registry.investigators.count_active(t["tenant_id"])
        t["investigator_limit"] = t.get("investigator_limit", 5)
        result.append(t)
    return {"total": len(result), "tenants": result}


@router.post("/admin/tenants", status_code=201)
def create_tenant(
    body: CreateTenant,
    request: Request,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    data = body.model_dump(exclude_none=True)
    tenant = registry.tenants.create(data)
    # Create the first institution owner. Two modes:
    #  - invitation (preferred): owner_email WITHOUT a password → the account is
    #    created as 'invited' (cannot log in) and a secure single-use expiring
    #    invitation is emailed; the owner sets their own password on acceptance.
    #  - legacy: owner_email WITH owner_password → direct active account
    #    (kept for backward compatibility with existing admin flows/tests).
    if body.owner_email:
        existing = registry.user_repo.find_by_email_any_status(tenant["tenant_id"], body.owner_email)
        if not existing:
            invited = not body.owner_password
            user = registry.user_repo.create(
                tenant["tenant_id"],
                body.owner_email,
                body.owner_name or body.name,
                role="institution_owner",
                password=(body.owner_password or None),
                status=("invited" if invited else "active"),
            )
            if invited:
                _row, raw = registry.invitations.create_invitation(
                    tenant["tenant_id"], user["user_id"], user["email"],
                    invited_by="owner", ttl_hours=settings.INVITATION_TTL_HOURS,
                )
                registry.email.send_invitation(
                    to=user["email"], tenant_name=tenant["name"],
                    owner_name=user["name"], token=raw,
                )
                registry.audit.log(
                    tenant["tenant_id"], "owner", "owner.invited", "user",
                    user["user_id"], getattr(request.state, "request_id", None),
                    {"email": user["email"]},
                )
            else:
                registry.audit.log(
                    tenant["tenant_id"], "owner", "tenant.owner_created", "user",
                    user["user_id"], getattr(request.state, "request_id", None),
                    {"email": user["email"]},
                )
    registry.audit.log(
        tenant["tenant_id"],
        "owner",
        "tenant.created",
        "tenant",
        tenant["tenant_id"],
        getattr(request.state, "request_id", None),
        {"name": tenant["name"], "plan": tenant["plan"]},
    )
    return tenant


# ═══════════════════ INSTITUTION OWNER MANAGEMENT (admin) ═══════════════════

def _owner_summary(registry, tenant_id: str) -> dict | None:
    """The current owner row + its latest invitation state (never secrets)."""
    owners = [u for u in registry.user_repo.list_by_tenant(tenant_id)
              if u.get("role") in ("institution_owner", "tenant_admin")]
    if not owners:
        # include non-active owners too (invited/disabled)
        rows = registry.db.query(
            "SELECT user_id,tenant_id,email,name,role,status,created_at FROM users "
            "WHERE tenant_id=? AND role IN ('institution_owner','tenant_admin') ORDER BY created_at DESC",
            (tenant_id,))
        owners = [dict(r) for r in rows]
    if not owners:
        return None
    u = owners[0]
    inv = registry.invitations.latest_for_user(u["user_id"])
    return {
        "user_id": u["user_id"], "email": u["email"], "name": u["name"],
        "status": u["status"],
        "invitation_status": (inv or {}).get("status"),
        "invitation_expires_at": (inv or {}).get("expires_at"),
    }


@router.get("/admin/tenants/{tenant_id}/owner")
def get_tenant_owner(tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)):
    if not registry.tenants.get(tenant_id):
        raise HTTPException(404, "tenant_not_found")
    return {"tenant_id": tenant_id, "owner": _owner_summary(registry, tenant_id)}


@router.post("/admin/tenants/{tenant_id}/owner/resend-invitation")
def resend_invitation(tenant_id: str, request: Request, owner=Depends(require_owner), registry=Depends(get_registry)):
    """Revoke any pending invitation and issue a fresh one (single-use, 72h)."""
    tenant = registry.tenants.get(tenant_id)
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    summ = _owner_summary(registry, tenant_id)
    if not summ:
        raise HTTPException(404, "owner_not_found")
    if summ["status"] == "active":
        raise HTTPException(409, "owner_already_active")
    registry.invitations.revoke_user_pending(summ["user_id"])
    _row, raw = registry.invitations.create_invitation(
        tenant_id, summ["user_id"], summ["email"],
        invited_by="owner", ttl_hours=settings.INVITATION_TTL_HOURS,
    )
    registry.email.send_invitation(to=summ["email"], tenant_name=tenant["name"],
                                   owner_name=summ["name"], token=raw)
    registry.audit.log(tenant_id, "owner", "owner.invitation_resent", "user",
                       summ["user_id"], getattr(request.state, "request_id", None),
                       {"email": summ["email"]})
    return {"resent": True, "email": summ["email"], "expires_in_hours": settings.INVITATION_TTL_HOURS}


@router.post("/admin/tenants/{tenant_id}/owner/disable")
def disable_owner(tenant_id: str, request: Request, owner=Depends(require_owner), registry=Depends(get_registry)):
    if not registry.tenants.get(tenant_id):
        raise HTTPException(404, "tenant_not_found")
    summ = _owner_summary(registry, tenant_id)
    if not summ:
        raise HTTPException(404, "owner_not_found")
    registry.user_repo.set_status(summ["user_id"], "disabled")
    registry.invitations.revoke_user_pending(summ["user_id"])
    registry.audit.log(tenant_id, "owner", "owner.disabled", "user",
                       summ["user_id"], getattr(request.state, "request_id", None), {})
    return {"status": "disabled"}


@router.post("/admin/tenants/{tenant_id}/owner/enable")
def enable_owner(tenant_id: str, request: Request, owner=Depends(require_owner), registry=Depends(get_registry)):
    if not registry.tenants.get(tenant_id):
        raise HTTPException(404, "tenant_not_found")
    summ = _owner_summary(registry, tenant_id)
    if not summ:
        raise HTTPException(404, "owner_not_found")
    if not registry.user_repo.get(summ["user_id"]).get("password_hash"):
        raise HTTPException(409, "owner_no_password_yet")
    registry.user_repo.set_status(summ["user_id"], "active")
    registry.audit.log(tenant_id, "owner", "owner.enabled", "user",
                       summ["user_id"], getattr(request.state, "request_id", None), {})
    return {"status": "active"}



@router.get("/admin/tenants/{tenant_id}/fx-status")
def tenant_fx_status(tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)):
    """Report which FX source the resolver would use for this tenant RIGHT NOW,
    with the actual USD/YER and SAR/YER rates (§16). Source precedence:
    institution -> manual override -> reference set -> general."""
    if not registry.tenants.get(tenant_id):
        raise HTTPException(404, "tenant_not_found")
    now = datetime.now(UTC).isoformat()

    def _rate(base, quote):
        row, inv = registry.fx._lookup(base, quote, region=None, at=None, tenant_id=tenant_id)
        if row is None:
            return None
        r = float(row["rate"])
        if inv:
            r = 1.0 / r
        return {"rate": r, "source": row["source"], "rate_id": row.get("rate_id")}

    # Detect the winning tier explicitly for a human-readable label.
    manual = registry.fx.fx_repo.latest_valid("USD", "YER", at=None, tenant_id=tenant_id, tenant_only=True)
    refset = registry.fx.reference_repo.set_for_tenant(tenant_id) if registry.fx.reference_repo else None
    if manual:
        layer = "manual"
    elif refset:
        layer = "reference"
    else:
        layer = "general"

    usd = _rate("USD", "YER")
    sar = _rate("SAR", "YER")
    return {
        "tenant_id": tenant_id,
        "source_layer": layer,
        "reference_set": ({"set_id": refset["set_id"], "name": refset.get("name")} if refset else None),
        "usd_yer": (usd["rate"] if usd else None),
        "sar_yer": (sar["rate"] if sar else None),
        "usd_yer_source": (usd["source"] if usd else None),
        "sar_yer_source": (sar["source"] if sar else None),
        "at": now,
    }


@router.get("/admin/tenants/{tenant_id}")
def get_tenant(tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)):
    tenant = registry.tenants.get(tenant_id, reveal=True)
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    tenant["investigators_used"] = registry.investigators.count_active(tenant_id)
    return tenant


@router.get("/admin/tenants/{tenant_id}/alerts")
def owner_tenant_alerts(
    tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)
):
    """AEGIS Owner support view — alerts belonging to one tenant only."""
    if not registry.tenants.get(tenant_id):
        raise HTTPException(404, "tenant_not_found")
    return registry.alerts.list(tenant_id=tenant_id, limit=200)


@router.get("/admin/tenants/{tenant_id}/cases")
def owner_tenant_cases(
    tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)
):
    if not registry.tenants.get(tenant_id):
        raise HTTPException(404, "tenant_not_found")
    return registry.cases.list(tenant_id=tenant_id, limit=200)


@router.get("/admin/tenants/{tenant_id}/decisions")
def owner_tenant_decisions(
    tenant_id: str, limit: int = 100, owner=Depends(require_owner), registry=Depends(get_registry)
):
    if not registry.tenants.get(tenant_id):
        raise HTTPException(404, "tenant_not_found")
    return registry.decisions.recent(limit=limit, tenant_id=tenant_id)


@router.get("/admin/tenants/{tenant_id}/transactions")
def owner_tenant_transactions(
    tenant_id: str, limit: int = 100, owner=Depends(require_owner), registry=Depends(get_registry)
):
    if not registry.tenants.get(tenant_id):
        raise HTTPException(404, "tenant_not_found")
    return registry.transactions.list_recent(tenant_id=tenant_id, limit=limit)


@router.put("/admin/tenants/{tenant_id}")
def update_tenant(
    tenant_id: str,
    body: UpdateTenant,
    request: Request,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    patch = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if "investigator_limit" in patch:
        active = registry.investigators.count_active(tenant_id)
        if patch["investigator_limit"] < active:
            raise HTTPException(400, f"limit_below_active_investigators:{active}")
    tenant = registry.tenants.update(tenant_id, patch)
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    registry.audit.log(
        tenant_id,
        "owner",
        "tenant.updated",
        "tenant",
        tenant_id,
        getattr(request.state, "request_id", None),
        patch,
    )
    return tenant


@router.post("/admin/tenants/{tenant_id}/suspend")
def suspend_tenant(
    tenant_id: str, request: Request, owner=Depends(require_owner), registry=Depends(get_registry)
):
    tenant = registry.tenants.set_status(tenant_id, "suspended")
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    registry.audit.log(
        tenant_id,
        "owner",
        "tenant.suspended",
        "tenant",
        tenant_id,
        getattr(request.state, "request_id", None),
        {},
    )
    return tenant


@router.post("/admin/tenants/{tenant_id}/activate")
def activate_tenant(
    tenant_id: str, request: Request, owner=Depends(require_owner), registry=Depends(get_registry)
):
    tenant = registry.tenants.set_status(tenant_id, "active")
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    registry.audit.log(
        tenant_id,
        "owner",
        "tenant.activated",
        "tenant",
        tenant_id,
        getattr(request.state, "request_id", None),
        {},
    )
    return tenant


@router.post("/admin/tenants/{tenant_id}/rotate-secret")
def rotate_secret(
    tenant_id: str, request: Request, owner=Depends(require_owner), registry=Depends(get_registry)
):
    """Platform Owner ONLY — rotate BOTH the tenant's API key and HMAC secret
    atomically (old pair invalid immediately). Institution owners have NO
    rotation capability: the owner-facing /integration/rotate endpoint is
    removed. Audit logs the rotate event only — never credential values."""
    tenant = registry.tenants.rotate_integration_credentials(tenant_id)
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    registry.audit.log(
        tenant_id,
        "owner",
        "owner.integration_credentials.rotated",
        "tenant",
        tenant_id,
        getattr(request.state, "request_id", None),
        {},
    )
    return tenant


@router.put("/admin/tenants/{tenant_id}/policy")
def update_policy(
    tenant_id: str,
    body: UpdatePolicy,
    request: Request,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    patch = body.model_dump(exclude_none=True)
    note = patch.pop("note", None)  # note is version metadata, not policy content
    tenant = registry.tenants.update_policy(tenant_id, patch)
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    # Record the resulting policy as an immutable, numbered version so any past
    # decision can be traced to the exact policy row that governed it.
    version_row = None
    try:
        version_row = registry.policy_versions.add(
            tenant_id, tenant.get("policy") or {}, actor="owner", note=note, status="active"
        )
    except Exception as e:  # noqa: BLE001 — versioning failure must never break a policy update
        logger.warning("policy.version_record_failed", tenant=tenant_id, error=str(e))
    registry.audit.log(
        tenant_id,
        "owner",
        "tenant.policy_updated",
        "tenant",
        tenant_id,
        getattr(request.state, "request_id", None),
        body.model_dump(exclude_none=True),
    )
    if version_row:
        tenant = {**tenant, "policy_version": version_row["version"], "policy_hash": version_row["policy_hash"]}
    return tenant


@router.get("/admin/tenants/{tenant_id}/policy/versions")
def list_policy_versions(
    tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)
):
    if not registry.tenants.get(tenant_id):
        raise HTTPException(404, "tenant_not_found")
    return registry.policy_versions.list_for(tenant_id)


@router.get("/admin/tenants/{tenant_id}/policy/versions/{version}")
def get_policy_version(
    tenant_id: str, version: int, owner=Depends(require_owner), registry=Depends(get_registry)
):
    row = registry.policy_versions.get(tenant_id, version)
    if not row:
        raise HTTPException(404, "policy_version_not_found")
    return row


@router.post("/admin/tenants/{tenant_id}/policy/versions/{version}/activate")
def activate_policy_version(
    tenant_id: str,
    version: int,
    request: Request,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    """Materialize a stored immutable version back into tenants.policy_json —
    the decision hot path is unchanged, only the governing policy content
    (and its version stamp on future decisions) changes."""
    row = registry.policy_versions.get(tenant_id, version)
    if not row:
        raise HTTPException(404, "policy_version_not_found")
    registry.tenants.update_policy(tenant_id, dict(row["policy"]))
    registry.policy_versions.set_status(tenant_id, version, "active")
    registry.audit.log(
        tenant_id,
        "owner",
        "tenant.policy_version_activated",
        "tenant",
        tenant_id,
        getattr(request.state, "request_id", None),
        {"version": version, "policy_hash": row["policy_hash"]},
    )
    return {"ok": True, "tenant_id": tenant_id, "active_version": version}


@router.post("/admin/tenants/{tenant_id}/policy/versions/{version}/disable")
def disable_policy_version(
    tenant_id: str,
    version: int,
    request: Request,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    row = registry.policy_versions.set_status(tenant_id, version, "disabled")
    if not row:
        raise HTTPException(404, "policy_version_not_found")
    registry.audit.log(
        tenant_id,
        "owner",
        "tenant.policy_version_disabled",
        "tenant",
        tenant_id,
        getattr(request.state, "request_id", None),
        {"version": version},
    )
    return {"ok": True, "tenant_id": tenant_id, "version": version, "status": "disabled"}


@router.delete("/admin/tenants/{tenant_id}")
def delete_tenant(
    tenant_id: str, request: Request, owner=Depends(require_owner), registry=Depends(get_registry)
):
    if not registry.tenants.delete(tenant_id):
        raise HTTPException(404, "tenant_not_found")
    registry.audit.log(
        tenant_id,
        "owner",
        "tenant.deleted",
        "tenant",
        tenant_id,
        getattr(request.state, "request_id", None),
        {},
    )
    return {"ok": True, "tenant_id": tenant_id}


@router.get("/admin/overview")
def overview(owner=Depends(require_owner), registry=Depends(get_registry)):
    tenants = registry.tenants.list()
    dec = registry.decisions.overview()
    by_tenant_rows = registry.db.query(
        "SELECT tenant_id, COUNT(*) AS c FROM decisions GROUP BY tenant_id ORDER BY c DESC LIMIT 20"
    )
    dec["by_tenant"] = {r["tenant_id"]: r["c"] for r in by_tenant_rows}
    total = len(tenants)
    active = len([t for t in tenants if t["status"] == "active"])
    return {
        "server_time": datetime.now(UTC).isoformat(),
        "total_tenants": total,
        "active_tenants": active,
        "tenants": {"total": total, "active": active},
        "decisions": dec,
    }


@router.get("/admin/decisions/recent")
def decisions_recent(limit: int = 50, owner=Depends(require_owner), registry=Depends(get_registry)):
    return registry.decisions.recent(limit=limit)


@router.get("/admin/audit-verify")
def audit_verify(owner=Depends(require_owner), registry=Depends(get_registry)):
    """Verify the tamper-evident audit hash chain end-to-end.
    Legacy (pre-chain) rows are skipped; any hash gap inside the chain fails."""
    return registry.audit_repo.verify_chain()


@router.get("/admin/audit")
def audit_log(
    limit: int = 200,
    tenant_id: str | None = None,
    event_type: str | None = None,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
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


# ═══════════════════ OWNER: INVESTIGATOR MANAGEMENT (tenant-scoped) ═══════════════════


@router.get("/admin/tenants/{tenant_id}/investigators")
def list_tenant_investigators(
    tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)
):
    if not registry.tenants.get(tenant_id):
        raise HTTPException(404, "tenant_not_found")
    rows = registry.investigators.list(tenant_id=tenant_id)
    return {
        "total": len(rows),
        "investigators": rows,
        "limit": registry.tenants.get(tenant_id)["investigator_limit"],
        "used": registry.investigators.count_active(tenant_id),
    }


@router.post("/admin/tenants/{tenant_id}/investigators", status_code=201)
def create_tenant_investigator(
    tenant_id: str,
    body: CreateInvestigator,
    request: Request,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    tenant = registry.tenants.get(tenant_id)
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    active = registry.investigators.count_active(tenant_id)
    limit = tenant.get("investigator_limit", 5)
    if active >= limit:
        raise HTTPException(409, f"investigator_limit_reached:{limit}")
    if registry.investigators.get_by_email(body.email):
        raise HTTPException(409, "email_exists")
    inv = registry.investigators.create(tenant_id, body.email, body.name, body.password)
    registry.audit.log(
        tenant_id,
        "owner",
        "investigator.created",
        "investigator",
        inv["investigator_id"],
        getattr(request.state, "request_id", None),
        {"email": inv["email"], "role": "investigator"},
    )
    return inv


@router.post("/admin/tenants/{tenant_id}/investigators/{inv_id}/suspend")
def suspend_tenant_investigator(
    tenant_id: str,
    inv_id: str,
    request: Request,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    if not registry.investigators.set_status(tenant_id, inv_id, "inactive"):
        raise HTTPException(404, "investigator_not_found")
    registry.audit.log(
        tenant_id,
        "owner",
        "investigator.suspended",
        "investigator",
        inv_id,
        getattr(request.state, "request_id", None),
        {},
    )
    return {"ok": True, "investigator_id": inv_id}


@router.post("/admin/tenants/{tenant_id}/investigators/{inv_id}/activate")
def activate_tenant_investigator(
    tenant_id: str,
    inv_id: str,
    request: Request,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    if not registry.investigators.set_status(tenant_id, inv_id, "active"):
        raise HTTPException(404, "investigator_not_found")
    registry.audit.log(
        tenant_id,
        "owner",
        "investigator.activated",
        "investigator",
        inv_id,
        getattr(request.state, "request_id", None),
        {},
    )
    return {"ok": True, "investigator_id": inv_id}


@router.delete("/admin/tenants/{tenant_id}/investigators/{inv_id}")
def delete_tenant_investigator(
    tenant_id: str,
    inv_id: str,
    request: Request,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    if not registry.investigators.set_status(tenant_id, inv_id, "deleted"):
        raise HTTPException(404, "investigator_not_found")
    registry.audit.log(
        tenant_id,
        "owner",
        "investigator.deleted",
        "investigator",
        inv_id,
        getattr(request.state, "request_id", None),
        {},
    )
    return {"ok": True, "investigator_id": inv_id}


@router.get("/admin/investigators")
def list_all_investigators(owner=Depends(require_owner), registry=Depends(get_registry)):
    return {"total": registry.investigators.count(), "investigators": registry.investigators.list()}


# ═══════════════════ MERCHANT / INSTITUTION ENDPOINTS ═══════════════════
# NOTE: the legacy human "API key + secret" login (POST /admin/merchant/login)
# was REMOVED. The ONLY human sign-in to the Merchant Portal is owner
# email+password at POST /auth/institution/login. API Key / HMAC Secret remain
# strictly as INTEGRATION credentials (webhook signature verification) and are
# managed under 🔌 إعدادات الربط below — they never authenticate a person.


@router.get("/admin/merchant/me")
def merchant_me(merchant=Depends(require_merchant), registry=Depends(get_registry)):
    tenant = registry.tenants.get(merchant["tenant_id"])
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    return tenant


@router.get("/admin/merchant/dashboard")
def merchant_dashboard(merchant=Depends(require_merchant), registry=Depends(get_registry)):
    tid = merchant["tenant_id"]
    dec = registry.decisions.count_by_tenant(tid)
    recent = registry.decisions.recent(limit=10, tenant_id=tid)
    alerts = registry.alerts.list(tenant_id=tid, limit=50)
    cases = registry.cases.list(tenant_id=tid, limit=50)
    open_alerts = sum(
        1 for a in alerts if a["status"] in ("open", "assigned", "in_review", "escalated")
    )
    open_cases = sum(1 for c in cases if c["status"] != "closed")
    manual = [
        a for a in alerts if a["status"] in ("resolved_true_positive", "resolved_false_positive")
    ]
    durations, sla = [], 0
    for a in manual:
        try:
            start = datetime.fromisoformat(a["created_at"])
            end = datetime.fromisoformat(a["updated_at"])
            minutes = (end - start).total_seconds() / 60
            durations.append(minutes)
            if minutes > 1440:
                sla += 1
        except Exception:
            continue
    return {
        "tenant_id": tid,
        "decisions": dec,
        "recent": recent,
        "alerts": {
            "total": len(alerts),
            "open": open_alerts,
            "counts": {
                s: sum(1 for a in alerts if a["status"] == s)
                for s in (
                    "open",
                    "assigned",
                    "in_review",
                    "escalated",
                    "resolved_true_positive",
                    "resolved_false_positive",
                )
            },
        },
        "cases": {
            "total": len(cases),
            "open": open_cases,
            "by_status": {
                s: sum(1 for c in cases if c["status"] == s)
                for s in ("open", "in_progress", "escalated", "closed")
            },
        },
        "manual_reviews": {
            "total": len(manual),
            "avg_duration_min": round(sum(durations) / len(durations), 1) if durations else 0,
            "sla_breach_over_24h": sla,
        },
        "top_risk_reasons": _top_reasons(registry, tid),
        "connection": {
            "status": "connected",
            "aegis_core": settings.VERSION,
            "ml": bool(registry.ml_scorer and registry.ml_scorer.ready),
        },
    }


def _top_reasons(registry, tenant_id: str, limit: int = 8) -> list[dict]:
    import json as _json
    from collections import Counter

    counts = Counter()
    for row in registry.db.query(
        "SELECT top_reasons_json FROM decisions WHERE tenant_id=? ORDER BY ts DESC LIMIT 300",
        (tenant_id,),
    ):
        try:
            for item in _json.loads(row["top_reasons_json"] or "[]"):
                key = item if isinstance(item, str) else item.get("reason", str(item))
                counts[key] += 1
        except Exception:
            continue
    return [{"reason": k, "count": v} for k, v in counts.most_common(limit)]


def _mask(secret: str | None) -> str:
    """Never reveal a stored credential in a default GET — mask it."""
    return "••••••••••••••••" if secret else ""


def _verify_owner_password(registry, merchant: dict, password: str) -> None:
    """Step-up check: the JWT subject (user_id) must exist and the supplied
    password must verify against its salted hash. 401 otherwise."""
    from app.repositories.user_repo import _verify_pw  # salted+legacy verify
    user = registry.user_repo.get(merchant.get("sub", ""))
    if not user or user.get("status") != "active":
        raise HTTPException(401, "reauth_required")
    if not _verify_pw(password, user):
        raise HTTPException(401, "invalid_credentials")


@router.get("/admin/merchant/integration")
def merchant_integration(merchant=Depends(require_merchant), registry=Depends(get_registry)):
    """Integration settings — secrets are MASKED by default. Use
    POST /admin/merchant/integration/reveal (password step-up) to view them."""
    tenant = registry.tenants.get(merchant["tenant_id"], reveal=True)
    endpoint = f"{settings.PUBLIC_URL}/api/v1/wallet/webhook"
    return {
        "tenant_id": tenant["tenant_id"],
        "endpoint": endpoint,
        "api_key": _mask(tenant["api_key"]),
        "hmac_secret": _mask(tenant["hmac_secret"]),
        "credentials_masked": True,
        "headers": {
            "X-API-Key": "<API_KEY>",
            "X-Wallet-Signature": "HMAC_SHA256(body, hmac_secret)",
        },
        "curl": f"curl -X POST '{endpoint}' -H 'Content-Type: application/json' "
        f"-H 'X-API-Key: <API_KEY>' "
        f"-H 'X-Wallet-Signature: <signature>' "
        f'-d \'{{"transaction":{{"amount":100,"sender_account_id":"acct_1","beneficiary_account_id":"acct_2"}}}}\'',
        "python": "import hmac,hashlib; sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()",
        "node": "const sig = crypto.createHmac('sha256', secret).update(body).digest('hex')",
        "code_samples": {
            "curl": (
                'BODY=\'{"transaction":{"tx_id":"tx-1","amount":100,'
                '"sender_account_id":"acct_1","beneficiary_account_id":"acct_2"}}\'\n'
                f"SIG=$(printf '%s' \"$BODY\" | openssl dgst -sha256 -hmac \"<HMAC_SECRET>\" | awk '{{print $2}}')\n"
                f"curl -X POST '{endpoint}' \\\n"
                "  -H 'Content-Type: application/json' \\\n"
                "  -H 'X-API-Key: <API_KEY>' \\\n"
                '  -H "x-wallet-signature: $SIG" \\\n'
                '  -d "$BODY"'
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
                "    'X-API-Key': '<API_KEY>', 'x-wallet-signature': sig },\n"
                "  body\n"
                "});\n"
                "const { decision, risk_score, reasoning_ar } = await r.json();"
            ),
            "python": (
                "import hmac, hashlib, json, requests\n"
                'body = json.dumps({"transaction": {"tx_id": "tx-1", "amount": 100,\n'
                '  "sender_account_id": "acct_1", "beneficiary_account_id": "acct_2"}}, separators=(",", ":"))\n'
                "sig = hmac.new(b'<HMAC_SECRET>', body.encode(), hashlib.sha256).hexdigest()\n"
                f"r = requests.post('{endpoint}', data=body, headers={{\n"
                "  'Content-Type': 'application/json', 'X-API-Key': '<API_KEY>',\n"
                "  'x-wallet-signature': sig})\n"
                "print(r.json())"
            ),
        },
    }


@router.post("/admin/merchant/integration/reveal")
def merchant_reveal_credentials(
    body: OwnerPasswordConfirm, request: Request,
    merchant=Depends(require_merchant), registry=Depends(get_registry),
):
    """Step-up: reveal this tenant's integration credentials after verifying
    the owner's password server-side. Audit logs the VIEW event only — never
    the credential values."""
    _verify_owner_password(registry, merchant, body.password)
    tenant = registry.tenants.get(merchant["tenant_id"], reveal=True)
    registry.audit.log(
        merchant["tenant_id"], merchant.get("sub", ""),
        "owner.integration_credentials.viewed", "tenant", merchant["tenant_id"],
        getattr(request.state, "request_id", None), {},
    )
    return {"tenant_id": tenant["tenant_id"], "api_key": tenant["api_key"],
            "hmac_secret": tenant["hmac_secret"], "credentials_masked": False}


# NOTE: institution-owner credential rotation was REMOVED — rotation is a
# Platform Owner capability only (see POST /admin/tenants/{id}/rotate-secret).
# An institution owner calling any rotation path gets 404/403 and no change.


@router.post("/admin/merchant/change-password")
def merchant_change_password(
    body: ChangeOwnerPassword, request: Request,
    merchant=Depends(require_merchant), registry=Depends(get_registry),
):
    """Change the institution owner's password. Verifies the CURRENT password
    server-side, sets a fresh per-user salt + hash, and bumps
    tokens_valid_after so every OTHER session is revoked (this one stays alive
    until its natural expiry — the standard post-rotation behavior)."""
    _verify_owner_password(registry, merchant, body.current_password)
    registry.user_repo.set_password(merchant["sub"], body.new_password)
    registry.audit.log(
        merchant["tenant_id"], merchant.get("sub", ""),
        "owner.password_changed", "user", merchant["sub"],
        getattr(request.state, "request_id", None), {},
    )
    return {"changed": True, "message": "تم تغيير كلمة المرور. سجّل الدخول مجددًا على أجهزتك الأخرى."}


@router.get("/admin/merchant/connection-status")
def merchant_connection(merchant=Depends(require_merchant), registry=Depends(get_registry)):
    ml_ready = registry.ml_scorer.ready if registry.ml_scorer else False
    tenant = registry.tenants.get(merchant["tenant_id"])
    now = datetime.now(UTC).isoformat()
    return {
        "tenant_id": merchant["tenant_id"],
        "api": True,
        "database": True,
        "ml": ml_ready,
        "graph": True,
        "tenant_status": tenant.get("status", "unknown") if tenant else "unknown",
        "connected": bool(tenant and tenant.get("status") == "active"),
        "aegis_core": settings.VERSION,
        "ai_agent": "ready"
        if settings.openrouter_keys and settings.AI_ENABLED
        else "not_configured",
        "checked_at": now,
    }


@router.get("/admin/merchant/stats")
def merchant_stats(merchant=Depends(require_merchant), registry=Depends(get_registry)):
    return registry.decisions.count_by_tenant(merchant["tenant_id"])


@router.get("/admin/merchant/decisions")
def merchant_decisions(
    limit: int = 50,
    decision: str | None = None,
    merchant=Depends(require_merchant),
    registry=Depends(get_registry),
):
    if decision:
        return registry.db.query(
            "SELECT * FROM decisions WHERE tenant_id=? AND decision=? ORDER BY ts DESC LIMIT ?",
            (merchant["tenant_id"], decision, limit),
        )
    return registry.decisions.recent(limit=limit, tenant_id=merchant["tenant_id"])


@router.get("/admin/merchant/transactions")
def merchant_transactions(
    limit: int = 100, merchant=Depends(require_merchant), registry=Depends(get_registry)
):
    return registry.transactions.list_recent(tenant_id=merchant["tenant_id"], limit=limit)


@router.get("/admin/merchant/alerts")
def merchant_alerts(
    status: str | None = None, merchant=Depends(require_merchant), registry=Depends(get_registry)
):
    return registry.alerts.list(tenant_id=merchant["tenant_id"], status=status)


@router.get("/admin/merchant/cases")
def merchant_cases(merchant=Depends(require_merchant), registry=Depends(get_registry)):
    return registry.cases.list(tenant_id=merchant["tenant_id"])


@router.get("/admin/merchant/manual-reviews")
def merchant_manual_reviews(merchant=Depends(require_merchant), registry=Depends(get_registry)):
    """Manually-processed transactions — reviewer identity, actor_type (stored
    EXPLICITLY in alert notes, never inferred from email), timings, resolution."""
    import json as _json

    rows = registry.db.query(
        "SELECT a.alert_id, a.tenant_id, a.tx_id, a.severity, a.title, a.status, "
        "a.assignee, a.created_at, a.updated_at, a.resolution, a.notes_json, "
        "t.amount, t.currency, d.decision "
        "FROM alerts a LEFT JOIN transactions t ON t.tx_id = a.tx_id "
        "LEFT JOIN decisions d ON d.tx_id = a.tx_id "
        "WHERE a.tenant_id=? AND a.status IN ('resolved_true_positive','resolved_false_positive') "
        "ORDER BY a.updated_at DESC LIMIT 200",
        (merchant["tenant_id"],),
    )
    for r in rows:
        try:
            dur = (
                datetime.fromisoformat(r["updated_at"]) - datetime.fromisoformat(r["created_at"])
            ).total_seconds() / 60
            r["review_duration_min"] = round(dur, 1)
        except Exception:
            r["review_duration_min"] = None
        notes = []
        try:
            notes = _json.loads(r.pop("notes_json", "[]") or "[]")
        except Exception:
            notes = []
        r["notes"] = notes
        r["actor_type"] = "system"
        r["decided_by"] = None
        if notes:
            last = notes[-1]
            r["decided_by"] = last.get("author")
            r["actor_type"] = last.get("actor_type") or "investigator"
        else:
            r["decided_by"] = r.get("assignee")
            r["actor_type"] = "investigator" if r.get("assignee") else "system"
        r["processed_at"] = r["updated_at"]
        r["assigned_to"] = r.get("assignee")
    return rows


@router.get("/admin/merchant/audit")
def merchant_audit(
    limit: int = 200, merchant=Depends(require_merchant), registry=Depends(get_registry)
):
    return registry.audit_repo.list(tenant_id=merchant["tenant_id"], limit=limit)


@router.get("/admin/merchant/investigators")
def merchant_investigators(merchant=Depends(require_merchant), registry=Depends(get_registry)):
    tid = merchant["tenant_id"]
    rows = registry.investigators.list(tenant_id=tid)
    tenant = registry.tenants.get(tid)
    return {
        "total": len(rows),
        "investigators": rows,
        "limit": tenant.get("investigator_limit", 5) if tenant else 5,
        "used": registry.investigators.count_active(tid),
    }


@router.post("/admin/merchant/investigators", status_code=201)
def merchant_create_investigator(
    body: CreateInvestigator,
    request: Request,
    merchant=Depends(require_merchant),
    registry=Depends(get_registry),
):
    """Institution Owner creates an investigator for OWN institution (limit enforced)."""
    tid = merchant["tenant_id"]
    tenant = registry.tenants.get(tid)
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    if merchant.get("role") not in ("merchant", "institution_owner", "tenant_admin"):
        raise HTTPException(403, "insufficient_role")
    active = registry.investigators.count_active(tid)
    limit = tenant.get("investigator_limit", 5)
    if active >= limit:
        raise HTTPException(409, f"investigator_limit_reached:{limit}")
    if registry.investigators.get_by_email(body.email):
        raise HTTPException(409, "email_exists")
    inv = registry.investigators.create(tid, body.email, body.name, body.password)
    registry.audit.log(
        tid,
        merchant.get("sub", merchant.get("name", "institution_owner")),
        "investigator.created",
        "investigator",
        inv["investigator_id"],
        getattr(request.state, "request_id", None),
        {"email": inv["email"], "actor_type": merchant.get("role")},
    )
    return inv


def _inv_action(investigator_id: str, action: str, merchant, request, registry, status_value: str):
    tid = merchant["tenant_id"]
    if not registry.investigators.set_status(tid, investigator_id, status_value):
        raise HTTPException(404, "investigator_not_found")
    registry.audit.log(
        tid,
        merchant.get("sub", merchant.get("name", "institution_owner")),
        f"investigator.{action}",
        "investigator",
        investigator_id,
        getattr(request.state, "request_id", None),
        {"actor_type": merchant.get("role")},
    )
    return {"ok": True, "investigator_id": investigator_id}


@router.post("/admin/merchant/investigators/{inv_id}/suspend")
def merchant_suspend_investigator(
    inv_id: str,
    request: Request,
    merchant=Depends(require_merchant),
    registry=Depends(get_registry),
):
    return _inv_action(inv_id, "suspended", merchant, request, registry, "inactive")


@router.post("/admin/merchant/investigators/{inv_id}/activate")
def merchant_activate_investigator(
    inv_id: str,
    request: Request,
    merchant=Depends(require_merchant),
    registry=Depends(get_registry),
):
    return _inv_action(inv_id, "activated", merchant, request, registry, "active")


@router.delete("/admin/merchant/investigators/{inv_id}")
def merchant_delete_investigator(
    inv_id: str,
    request: Request,
    merchant=Depends(require_merchant),
    registry=Depends(get_registry),
):
    return _inv_action(inv_id, "deleted", merchant, request, registry, "deleted")


@router.post("/admin/merchant/investigators/{inv_id}/reset-password")
def merchant_reset_password(
    inv_id: str,
    body: ResetPassword,
    request: Request,
    merchant=Depends(require_merchant),
    registry=Depends(get_registry),
):
    tid = merchant["tenant_id"]
    if not registry.investigators.reset_password(tid, inv_id, body.password):
        raise HTTPException(404, "investigator_not_found")
    registry.audit.log(
        tid,
        merchant.get("sub", merchant.get("name", "institution_owner")),
        "investigator.password_reset",
        "investigator",
        inv_id,
        getattr(request.state, "request_id", None),
        {"actor_type": merchant.get("role")},
    )
    return {"ok": True, "investigator_id": inv_id}


# ═══════════════════ MERCHANT: UNIFIED TRANSACTION FEED (backend filters + real counts) ═══════════════════


@router.get("/admin/merchant/feed")
def merchant_feed(
    filter: str = "all",
    limit: int = 300,
    merchant=Depends(require_merchant),
    registry=Depends(get_registry),
):
    """One endpoint for the transaction tabs. Filters are applied by the BACKEND;
    counts are real numbers from the DB — never client-side hardcoded."""
    import json as _json

    valid = {"all", "pending", "manual", "auto_allow", "needs_review", "blocked", "live"}
    if filter not in valid:
        raise HTTPException(400, f"invalid_filter:{filter}")
    rows = registry.db.query(
        "SELECT d.decision_id, d.tx_id, d.ts AS decision_ts, d.decision,"
        " d.risk_score, d.risk_band, d.typology, d.reasoning_ar, d.ai_model,"
        " t.amount, t.currency, t.sender_account_id, t.beneficiary_account_id,"
        " t.ts AS tx_ts, a.alert_id, a.status AS alert_status, a.assignee,"
        " a.created_at AS alert_created_at, a.updated_at AS alert_updated_at,"
        " a.resolution, a.notes_json"
        " FROM decisions d JOIN transactions t ON t.tx_id = d.tx_id"
        " LEFT JOIN alerts a ON a.tx_id = d.tx_id AND a.tenant_id = d.tenant_id"
        " WHERE d.tenant_id=? ORDER BY d.ts DESC LIMIT ?",
        (merchant["tenant_id"], limit),
    )
    for r in rows:
        try:
            r["notes"] = _json.loads(r.pop("notes_json", "[]") or "[]")
        except Exception:
            r["notes"] = []
    pend = [
        r
        for r in rows
        if r["decision"] == "review" and not (r["alert_status"] or "").startswith("resolved")
    ]
    manual = [r for r in rows if (r["alert_status"] or "").startswith("resolved")]
    auto_allow = [r for r in rows if r["decision"] == "allow"]
    needs_review = [r for r in rows if r["decision"] in ("review", "challenge")]
    blocked = [r for r in rows if r["decision"] == "block"]
    live = [r for r in rows if r["decision"] in ("review", "challenge")]
    sets = {
        "all": rows,
        "pending": pend,
        "manual": manual,
        "auto_allow": auto_allow,
        "needs_review": needs_review,
        "blocked": blocked,
        "live": live,
    }
    return {
        "tenant_id": merchant["tenant_id"],
        "filter": filter,
        "counts": {k: len(v) for k, v in sets.items()},
        "transactions": sets[filter],
    }


class OwnerReviewDecision(BaseModel):
    decision: str = Field(pattern="^(allow|deny)$")
    note: str = ""


@router.post("/admin/merchant/reviews/{alert_id}/decision")
def merchant_owner_review(
    alert_id: str,
    body: OwnerReviewDecision,
    request: Request,
    merchant=Depends(require_merchant),
    registry=Depends(get_registry),
):
    """Institution Owner manually processes a pending review — actor_type=institution_owner.
    allow -> resolved_false_positive (not fraud), deny -> resolved_true_positive (fraud)."""
    tid = merchant["tenant_id"]
    alert = registry.db.query_one(
        "SELECT * FROM alerts WHERE alert_id=? AND tenant_id=?", (alert_id, tid)
    )
    if not alert:
        raise HTTPException(404, "alert_not_found")
    actor = merchant.get("name") or merchant.get("sub", "institution_owner")
    if not (alert["status"] or "open").startswith("resolved"):
        new_status = (
            "resolved_true_positive" if body.decision == "deny" else "resolved_false_positive"
        )
        registry.alerts.resolve(
            alert_id, new_status, body.note, author=actor, actor_type="institution_owner"
        )
    registry.audit.log(
        tid,
        actor,
        "alert.owner_decision",
        "alert",
        alert_id,
        getattr(request.state, "request_id", None),
        {
            "decision": body.decision,
            "actor_type": merchant.get("role", "institution_owner"),
            "tx_id": alert["tx_id"],
        },
    )
    return {
        "ok": True,
        "alert_id": alert_id,
        "tx_id": alert["tx_id"],
        "decision": body.decision,
        "actor": actor,
        "actor_type": "institution_owner",
    }


# ═══════════════════ OWNER: RESET INVESTIGATOR PASSWORD (was missing on owner path) ═══════════════════


@router.post("/admin/tenants/{tenant_id}/investigators/{inv_id}/reset-password")
def owner_reset_investigator_password(
    tenant_id: str,
    inv_id: str,
    body: ResetPassword,
    request: Request,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    if not registry.tenants.get(tenant_id):
        raise HTTPException(404, "tenant_not_found")
    if not registry.investigators.reset_password(tenant_id, inv_id, body.password):
        raise HTTPException(404, "investigator_not_found")
    registry.audit.log(
        tenant_id,
        "owner",
        "investigator.password_reset",
        "investigator",
        inv_id,
        getattr(request.state, "request_id", None),
        {"actor_type": "owner"},
    )
    return {"ok": True, "investigator_id": inv_id}
