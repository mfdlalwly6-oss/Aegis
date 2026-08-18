from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db import Database
from app.security import (
    generate_api_key, generate_hmac_secret, generate_tenant_id, verify_api_key_secret,
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class TenantRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, body: dict) -> dict:
        tid = generate_tenant_id()
        api_key = generate_api_key()
        hmac_secret = generate_hmac_secret()
        now = utcnow()
        self.db.execute(
            "INSERT INTO tenants (tenant_id,name,type,country,plan,contact_email,"
            "contact_phone,api_key,hmac_secret,status,policy_json,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (tid, body["name"], body.get("type", "wallet"), body.get("country", "YE"),
             body.get("plan", "sandbox"), body.get("contact_email"),
             body.get("contact_phone"), api_key, hmac_secret, "active",
             json.dumps(body.get("policy", {})), now),
        )
        return self.get(tid, reveal=True)

    def list(self) -> list[dict]:
        rows = self.db.query(
            "SELECT tenant_id,name,type,country,plan,status,created_at FROM tenants "
            "WHERE status != 'deleted' ORDER BY created_at DESC"
        )
        return rows

    def get(self, tenant_id: str, reveal: bool = False) -> dict | None:
        row = self.db.query_one(
            "SELECT * FROM tenants WHERE tenant_id=? AND status != 'deleted'", (tenant_id,)
        )
        if not row:
            return None
        if not reveal:
            row = {k: v for k, v in row.items() if k not in ("hmac_secret",)}
            row["hmac_secret_masked"] = True
        if row.get("policy_json"):
            row["policy"] = json.loads(row.pop("policy_json"))
        return row

    def by_api_key(self, api_key: str) -> dict | None:
        row = self.db.query_one(
            "SELECT * FROM tenants WHERE api_key=? AND status='active'", (api_key,)
        )
        if row and row.get("policy_json"):
            row["policy"] = json.loads(row.pop("policy_json"))
        return row

    def rotate_secret(self, tenant_id: str) -> dict | None:
        existing = self.get(tenant_id, reveal=True)
        if not existing:
            return None
        new_secret = generate_hmac_secret()
        self.db.execute(
            "UPDATE tenants SET hmac_secret=?, secret_rotated_at=? WHERE tenant_id=?",
            (new_secret, utcnow(), tenant_id),
        )
        return self.get(tenant_id, reveal=True)

    def update_policy(self, tenant_id: str, policy: dict) -> dict | None:
        if not self.get(tenant_id):
            return None
        self.db.execute(
            "UPDATE tenants SET policy_json=? WHERE tenant_id=?",
            (json.dumps(policy), tenant_id),
        )
        return self.get(tenant_id)

    def delete(self, tenant_id: str) -> bool:
        if not self.get(tenant_id):
            return False
        self.db.execute(
            "UPDATE tenants SET status='deleted', deleted_at=? WHERE tenant_id=?",
            (utcnow(), tenant_id),
        )
        return True

    def authenticate_merchant(self, api_key: str, api_secret: str) -> dict | None:
        tenant = self.by_api_key(api_key)
        if not tenant:
            return None
        if not verify_api_key_secret(api_secret, tenant["hmac_secret"]):
            return None
        return tenant
