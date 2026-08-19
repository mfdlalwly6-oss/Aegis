"""Security primitives — HMAC verification, JWT issuing/verification, key generation."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.config import settings


def generate_api_key() -> str:
    return "aeg_pk_" + secrets.token_urlsafe(24)


def generate_hmac_secret() -> str:
    return "aeg_sk_" + secrets.token_urlsafe(36)


def generate_tenant_id() -> str:
    return "tnt_" + secrets.token_hex(8)


def generate_id(prefix: str) -> str:
    return f"{prefix}_" + secrets.token_hex(10)


def verify_signature(secret: str, raw_body: bytes, provided: str) -> bool:
    """Constant-time HMAC-SHA256 verification. provided may be hex or 'sha256=hex'."""
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = provided.removeprefix("sha256=").strip().lower()
    return hmac.compare_digest(expected, provided)


def verify_api_key_secret(api_secret_plain: str, secret_stored: str) -> bool:
    return hmac.compare_digest(api_secret_plain, secret_stored)


def issue_jwt(subject: str, role: str, ttl_sec: int, extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_sec)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_jwt(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def compare_owner_token(token: str) -> bool:
    return hmac.compare_digest(token, settings.OWNER_TOKEN)
