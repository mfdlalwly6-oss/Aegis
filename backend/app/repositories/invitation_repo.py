"""Invitation + password-reset token repository — hashed, expiring, single-use.

Security guarantees enforced here:
- Raw tokens are NEVER stored — only their SHA-256 hash. A DB leak yields
  nothing usable.
- Invitations are single-use (accept flips status to 'accepted' atomically),
  expiring (expires_at checked on every consume), and revocable.
- Reset tokens follow the same model.
- No raw token is ever written to audit or logs.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from app.db import Database


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _row(r) -> dict:
    return {
        "invitation_id": r["invitation_id"], "tenant_id": r["tenant_id"],
        "user_id": r["user_id"], "email": r["email"], "status": r["status"],
        "invited_by": r["invited_by"], "expires_at": r["expires_at"],
        "accepted_at": r["accepted_at"], "created_at": r["created_at"],
    }


class InvitationRepository:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------ invites --
    def create_invitation(self, tenant_id: str, user_id: str, email: str, *,
                          invited_by: str, ttl_hours: int) -> tuple[dict, str]:
        """Create a pending invitation; returns (row, RAW token) — the raw token
        exists only here so it can be emailed; it is never persisted."""
        raw = "aeg_inv_" + secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        iid = f"inv_{secrets.token_hex(10)}"
        self.db.execute(
            "INSERT INTO invitations (invitation_id,tenant_id,user_id,email,token_hash,status,invited_by,expires_at,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (iid, tenant_id, user_id, email, _hash(raw), "pending", invited_by,
             _iso(now + timedelta(hours=ttl_hours)), _iso(now)),
        )
        return self.get_invitation(iid), raw

    def get_invitation(self, invitation_id: str) -> dict | None:
        r = self.db.query_one("SELECT * FROM invitations WHERE invitation_id=?", (invitation_id,))
        return _row(r) if r else None

    def list_pending_for_user(self, user_id: str) -> list[dict]:
        rows = self.db.query(
            "SELECT * FROM invitations WHERE user_id=? AND status='pending' ORDER BY created_at DESC",
            (user_id,))
        return [_row(r) for r in rows]

    def latest_for_user(self, user_id: str) -> dict | None:
        r = self.db.query_one(
            "SELECT * FROM invitations WHERE user_id=? ORDER BY created_at DESC LIMIT 1", (user_id,))
        return _row(r) if r else None

    def _sweep_expired(self) -> None:
        self.db.execute(
            "UPDATE invitations SET status='expired' WHERE status='pending' AND expires_at < ?",
            (utcnow(),))

    def consume(self, raw_token: str) -> tuple[str, dict | None]:
        """Validate a raw invite token. Returns (verdict, row).

        verdict ∈ valid | invalid | expired | revoked | used
        On 'valid' the invitation is atomically marked accepted.
        """
        self._sweep_expired()
        r = self.db.query_one("SELECT * FROM invitations WHERE token_hash=?", (_hash(raw_token),))
        if not r:
            return "invalid", None
        row = _row(r)
        if row["status"] == "accepted":
            return "used", row
        if row["status"] == "revoked":
            return "revoked", row
        if row["status"] == "expired" or _parse(row["expires_at"]) < datetime.now(UTC):
            return "expired", row
        # valid -> consume
        self.db.execute(
            "UPDATE invitations SET status='accepted', accepted_at=? WHERE invitation_id=? AND status='pending'",
            (utcnow(), row["invitation_id"]),
        )
        row["status"] = "accepted"
        row["accepted_at"] = utcnow()
        return "valid", row

    def peek(self, raw_token: str) -> tuple[str, dict | None]:
        """Like consume() but does NOT mark accepted (used by the GET preview)."""
        self._sweep_expired()
        r = self.db.query_one("SELECT * FROM invitations WHERE token_hash=?", (_hash(raw_token),))
        if not r:
            return "invalid", None
        row = _row(r)
        if row["status"] == "accepted":
            return "used", row
        if row["status"] == "revoked":
            return "revoked", row
        if row["status"] == "expired" or _parse(row["expires_at"]) < datetime.now(UTC):
            return "expired", row
        return "valid", row

    def revoke_user_pending(self, user_id: str) -> int:
        rows = self.list_pending_for_user(user_id)
        for r in rows:
            self.db.execute("UPDATE invitations SET status='revoked' WHERE invitation_id=?",
                            (r["invitation_id"],))
        return len(rows)

    # ------------------------------------------------------------- resets --
    def create_reset(self, tenant_id: str, user_id: str, email: str, *,
                     ttl_hours: int) -> tuple[dict, str]:
        raw = "aeg_rst_" + secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        rid = f"rst_{secrets.token_hex(10)}"
        self.db.execute(
            "INSERT INTO password_reset_tokens (reset_id,tenant_id,user_id,email,token_hash,status,expires_at,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (rid, tenant_id, user_id, email, _hash(raw), "pending",
             _iso(now + timedelta(hours=ttl_hours)), _iso(now)),
        )
        r = self.db.query_one("SELECT * FROM password_reset_tokens WHERE reset_id=?", (rid,))
        return dict(r), raw

    def consume_reset(self, raw_token: str) -> tuple[str, dict | None]:
        self.db.execute(
            "UPDATE password_reset_tokens SET status='expired' WHERE status='pending' AND expires_at < ?",
            (utcnow(),))
        r = self.db.query_one("SELECT * FROM password_reset_tokens WHERE token_hash=?", (_hash(raw_token),))
        if not r:
            return "invalid", None
        row = dict(r)
        if row["status"] == "used":
            return "used", row
        if row["status"] == "expired" or _parse(row["expires_at"]) < datetime.now(UTC):
            return "expired", row
        self.db.execute(
            "UPDATE password_reset_tokens SET status='used', used_at=? WHERE reset_id=? AND status='pending'",
            (utcnow(), row["reset_id"]),
        )
        row["status"] = "used"
        return "valid", row
