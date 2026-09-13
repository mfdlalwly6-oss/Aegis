"""Authentication — platform admin login (users table), merchant JWT, and institution-owner login."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from jose import jwt
from pydantic import BaseModel, Field

from app.api.deps import get_registry
from app.core.config import settings
from app.security import issue_jwt

router = APIRouter()


# ────────────────────────── invitation / reset payload models ──────────────
class AcceptInvitationBody(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class ForgotPasswordBody(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class ResetPasswordBody(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=8, max_length=200)

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
        # Generic failure — also covers non-active accounts (invited/disabled).
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
    # Explicit lifecycle guard (defense-in-depth on top of the status filter):
    # an INVITED owner must accept the invitation first; a DISABLED account
    # cannot log in until re-enabled. Never reveal which case it was.
    if user.get("status") != "active":
        registry.audit.log(
            user["tenant_id"], user["email"], "authentication.failure", "institution_login",
            user["tenant_id"], getattr(request.state, "request_id", None),
            {"reason": "account_not_active"},
        )
        raise HTTPException(401, "invalid_credentials")
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


# ═══════════════════ INSTITUTION INVITATION LIFECYCLE ═══════════════════

@router.get("/institution/invitation")
def peek_invitation(token: str, registry=Depends(get_registry)):
    """Preview an invitation (no consumption). Powers the accept page states:
    valid | invalid | expired | revoked | used."""
    registry.db.set_tenant("platform")
    verdict, inv = registry.invitations.peek(token)
    if verdict != "valid" or not inv:
        return {"status": verdict}
    tenant = registry.tenants.get(inv["tenant_id"])
    return {
        "status": "valid",
        "email": inv["email"],
        "tenant_name": (tenant or {}).get("name", inv["tenant_id"]),
        "expires_at": inv["expires_at"],
    }


@router.post("/institution/accept-invitation")
def accept_invitation(body: AcceptInvitationBody, request: Request, registry=Depends(get_registry)):
    """Consume the invitation: verify token/expiry/revocation/single-use, set the
    owner password, activate the account, mark the invitation accepted, audit."""
    registry.db.set_tenant("platform")
    verdict, inv = registry.invitations.consume(body.token)
    if verdict != "valid" or not inv:
        raise HTTPException(410, f"invitation_{verdict}")
    tenant = registry.tenants.get(inv["tenant_id"])
    if not tenant or tenant.get("status") != "active":
        raise HTTPException(403, "tenant_not_active")
    user = registry.user_repo.get(inv["user_id"])
    if not user:
        raise HTTPException(404, "owner_not_found")
    registry.user_repo.set_password(user["user_id"], body.password)
    registry.user_repo.set_status(user["user_id"], "active")
    registry.audit.log(
        inv["tenant_id"], user["email"], "owner.invitation_accepted", "user",
        user["user_id"], getattr(request.state, "request_id", None), {},
    )
    return {"activated": True, "message": "تم تفعيل حسابك بنجاح. يمكنك الآن تسجيل الدخول."}


# ═══════════════════ PASSWORD RESET (forgot-password) ═══════════════════

@router.post("/institution/forgot-password")
def forgot_password(body: ForgotPasswordBody, request: Request, registry=Depends(get_registry)):
    """Generic 200 always — never reveals whether the email exists."""
    registry.db.set_tenant("platform")
    user = registry.user_repo.find_global_by_email_any_status(body.email)
    if user and user.get("status") == "active" and user.get("role") in INSTITUTION_OWNER_ROLES:
        tenant = registry.tenants.get(user["tenant_id"])
        if tenant and tenant.get("status") == "active":
            _row, raw = registry.invitations.create_reset(
                user["tenant_id"], user["user_id"], user["email"],
                ttl_hours=settings.RESET_TOKEN_TTL_HOURS,
            )
            registry.email.send_password_reset(
                to=user["email"], tenant_name=tenant["name"], token=raw,
            )
            registry.audit.log(
                user["tenant_id"], user["email"], "owner.password_reset_requested", "user",
                user["user_id"], getattr(request.state, "request_id", None), {},
            )
    return {"sent": True, "message": "إذا كان البريد مسجلًا، ستصلك رسالة إعادة التعيين."}


@router.post("/institution/reset-password")
def reset_password(body: ResetPasswordBody, request: Request, registry=Depends(get_registry)):
    """Consume a reset token (hashed, expiring, single-use) and set the password."""
    registry.db.set_tenant("platform")
    verdict, row = registry.invitations.consume_reset(body.token)
    if verdict != "valid" or not row:
        raise HTTPException(410, f"reset_{verdict}")
    registry.user_repo.set_password(row["user_id"], body.password)
    registry.audit.log(
        row["tenant_id"], row["email"], "owner.password_reset_completed", "user",
        row["user_id"], getattr(request.state, "request_id", None), {},
    )
    return {"reset": True, "message": "تم تغيير كلمة المرور. يمكنك الآن تسجيل الدخول."}
