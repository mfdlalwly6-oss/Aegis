"""Authentication — platform admin login (users table), merchant JWT, and institution-owner login."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from jose import jwt
from pydantic import BaseModel, Field

from app.api.deps import get_registry
from app.core.config import settings
from app.security import issue_jwt

router = APIRouter()

INSTITUTION_OWNER_ROLES = {"institution_owner", "tenant_admin"}


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class TokenPair(BaseModel):
    access_token: str
    token_type: str = "Bearer"


def _issue(sub: str, role: str, ttl: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@router.post("/login", response_model=TokenPair)
async def login(body: LoginBody, registry=Depends(get_registry)) -> TokenPair:
    """Platform admin login — authenticated against the users table.

    No hardcoded credentials. Bootstrap an admin via
    AEGIS_PLATFORM_ADMIN_EMAIL / AEGIS_PLATFORM_ADMIN_PASSWORD.
    """
    # Pre-auth runs in platform scope: reset pooled connection GUC before any
    # DB work (same stale-GUC hazard documented in webhook.py).
    registry.db.set_tenant("platform")
    user = registry.user_repo.authenticate_global(body.email, body.password)
    if not user or user.get("role") != "admin":
        raise HTTPException(401, "invalid_credentials")
    return TokenPair(access_token=_issue(user["email"], "admin", settings.JWT_ACCESS_TTL_SEC))


@router.post("/institution/login")
def institution_login(body: LoginBody, request: "Request", registry=Depends(get_registry)):
    """Institution Owner login — email/password → tenant-scoped JWT."""
    # Pre-auth runs in platform scope: reset pooled connection GUC before the
    # global user lookup + audit insert (audit_log RLS is platform-scoped).
    registry.db.set_tenant("platform")
    user = registry.user_repo.authenticate_global(body.email, body.password)
    if not user:
        registry.audit.log(
            None,
            body.email[:12],
            "authentication.failure",
            "institution_login",
            None,
            getattr(request.state, "request_id", None),
            {},
        )
        raise HTTPException(401, "invalid_credentials")
    if user["role"] not in INSTITUTION_OWNER_ROLES:
        raise HTTPException(403, "role_not_allowed")
    tenant = registry.tenants.get(user["tenant_id"])
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    if tenant.get("status") != "active":
        registry.audit.log(
            tenant["tenant_id"],
            user["email"],
            "authentication.failure",
            "institution_login",
            tenant["tenant_id"],
            getattr(request.state, "request_id", None),
            {"reason": "tenant_not_active"},
        )
        raise HTTPException(403, "tenant_not_active")
    token = issue_jwt(
        user["user_id"],
        user["role"],
        settings.MERCHANT_JWT_TTL_SEC,
        {"tenant_id": user["tenant_id"], "tenant_name": tenant["name"], "name": user["name"]},
    )
    registry.audit.log(
        user["tenant_id"],
        user["email"],
        "authentication.success",
        "institution_login",
        user["tenant_id"],
        getattr(request.state, "request_id", None),
        {},
    )
    return {
        "access_token": token,
        "token_type": "Bearer",
        "user": {
            "user_id": user["user_id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "tenant_id": user["tenant_id"],
            "tenant_name": tenant["name"],
        },
    }
