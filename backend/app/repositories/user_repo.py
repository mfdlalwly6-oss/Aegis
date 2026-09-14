from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime

from app.core.config import settings
from app.db import Database
from app.security import generate_id


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _new_salt() -> str:
    """Fresh per-user random salt (hex)."""
    return secrets.token_hex(16)


def _hash_pw_with_salt(password: str, salt_hex: str) -> str:
    """PBKDF2-SHA256 with a per-user random salt (100k iterations)."""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 100_000).hex()


def _hash_pw_legacy(password: str) -> str:
    """Legacy fixed-salt hash — kept ONLY to verify pre-031 accounts."""
    salt = settings.SECRET_KEY[:16].encode()
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000).hex()


def _verify_pw(password: str, user: dict) -> bool:
    """Verify against the per-user salted hash; fall back to legacy fixed-salt.

    password_salt NULL ⇒ the row still holds a legacy hash. We verify with the
    legacy scheme and return True; the caller opportunistically upgrades the
    row to a random salt (never a lockout, fully backward compatible).
    """
    stored = user.get("password_hash")
    if not stored:
        return False
    salt = user.get("password_salt")
    if salt:
        return hmac.compare_digest(_hash_pw_with_salt(password, salt), stored)
    return hmac.compare_digest(_hash_pw_legacy(password), stored)


class UserRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(
        self,
        tenant_id: str,
        email: str,
        name: str,
        role: str = "viewer",
        password: str | None = None,
        status: str = "active",
    ) -> dict:
        uid = generate_id("usr")
        salt = _new_salt() if password else None
        pw_hash = _hash_pw_with_salt(password, salt) if password else None
        self.db.execute(
            "INSERT INTO users (user_id,tenant_id,email,name,role,password_hash,"
            "password_salt,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (uid, tenant_id, email.strip().lower(), name, role, pw_hash, salt, status, utcnow()),
        )
        return self.get(uid)

    def find_by_email_any_status(self, tenant_id: str, email: str) -> dict | None:
        """Lookup regardless of status (needed to detect invited/disabled owners)."""
        return self.db.query_one(
            "SELECT * FROM users WHERE tenant_id=? AND email=? ORDER BY created_at DESC LIMIT 1",
            (tenant_id, email.strip().lower()),
        )

    def find_global_by_email_any_status(self, email: str) -> dict | None:
        return self.db.query_one(
            "SELECT * FROM users WHERE email=? ORDER BY created_at DESC LIMIT 1",
            (email.strip().lower(),),
        )

    def set_password(self, user_id: str, password: str) -> bool:
        """Set a new password (fresh random salt) AND revoke all sessions issued
        before this moment (tokens_valid_after=now). Never logs/returns the raw
        password."""
        salt = _new_salt()
        self.db.execute(
            "UPDATE users SET password_hash=?, password_salt=?, tokens_valid_after=? "
            "WHERE user_id=?",
            (_hash_pw_with_salt(password, salt), salt, utcnow(), user_id),
        )
        return True

    def set_status(self, user_id: str, status: str) -> bool:
        """Activate / disable / mark-invited a user account.

        On 'disabled' we also bump tokens_valid_after so every outstanding JWT
        for this account stops validating immediately (server-side revocation).
        On re-activation the floor is kept — the user must log in again (a
        fresh token is issued then), which is the correct security semantics.
        """
        if status == "disabled":
            self.db.execute(
                "UPDATE users SET status=?, tokens_valid_after=? WHERE user_id=?",
                (status, utcnow(), user_id),
            )
        else:
            self.db.execute("UPDATE users SET status=? WHERE user_id=?", (status, user_id))
        return True

    def upgrade_password_salt_if_legacy(self, user_id: str, password: str) -> None:
        """After a successful legacy login, transparently rehash with a fresh
        random per-user salt (no lockout, seamless migration). Does NOT touch
        tokens_valid_after — a legitimate login must not kill the session it
        just created."""
        salt = _new_salt()
        self.db.execute(
            "UPDATE users SET password_hash=?, password_salt=? WHERE user_id=?",
            (_hash_pw_with_salt(password, salt), salt, user_id),
        )

    def get(self, user_id: str) -> dict | None:
        return self.db.query_one("SELECT * FROM users WHERE user_id=?", (user_id,))

    def get_by_email(self, tenant_id: str, email: str) -> dict | None:
        return self.db.query_one(
            "SELECT * FROM users WHERE tenant_id=? AND email=? AND status='active'",
            (tenant_id, email),
        )

    def list_by_tenant(self, tenant_id: str) -> list[dict]:
        return self.db.query(
            "SELECT user_id,tenant_id,email,name,role,status,created_at FROM users "
            "WHERE tenant_id=? AND status='active'",
            (tenant_id,),
        )

    def authenticate(self, tenant_id: str, email: str, password: str) -> dict | None:
        user = self.get_by_email(tenant_id, email)
        if not user or not user.get("password_hash"):
            return None
        if not _verify_pw(password, user):
            return None
        if not user.get("password_salt"):
            self.upgrade_password_salt_if_legacy(user["user_id"], password)
        return user

    def update_role(self, user_id: str, role: str) -> dict | None:
        self.db.execute("UPDATE users SET role=? WHERE user_id=?", (role, user_id))
        return self.get(user_id)

    def deactivate(self, user_id: str) -> bool:
        self.db.execute("UPDATE users SET status='inactive' WHERE user_id=?", (user_id,))
        return True


if not hasattr(UserRepository, "authenticate_global"):

    def authenticate_global(self, email, password):
        user = self.db.query_one(
            "SELECT * FROM users WHERE email=? AND status='active' ORDER BY created_at LIMIT 1",
            (email.strip().lower(),),
        )
        if not user or not user.get("password_hash"):
            return None
        if not _verify_pw(password, user):
            return None
        # Seamless legacy → per-user-salt upgrade on successful login.
        if not user.get("password_salt"):
            self.upgrade_password_salt_if_legacy(user["user_id"], password)
        return user

    UserRepository.authenticate_global = authenticate_global
