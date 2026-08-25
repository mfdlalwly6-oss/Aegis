"""Tenant repository — multi-tenant institution registry with real credentials,
plans, investigator limits, timezone and soft-delete lifecycle.
Secrets (api_key / hmac_secret) are only returned when reveal=True.
"""

from __future__ import annotations

import hmac as hmac_mod
import json
import secrets
from datetime import UTC, datetime

from app.crypto import decrypt_secret, encrypt_secret
from app.db import Database
from app.security import generate_id

DEFAULT_REVIEW_MESSAGE = (
    "تم تعليق العملية مؤقتًا للمراجعة الأمنية. يرجى التواصل مع المؤسسة المالية لإتمام المراجعة."
)

_UPDATABLE = {
    "name",
    "country",
    "plan",
    "contact_email",
    "contact_phone",
    "investigator_limit",
    "timezone",
    "review_message",
}


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class TenantRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, data: dict) -> dict:
        now = _utcnow()
        tenant_id = generate_id("tn")
        api_key = "ak_" + secrets.token_hex(16)
        hmac_secret_plain = secrets.token_urlsafe(32)
        hmac_secret = encrypt_secret(hmac_secret_plain)
        plan = data.get("plan") or "sandbox"
        tz = data.get("timezone") or "Asia/Aden"
        limit = int(data.get("investigator_limit") or 5)
        self.db.execute(
            "INSERT INTO tenants (tenant_id, name, type, country, plan,"
            " contact_email, contact_phone, api_key, hmac_secret, status,"
            " policy_json, created_at, secret_rotated_at, deleted_at,"
            " investigator_limit, timezone, review_message)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                tenant_id,
                data["name"],
                data.get("type", "wallet"),
                data.get("country", "YE"),
                plan,
                data.get("contact_email"),
                data.get("contact_phone"),
                api_key,
                hmac_secret,
                "active",
                json.dumps(data.get("policy") or {}, ensure_ascii=False),
                now,
                None,
                None,
                limit,
                tz,
                data.get("review_message") or DEFAULT_REVIEW_MESSAGE,
            ),
        )
        return self.get(tenant_id, reveal=True)

    def list(self, include_deleted: bool = False) -> list[dict]:
        """Never leaks credentials — rows are sanitized (secrets stripped)."""
        if include_deleted:
            rows = self.db.query("SELECT * FROM tenants ORDER BY created_at DESC")
        else:
            rows = self.db.query("SELECT * FROM tenants WHERE deleted_at IS NULL ORDER BY created_at DESC")
        return [self._sanitize(r, False) for r in rows]

    def get(self, tenant_id: str, reveal: bool = False) -> dict | None:
        row = self.db.query_one("SELECT * FROM tenants WHERE tenant_id=?", (tenant_id,))
        if not row or (row.get("deleted_at") and not reveal):
            return None
        return self._sanitize(row, reveal)

    def get_by_api_key(self, api_key: str) -> dict | None:
        """Authentication path — returns secrets so the webhook can verify HMAC."""
        row = self.db.query_one("SELECT * FROM tenants WHERE api_key=?", (api_key,))
        if not row or row.get("deleted_at"):
            return None
        return self._sanitize(row, True)

    def by_api_key(self, api_key: str) -> dict | None:
        """Alias kept for interface compatibility with the webhook router."""
        return self.get_by_api_key(api_key)

    def update(self, tenant_id: str, patch: dict) -> dict | None:
        if not self.db.query_one("SELECT tenant_id FROM tenants WHERE tenant_id=?", (tenant_id,)):
            return None
        fields, params = [], []
        for key in _UPDATABLE:
            if key in patch and patch[key] is not None:
                fields.append(f"{key}=?")
                params.append(patch[key])
        if fields:
            params.append(tenant_id)
            # fields contain only whitelisted column names (validated above); values are
            # parameterized — the f-string interpolates column identifiers, never user data.
            self.db.execute(
                f"UPDATE tenants SET {', '.join(fields)} WHERE tenant_id=?",  # noqa: S608
                tuple(params),
            )
        return self.get(tenant_id, reveal=True)

    def set_status(self, tenant_id: str, status: str) -> dict | None:
        cur = self.db.execute(
            "UPDATE tenants SET status=? WHERE tenant_id=? AND deleted_at IS NULL", (status, tenant_id)
        )
        if cur.rowcount == 0:
            return None
        return self.get(tenant_id, reveal=True)

    def rotate_secret(self, tenant_id: str) -> dict | None:
        new_secret = encrypt_secret(secrets.token_urlsafe(32))
        cur = self.db.execute(
            "UPDATE tenants SET hmac_secret=?, secret_rotated_at=? WHERE tenant_id=? AND deleted_at IS NULL",
            (new_secret, _utcnow(), tenant_id),
        )
        if cur.rowcount == 0:
            return None
        return self.get(tenant_id, reveal=True)

    def update_policy(self, tenant_id: str, patch: dict) -> dict | None:
        row = self.db.query_one(
            "SELECT policy_json FROM tenants WHERE tenant_id=? AND deleted_at IS NULL", (tenant_id,)
        )
        if not row:
            return None
        try:
            policy = json.loads(row["policy_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            policy = {}
        if not isinstance(policy, dict):
            policy = {}
        for k, v in patch.items():
            if v is not None:
                policy[k] = v
        self.db.execute(
            "UPDATE tenants SET policy_json=? WHERE tenant_id=?",
            (json.dumps(policy, ensure_ascii=False), tenant_id),
        )
        return self.get(tenant_id, reveal=True)

    def get_policy(self, tenant_id: str) -> dict:
        """Return only this tenant's policy, safely falling back for malformed JSON."""
        row = self.db.query_one(
            "SELECT policy_json FROM tenants WHERE tenant_id=? AND deleted_at IS NULL", (tenant_id,)
        )
        if not row:
            return {}
        try:
            policy = json.loads(row.get("policy_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
        return policy if isinstance(policy, dict) else {}

    def delete(self, tenant_id: str) -> bool:
        cur = self.db.execute(
            "UPDATE tenants SET status='deleted', deleted_at=? WHERE tenant_id=? AND deleted_at IS NULL",
            (_utcnow(), tenant_id),
        )
        return cur.rowcount > 0

    def authenticate_merchant(self, api_key: str, api_secret: str) -> dict | None:
        row = self.db.query_one("SELECT * FROM tenants WHERE api_key=? AND deleted_at IS NULL", (api_key,))
        if not row:
            return None
        if row.get("status") != "active":
            return None
        if not hmac_mod.compare_digest(decrypt_secret(row["hmac_secret"]) or "", api_secret):
            return None
        return self._sanitize(row, True)

    @staticmethod
    def _sanitize(row: dict, reveal: bool) -> dict:
        out = dict(row)
        out["policy"] = json.loads(out.pop("policy_json", "{}") or "{}")
        if reveal:
            # Return plaintext hmac_secret to internal callers only
            if out.get("hmac_secret"):
                out["hmac_secret"] = decrypt_secret(out["hmac_secret"])
        else:
            out.pop("api_key", None)
            out.pop("hmac_secret", None)
        return out
