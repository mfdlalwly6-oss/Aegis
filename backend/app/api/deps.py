"""Shared FastAPI dependencies:
- get_registry: access the live service registry
- require_owner: AEGIS Owner (platform token)
- require_merchant: Institution owner/merchant (JWT, tenant-scoped, active status enforced)
- require_investigator: Institution investigator (JWT, tenant-scoped, active status enforced)

Server-side session revocation (migration 031): for interactive institution
principals (institution_owner / tenant_admin) every request re-checks the
user row — status must be 'active' AND the JWT's `iat` must be >=
`tokens_valid_after`. Disabling an account or resetting/changing its password
bumps `tokens_valid_after`, so all previously-issued tokens die instantly,
without a session table or a per-token denylist.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request
from jose import jwt

from app.core.config import settings


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


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
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except Exception:
        return None


def require_owner(request: Request) -> str:
    """AEGIS Owner — Bearer token header OR legacy X-Owner-Token header."""
    token = _bearer(request)
    if token and token == settings.OWNER_TOKEN:
        reg = get_registry(request)
        if reg is not None and getattr(reg, "db", None) is not None:
            reg.db.set_tenant("platform")
        return token
    x = request.headers.get("X-Owner-Token", "")
    if x and x == settings.OWNER_TOKEN:
        reg = get_registry(request)
        if reg is not None and getattr(reg, "db", None) is not None:
            reg.db.set_tenant("platform")
        return x
    raise HTTPException(401, "owner_token_required")


def require_merchant(request: Request, registry=Depends(get_registry)) -> dict:
    """Institution (merchant/owner/admin) — JWT roles: merchant (API key),
    institution_owner, tenant_admin. Must carry tenant_id; suspended tenants
    are hard-blocked here, on every request. Interactive principals
    (institution_owner / tenant_admin) additionally pass the revocation gate:
    account active + iat >= tokens_valid_after."""
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
    # Server-side revocation gate — interactive institution principals only
    # (the legacy `merchant` API-key role has no user row and is governed by
    # secret rotation instead; see tenant_repo.rotate_secret).
    if claims.get("role") in ("institution_owner", "tenant_admin") and getattr(registry, "user_repo", None) is not None:
        user = registry.user_repo.get(claims.get("sub", ""))
        if not user or user.get("status") != "active":
            raise HTTPException(401, "account_revoked")
        floor = _parse_ts(user.get("tokens_valid_after"))
        iat = claims.get("iat")
        if floor is not None and iat is not None:
            # Standard not-before gate at whole-second granularity (JWT `iat`
            # is an int of seconds): revoke when the token predates the floor.
            #   - token issued BEFORE the bump   → iat <  floor → revoked ✓
            #   - fresh login AFTER reset/enable  → iat >= floor → valid ✓
            #     (this is what makes reset→immediate-login work)
            #   - known, documented edge: a token minted in the SAME second as
            #     the revocation bump survives — a ≤1s ambiguity window, the
            #     industry-standard trade-off for timestamp-based revocation.
            #   Disable is additionally enforced by the status='active' check
            #   above, which has no such window.
            if int(iat) < int(floor.timestamp()):
                raise HTTPException(401, "token_revoked")
    if getattr(registry, "db", None) is not None:
        registry.db.set_tenant(tid)
    return claims


def require_investigator(request: Request, registry=Depends(get_registry)) -> dict:
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
    if getattr(registry, "db", None) is not None:
        registry.db.set_tenant(tid)
    return claims
