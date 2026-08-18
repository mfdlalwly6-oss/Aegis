"""Authentication — platform-level demo login + merchant JWT issued via /admin/merchant/login.
NOTE: the admin user here is a development convenience. Merchant auth is the production path.
"""
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from jose import jwt
from pydantic import BaseModel, Field

from app.core.config import settings

router = APIRouter()


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
