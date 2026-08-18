"""Shared API dependencies — auth guards + registry accessor."""
from __future__ import annotations

from fastapi import Header, HTTPException, Query, Request

from app.security import compare_owner_token, decode_jwt


def get_registry(request: Request):
    return request.app.state.registry


def require_owner(
    x_owner_token: str = Header(default=""),
    owner_token: str = Query(default=""),
) -> str:
    token = x_owner_token or owner_token
    if not token or not compare_owner_token(token):
        raise HTTPException(401, "owner_auth_required")
    return token


def require_merchant(
    authorization: str = Header(default=""),
) -> dict:
    if not authorization:
        raise HTTPException(401, "merchant_auth_required")
    raw = authorization.replace("Bearer ", "")
    try:
        data = decode_jwt(raw)
    except Exception:
        raise HTTPException(401, "invalid_token")
    if data.get("role") not in ("merchant", "tenant_admin", "analyst", "investigator", "viewer"):
        raise HTTPException(403, "merchant_role_required")
    return data


def require_analyst_or_above(merchant: dict = None) -> dict:
    if merchant and merchant.get("role") in ("merchant", "tenant_admin", "analyst", "investigator"):
        return merchant
    raise HTTPException(403, "insufficient_role")
