from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone

from app.core.config import settings
from app.db import Database
from app.security import generate_id


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_pw(password: str) -> str:
    salt = settings.SECRET_KEY[:16].encode()
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000).hex()


class UserRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, tenant_id: str, email: str, name: str,
               role: str = "viewer", password: str | None = None) -> dict:
        uid = generate_id("usr")
        pw_hash = _hash_pw(password) if password else None
        self.db.execute(
            "INSERT INTO users (user_id,tenant_id,email,name,role,password_hash,"
            "status,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (uid, tenant_id, email, name, role, pw_hash, "active", utcnow()))
        return self.get(uid)

    def get(self, user_id: str) -> dict | None:
        return self.db.query_one("SELECT * FROM users WHERE user_id=?", (user_id,))

    def get_by_email(self, tenant_id: str, email: str) -> dict | None:
        return self.db.query_one(
            "SELECT * FROM users WHERE tenant_id=? AND email=? AND status='active'",
            (tenant_id, email))

    def list_by_tenant(self, tenant_id: str) -> list[dict]:
        return self.db.query(
            "SELECT user_id,tenant_id,email,name,role,status,created_at FROM users "
            "WHERE tenant_id=? AND status='active'", (tenant_id,))

    def authenticate(self, tenant_id: str, email: str, password: str) -> dict | None:
        user = self.get_by_email(tenant_id, email)
        if not user or not user.get("password_hash"):
            return None
        if not hmac.compare_digest(_hash_pw(password), user["password_hash"]):
            return None
        return user

    def update_role(self, user_id: str, role: str) -> dict | None:
        self.db.execute("UPDATE users SET role=? WHERE user_id=?", (role, user_id))
        return self.get(user_id)

    def deactivate(self, user_id: str) -> bool:
        self.db.execute("UPDATE users SET status='inactive' WHERE user_id=?", (user_id,))
        return True


if not hasattr(UserRepository, "authenticate_global"):
    def authenticate_global(self, email, password):
        import hashlib, hmac as _hm
        from app.core.config import settings
        salt = settings.SECRET_KEY.encode()[:16]
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000).hex()
        user = self.db.query_one(
            "SELECT * FROM users WHERE email=? AND status='active' ORDER BY created_at LIMIT 1",
            (email.strip().lower(),))
        if not user or not user.get("password_hash"):
            return None
        if not _hm.compare_digest(h, user["password_hash"]):
            return None
        return user
    UserRepository.authenticate_global = authenticate_global
