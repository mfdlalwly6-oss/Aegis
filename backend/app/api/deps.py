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


def require_investigator(
    authorization: str = Header(default=""),
    token: str = Query(default=""),
) -> dict:
    """Investigator portal guard — JWT with role='investigator' only.
    `token` query param is accepted because EventSource (SSE) cannot set headers.
    """
    raw = authorization.replace("Bearer ", "") if authorization else token
    if not raw:
        raise HTTPException(401, "investigator_auth_required")
    try:
        data = decode_jwt(raw)
    except Exception:
        raise HTTPException(401, "invalid_token")
    if data.get("role") != "investigator":
        raise HTTPException(403, "investigator_role_required")
    return data


def require_owner_or_investigator(
    request: Request,
    x_owner_token: str = Header(default=""),
    owner_token: str = Query(default=""),
    authorization: str = Header(default=""),
) -> dict:
    """Accepts either a valid owner token or an investigator JWT.
    Returns {"actor": ..., "role": "owner"|"investigator"}.
    """
    token = x_owner_token or owner_token
    if token and compare_owner_token(token):
        return {"actor": "owner", "role": "owner", "sub": "owner"}
    if authorization:
        raw = authorization.replace("Bearer ", "")
        try:
            data = decode_jwt(raw)
        except Exception:
            data = None
        if data and data.get("role") == "investigator":
            return {"actor": data.get("sub", "investigator"), "role": "investigator",
                    "sub": data.get("sub", "investigator")}
    raise HTTPException(401, "auth_required")
