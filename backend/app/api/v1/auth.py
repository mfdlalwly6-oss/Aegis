"""Authentication — platform demo login (dev), merchant JWT, and institution-owner login."""
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from pydantic import BaseModel, Field

from app.api.deps import get_registry
from app.core.config import settings
from app.security import issue_jwt

router = APIRouter()

INSTITUTION_OWNER_ROLES = {"institution_owner", "tenant_admin"}


def _hash(password: str) -> str:
    salt = settings.SECRET_KEY[:16].encode()
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000).hex()


_DEMO_USER = "admin@aegis.local"
_DEMO_PASSWORD = "ChangeMe!2026"


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class TokenPair(BaseModel):
    access_token: str
    token_type: str = "Bearer"


def _issue(sub: str, role: str, ttl: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": sub, "role": role,
               "iat": int(now.timestamp()),
               "exp": int((now + timedelta(seconds=ttl)).timestamp())}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@router.post("/login", response_model=TokenPair)
async def login(body: LoginBody) -> TokenPair:
    if body.email != _DEMO_USER or not hmac.compare_digest(_hash(body.password), _hash(_DEMO_PASSWORD)):
        raise HTTPException(401, "invalid_credentials")
    return TokenPair(access_token=_issue(_DEMO_USER, "admin", settings.JWT_ACCESS_TTL_SEC))


@router.post("/institution/login")
def institution_login(body: LoginBody, request: "Request", registry=Depends(get_registry)):
    """Institution Owner login — email/password → tenant-scoped JWT."""
    user = registry.user_repo.authenticate_global(body.email, body.password)
    if not user:
        registry.audit.log(None, body.email[:12], "authentication.failure",
                           "institution_login", None,
                           getattr(request.state, "request_id", None), {})
        raise HTTPException(401, "invalid_credentials")
    if user["role"] not in INSTITUTION_OWNER_ROLES:
        raise HTTPException(403, "role_not_allowed")
    tenant = registry.tenants.get(user["tenant_id"])
    if not tenant:
        raise HTTPException(404, "tenant_not_found")
    if tenant.get("status") != "active":
        registry.audit.log(tenant["tenant_id"], user["email"], "authentication.failure",
                           "institution_login", tenant["tenant_id"],
                           getattr(request.state, "request_id", None),
                           {"reason": "tenant_not_active"})
        raise HTTPException(403, "tenant_not_active")
    token = issue_jwt(user["user_id"], user["role"], settings.MERCHANT_JWT_TTL_SEC,
                      {"tenant_id": user["tenant_id"], "tenant_name": tenant["name"],
                       "name": user["name"]})
    registry.audit.log(user["tenant_id"], user["email"], "authentication.success",
                       "institution_login", user["tenant_id"],
                       getattr(request.state, "request_id", None), {})
    return {"access_token": token, "token_type": "Bearer",
            "user": {"user_id": user["user_id"], "email": user["email"],
                     "name": user["name"], "role": user["role"],
                     "tenant_id": user["tenant_id"], "tenant_name": tenant["name"]}}
