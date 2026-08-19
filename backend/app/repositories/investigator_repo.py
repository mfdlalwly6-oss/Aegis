"""Investigator repository — TENANT-SCOPED.
Every investigator belongs to exactly one tenant. All accessors enforce the
tenant_id bound; cross-tenant reads/writes return nothing (404 semantics).
Passwords are hashed (PBKDF2-HMAC-SHA256, secret-key salt) and never returned.
"""
from __future__ import annotations

import hashlib
import hmac as hmac_mod
from datetime import datetime, timezone

from app.core.config import settings
from app.db import Database
from app.security import generate_id

_ITERATIONS = 100_000


def _hash_pw(password: str) -> str:
    salt = settings.SECRET_KEY.encode()[:16]
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS).hex()


def _verify_pw(password: str, stored: str) -> bool:
    if not stored:
        return False
    candidate = _hash_pw(password)
    return hmac_mod.compare_digest(candidate, stored)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class InvestigatorRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, tenant_id: str, email: str, name: str, password: str) -> dict:
        inv_id = generate_id("inv")
        now = _utcnow()
        self.db.execute(
            "INSERT INTO investigators (investigator_id, tenant_id, email, name,"
            " password_hash, status, created_at, last_login_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (inv_id, tenant_id, email.strip().lower(), name,
             _hash_pw(password), "active", now, None))
        return {"investigator_id": inv_id, "tenant_id": tenant_id,
                "email": email.strip().lower(), "name": name,
                "status": "active", "created_at": now, "last_login_at": None}

    def get_by_email(self, email: str) -> dict | None:
        row = self.db.query_one(
            "SELECT * FROM investigators WHERE email=?", (email.strip().lower(),))
        return self._strip(row)

    def get(self, investigator_id: str, tenant_id: str | None = None) -> dict | None:
        if tenant_id:
            row = self.db.query_one(
                "SELECT * FROM investigators WHERE investigator_id=? AND tenant_id=?",
                (investigator_id, tenant_id))
        else:
            row = self.db.query_one(
                "SELECT * FROM investigators WHERE investigator_id=?",
                (investigator_id,))
        return self._strip(row)

    def list(self, tenant_id: str | None = None) -> list[dict]:
        if tenant_id:
            rows = self.db.query(
                "SELECT * FROM investigators WHERE tenant_id=? "
                "ORDER BY created_at DESC", (tenant_id,))
        else:
            rows = self.db.query(
                "SELECT * FROM investigators ORDER BY created_at DESC")
        return [self._strip(r) for r in rows]

    def count(self, tenant_id: str | None = None) -> int:
        if tenant_id:
            row = self.db.query_one(
                "SELECT COUNT(*) AS c FROM investigators WHERE tenant_id=?",
                (tenant_id,))
        else:
            row = self.db.query_one("SELECT COUNT(*) AS c FROM investigators")
        return row["c"] if row else 0

    def count_active(self, tenant_id: str | None = None) -> int:
        if tenant_id:
            row = self.db.query_one(
                "SELECT COUNT(*) AS c FROM investigators "
                "WHERE tenant_id=? AND status IN ('active','suspended_by_owner')",
                (tenant_id,))
        else:
            row = self.db.query_one(
                "SELECT COUNT(*) AS c FROM investigators WHERE status='active'")
        return row["c"] if row else 0

    def authenticate(self, email: str, password: str) -> dict | None:
        row = self.db.query_one(
            "SELECT * FROM investigators WHERE email=? AND status IN ('active','suspended_by_owner')",
            (email.strip().lower(),))
        if not row or not _verify_pw(password, row["password_hash"]):
            return None
        return self._strip(row)

    def touch_login(self, investigator_id: str) -> None:
        self.db.execute(
            "UPDATE investigators SET last_login_at=? WHERE investigator_id=?",
            (_utcnow(), investigator_id))

    def set_status(self, tenant_id: str, investigator_id: str, status: str) -> bool:
        cur = self.db.execute(
            "UPDATE investigators SET status=? "
            "WHERE investigator_id=? AND tenant_id=?",
            (status, investigator_id, tenant_id))
        return cur.rowcount > 0

    def reset_password(self, tenant_id: str, investigator_id: str,
                       password: str) -> bool:
        cur = self.db.execute(
            "UPDATE investigators SET password_hash=? "
            "WHERE investigator_id=? AND tenant_id=?",
            (_hash_pw(password), investigator_id, tenant_id))
        return cur.rowcount > 0

    @staticmethod
    def _strip(row: dict | None) -> dict | None:
        if not row:
            return None
        row.pop("password_hash", None)
        return row
