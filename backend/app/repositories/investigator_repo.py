"""Investigator accounts — platform-level fraud analysts (not tenant-scoped).
Passwords: PBKDF2-HMAC-SHA256 salted with SECRET_KEY, same scheme as UserRepository.
"""
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


class InvestigatorRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, email: str, name: str, password: str) -> dict:
        iid = generate_id("inv")
        self.db.execute(
            "INSERT INTO investigators (investigator_id,email,name,password_hash,"
            "status,created_at) VALUES (?,?,?,?,?,?)",
            (iid, email.strip().lower(), name.strip(), _hash_pw(password),
             "active", utcnow()))
        return self.get(iid)

    def get(self, investigator_id: str) -> dict | None:
        return self.db.query_one(
            "SELECT investigator_id,email,name,status,created_at,last_login_at "
            "FROM investigators WHERE investigator_id=?", (investigator_id,))

    def get_by_email(self, email: str) -> dict | None:
        return self.db.query_one(
            "SELECT * FROM investigators WHERE email=? AND status='active'",
            (email.strip().lower(),))

    def list(self) -> list[dict]:
        return self.db.query(
            "SELECT investigator_id,email,name,status,created_at,last_login_at "
            "FROM investigators WHERE status != 'deleted' ORDER BY created_at DESC")

    def authenticate(self, email: str, password: str) -> dict | None:
        inv = self.get_by_email(email)
        if not inv:
            return None
        if not hmac.compare_digest(_hash_pw(password), inv["password_hash"]):
            return None
        inv.pop("password_hash", None)
        return inv

    def touch_login(self, investigator_id: str) -> None:
        self.db.execute(
            "UPDATE investigators SET last_login_at=? WHERE investigator_id=?",
            (utcnow(), investigator_id))

    def deactivate(self, investigator_id: str) -> bool:
        cur = self.db.execute(
            "UPDATE investigators SET status='inactive' WHERE investigator_id=? "
            "AND status='active'", (investigator_id,))
        return cur.rowcount > 0

    def count(self) -> int:
        row = self.db.query_one(
            "SELECT COUNT(*) AS c FROM investigators WHERE status='active'")
        return row["c"] if row else 0
