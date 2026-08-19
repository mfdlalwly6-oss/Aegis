"""Shared FastAPI dependencies:
- get_registry: access the live service registry
- require_owner: AEGIS Owner (platform token)
- require_merchant: Institution owner/merchant (JWT, tenant-scoped, active status enforced)
- require_investigator: Institution investigator (JWT, tenant-scoped, active status enforced)
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from jose import jwt

from app.core.config import settings


def get_registry(request: Request):
    return getattr(request.app.state, "registry", None)


def _bearer(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]
    return ""


def _decode(token: str) -> dict | None:
    if not token:
        return None
    try:
        return jwt.decode(token, settings.SECRET_KEY,
                          algorithms=[settings.JWT_ALGORITHM])
    except Exception:
        return None


def require_owner(request: Request) -> str:
    """AEGIS Owner — Bearer token header OR legacy X-Owner-Token header."""
    token = _bearer(request)
    if token and token == settings.OWNER_TOKEN:
        return token
    x = request.headers.get("X-Owner-Token", "")
    if x and x == settings.OWNER_TOKEN:
        return x
    raise HTTPException(401, "owner_token_required")


def require_merchant(request: Request,
                     registry=Depends(get_registry)) -> dict:
    """Institution (merchant/owner/admin) — JWT roles: merchant (API key),
    institution_owner, tenant_admin. Must carry tenant_id; suspended tenants
    are hard-blocked here, on every request."""
    claims = _decode(_bearer(request))
    if not claims or claims.get("role") not in ("merchant", "institution_owner", "tenant_admin"):
        raise HTTPException(401, "invalid_token")
    tid = claims.get("tenant_id")
    if not tid:
        raise HTTPException(401, "missing_tenant")
    tenant = registry.tenants.get(tid)
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    if tenant.get("status") != "active":
        raise HTTPException(403, "tenant_suspended")
    return claims


def require_investigator(request: Request,
                         registry=Depends(get_registry)) -> dict:
    """Institution investigator — JWT role=investigator, tenant_id claim,
    active account, belonging to the claimed tenant."""
    claims = _decode(_bearer(request))
    if not claims or claims.get("role") != "investigator":
        raise HTTPException(401, "invalid_token")
    tid = claims.get("tenant_id")
    if not tid or tid == "platform":
        raise HTTPException(403, "investigator_not_tenant_scoped")
    inv = registry.investigators.get_by_email(claims.get("sub", ""))
    if not inv:
        raise HTTPException(401, "investigator_missing")
    if inv.get("status") != "active":
        raise HTTPException(401, "investigator_inactive")
    if inv.get("tenant_id") != tid:
        raise HTTPException(403, "tenant_mismatch")
    return claims
