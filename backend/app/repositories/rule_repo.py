from __future__ import annotations

import json
from datetime import UTC, datetime

from app.db import Database


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class RuleRepository:
    def __init__(self, db: Database):
        self.db = db

    def upsert(self, rule: dict, tenant_id: str | None = None) -> dict:
        self.db.execute(
            "INSERT INTO rules (rule_id,tenant_id,name,severity,score,enabled,"
            "tags_json,description,when_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(rule_id) DO UPDATE SET name=excluded.name,"
            "severity=excluded.severity,score=excluded.score,enabled=excluded.enabled,"
            "tags_json=excluded.tags_json,description=excluded.description,"
            "when_json=excluded.when_json",
            (
                rule["id"],
                tenant_id,
                rule["name"],
                rule.get("severity", "medium"),
                float(rule.get("score", 0.2)),
                int(rule.get("enabled", True)),
                json.dumps(rule.get("tags", [])),
                rule.get("description", ""),
                json.dumps(rule["when"]),
                utcnow(),
            ),
        )

    def list_all(self, tenant_id: str | None = None) -> list[dict]:
        """Platform rules (tenant_id IS NULL) + tenant-specific overrides."""
        rows = self.db.query(
            "SELECT * FROM rules WHERE tenant_id IS NULL OR tenant_id=?", (tenant_id or "",)
        )
        out = []
        for r in rows:
            out.append(
                {
                    "id": r["rule_id"],
                    "tenant_id": r["tenant_id"],
                    "name": r["name"],
                    "severity": r["severity"],
                    "score": r["score"],
                    "enabled": bool(r["enabled"]),
                    "tags": json.loads(r["tags_json"]),
                    "description": r["description"],
                    "when": json.loads(r["when_json"]),
                }
            )
        return out

    def delete(self, rule_id: str, tenant_id: str | None = None) -> bool:
        cur = self.db.execute(
            "DELETE FROM rules WHERE rule_id=? AND (tenant_id IS NULL OR tenant_id=?)",
            (rule_id, tenant_id or ""),
        )
        return cur.rowcount > 0

    def seed_defaults(self, rules: list[dict]) -> int:
        count = 0
        for rule in rules:
            existing = self.db.query_one("SELECT 1 FROM rules WHERE rule_id=?", (rule["id"],))
            if not existing:
                self.upsert(rule, tenant_id=None)
                count += 1
        return count
