"""Policy version store — immutable, numbered, attributed policy snapshots.

Design: `tenants.policy_json` remains the decision-time source of truth (the
hot path in PolicyEngine.resolve is unchanged and fully backward compatible).
This repository adds the versioning layer the platform was missing: every
policy change is recorded as an immutable version (who/when/what/note), and
activating/disabling materializes the chosen version into tenants.policy_json.

An old decision therefore always traces to the exact policy that governed it,
because it carries the version's content hash — and the version rows are never
rewritten, only superseded by a newer version or disabled.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _hash(policy_json: str) -> str:
    return hashlib.sha256(policy_json.encode()).hexdigest()[:16]


class PolicyVersionRepository:
    def __init__(self, db):
        self.db = db

    def _row(self, r: dict) -> dict:
        return {
            "tenant_id": r["tenant_id"],
            "version": r["version"],
            "policy": json.loads(r["policy_json"]),
            "policy_hash": _hash(r["policy_json"]),
            "status": r["status"],
            "created_by": r["created_by"],
            "created_at": r["created_at"],
            "note": r["note"],
        }

    def next_version(self, tenant_id: str) -> int:
        row = self.db.query_one(
            "SELECT COALESCE(MAX(version), 0) + 1 AS v FROM policy_versions WHERE tenant_id=?",
            (tenant_id,),
        )
        return int(row["v"])

    def add(self, tenant_id: str, policy: dict, *, actor: str, note: str | None = None,
            status: str = "active") -> dict:
        version = self.next_version(tenant_id)
        pj = json.dumps(policy, ensure_ascii=False)
        self.db.execute(
            "INSERT INTO policy_versions (tenant_id,version,policy_json,status,created_by,created_at,note) "
            "VALUES (?,?,?,?,?,?,?)",
            (tenant_id, version, pj, status, actor, utcnow(), note),
        )
        return self._row(
            self.db.query_one(
                "SELECT * FROM policy_versions WHERE tenant_id=? AND version=?", (tenant_id, version)
            )
        )

    def list_for(self, tenant_id: str) -> list[dict]:
        rows = self.db.query(
            "SELECT * FROM policy_versions WHERE tenant_id=? ORDER BY version DESC", (tenant_id,)
        )
        return [self._row(r) for r in rows]

    def get(self, tenant_id: str, version: int) -> dict | None:
        r = self.db.query_one(
            "SELECT * FROM policy_versions WHERE tenant_id=? AND version=?", (tenant_id, version)
        )
        return self._row(r) if r else None

    def active(self, tenant_id: str) -> dict | None:
        r = self.db.query_one(
            "SELECT * FROM policy_versions WHERE tenant_id=? AND status='active' "
            "ORDER BY version DESC LIMIT 1",
            (tenant_id,),
        )
        return self._row(r) if r else None

    def set_status(self, tenant_id: str, version: int, status: str) -> dict | None:
        if status not in ("active", "disabled"):
            raise ValueError("invalid_status")
        self.db.execute(
            "UPDATE policy_versions SET status=? WHERE tenant_id=? AND version=?",
            (status, tenant_id, version),
        )
        return self.get(tenant_id, version)

    def disable_all(self, tenant_id: str) -> None:
        self.db.execute(
            "UPDATE policy_versions SET status='disabled' WHERE tenant_id=?", (tenant_id,)
        )
