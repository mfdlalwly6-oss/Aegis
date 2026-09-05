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
            "tags_json,description,when_json,currency,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(rule_id) DO UPDATE SET name=excluded.name,"
            "severity=excluded.severity,score=excluded.score,enabled=excluded.enabled,"
            "tags_json=excluded.tags_json,description=excluded.description,"
            "when_json=excluded.when_json,currency=excluded.currency",
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
                rule.get("currency"),
                utcnow(),
            ),
        )

    def _row_to_rule(self, r: dict) -> dict:
        return {
            "id": r["rule_id"],
            "tenant_id": r["tenant_id"],
            "name": r["name"],
            "severity": r["severity"],
            "score": r["score"],
            "enabled": bool(r["enabled"]),
            "tags": json.loads(r["tags_json"]),
            "description": r["description"],
            "when": json.loads(r["when_json"]),
            "currency": r.get("currency"),
        }

    def list_all(self, tenant_id: str | None = None) -> list[dict]:
        """Platform rules (tenant_id IS NULL) + tenant-specific overrides."""
        rows = self.db.query(
            "SELECT * FROM rules WHERE tenant_id IS NULL OR tenant_id=?", (tenant_id or "",)
        )
        return [self._row_to_rule(r) for r in rows]

    def list_for_engine(self) -> list[dict]:
        """Everything the engine must hold in memory: platform rules (tenant_id
        IS NULL) plus every tenant's materialized override specs (tagged with
        their tenant_id). The engine replaces a platform rule with the tenant's
        override at evaluation time, so a customized rule is never evaluated
        twice and never fires on the wrong tenant."""
        rows = self.db.query("SELECT * FROM rules WHERE tenant_id IS NULL")
        specs = [self._row_to_rule(r) for r in rows]
        for tid, tenant_specs in self.all_tenant_rule_specs().items():
            specs.extend(tenant_specs)
        return specs

    # ── per-tenant rule customization (rule_overrides) ───────────────────────
    # A bank's customization REPLACES the platform rule for that tenant (or
    # defines a tenant-only rule). Platform rules stay untouched, so changing
    # one bank's policy never leaks into another bank's scoring.

    def upsert_override(self, tenant_id: str, rule_id: str, patch: dict, actor: str = "owner") -> None:
        now = utcnow()
        self.db.execute(
            "INSERT INTO rule_overrides (tenant_id,rule_id,enabled,score,severity,name,description,"
            "when_json,tags_json,created_by,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(tenant_id,rule_id) DO UPDATE SET enabled=excluded.enabled,"
            "score=excluded.score,severity=excluded.severity,name=excluded.name,"
            "description=excluded.description,when_json=excluded.when_json,"
            "tags_json=excluded.tags_json,updated_at=excluded.updated_at",
            (
                tenant_id,
                rule_id,
                None if patch.get("enabled") is None else int(bool(patch.get("enabled"))),
                patch.get("score"),
                patch.get("severity"),
                patch.get("name"),
                patch.get("description"),
                None if patch.get("when") is None else json.dumps(patch["when"]),
                None if patch.get("tags") is None else json.dumps(patch["tags"]),
                actor,
                now,
                now,
            ),
        )

    def delete_override(self, tenant_id: str, rule_id: str) -> bool:
        cur = self.db.execute(
            "DELETE FROM rule_overrides WHERE tenant_id=? AND rule_id=?", (tenant_id, rule_id)
        )
        return cur.rowcount > 0

    def list_overrides(self, tenant_id: str | None = None) -> list[dict]:
        if tenant_id:
            rows = self.db.query("SELECT * FROM rule_overrides WHERE tenant_id=?", (tenant_id,))
        else:
            rows = self.db.query("SELECT * FROM rule_overrides")
        return [
            {
                "tenant_id": r["tenant_id"],
                "rule_id": r["rule_id"],
                "enabled": None if r["enabled"] is None else bool(r["enabled"]),
                "score": r["score"],
                "severity": r["severity"],
                "name": r["name"],
                "description": r["description"],
                "when": json.loads(r["when_json"]) if r["when_json"] else None,
                "tags": json.loads(r["tags_json"]) if r["tags_json"] else None,
                "created_by": r["created_by"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    def tenant_rule_specs(self, tenant_id: str) -> list[dict]:
        """Materialized rule specs for this tenant's overrides ONLY (not the
        whole effective set): for each override row, the platform rule's spec
        with non-null override fields applied, or a tenant-only rule spec when
        no platform rule shares the id. The engine evaluates these in place of
        the platform rule for this tenant — so no double evaluation."""
        platform = {r["id"]: r for r in self.list_all(None)}
        specs = []
        for ov in self.list_overrides(tenant_id):
            base = platform.get(ov["rule_id"])
            if base:
                merged = dict(base)
                for f in ("enabled", "score", "severity", "name", "description", "when", "tags"):
                    if ov.get(f) is not None:
                        merged[f] = ov[f]
                merged["tenant_id"] = tenant_id
                specs.append(merged)
            else:
                specs.append(
                    {
                        "id": ov["rule_id"],
                        "tenant_id": tenant_id,
                        "name": ov.get("name") or ov["rule_id"],
                        "severity": ov.get("severity") or "medium",
                        "score": ov.get("score") if ov.get("score") is not None else 0.2,
                        "enabled": True if ov.get("enabled") is None else ov["enabled"],
                        "tags": ov.get("tags") or [],
                        "description": ov.get("description") or "",
                        "when": ov.get("when") or {"==": [1, 0]},  # never fires unless defined
                    }
                )
        return specs

    def all_tenant_rule_specs(self) -> dict[str, list[dict]]:
        """All tenants' materialized override specs, grouped by tenant_id."""
        tenants = {o["tenant_id"] for o in self.list_overrides()}
        return {tid: self.tenant_rule_specs(tid) for tid in tenants}

    def effective_rules_for(self, tenant_id: str) -> list[dict]:
        """The exact rule set that governs this tenant: every platform rule,
        with the tenant's override applied where one exists, plus tenant-only
        rules. This is what the engine evaluates for that tenant."""
        platform = self.list_all(None)  # platform rules only
        overrides = {o["rule_id"]: o for o in self.list_overrides(tenant_id)}
        out = []
        for base in platform:
            ov = overrides.pop(base["id"], None)
            if ov:
                merged = dict(base)
                for f in ("enabled", "score", "severity", "name", "description", "when", "tags"):
                    if ov.get(f) is not None:
                        merged[f] = ov[f]
                merged["tenant_id"] = tenant_id
                merged["customized"] = True
                out.append(merged)
            else:
                out.append(base)
        # remaining overrides = tenant-only rules (no platform rule with that id)
        for rule_id, ov in overrides.items():
            out.append(
                {
                    "id": rule_id,
                    "tenant_id": tenant_id,
                    "name": ov.get("name") or rule_id,
                    "severity": ov.get("severity") or "medium",
                    "score": ov.get("score") if ov.get("score") is not None else 0.2,
                    "enabled": True if ov.get("enabled") is None else ov["enabled"],
                    "tags": ov.get("tags") or [],
                    "description": ov.get("description") or "",
                    "when": ov.get("when") or {"==": [1, 0]},  # never fires unless defined
                    "currency": ov.get("currency"),
                    "customized": True,
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
