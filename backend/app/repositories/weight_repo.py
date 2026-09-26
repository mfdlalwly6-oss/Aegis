"""Weight profiles repository — platform default + per-tenant override risk weights.

Single source of truth for fusion weights. Resolution rule (enforced by
`effective_weights`): an ACTIVE tenant override wins; otherwise the platform
default row. Overrides are never copied per tenant — a tenant without an
override row simply inherits the default live, so editing the default
propagates instantly to every institution that has no override.

Rows are NEVER hard-deleted except an explicit override `delete` (which is a
revert-to-default); the platform default row is immutable-in-scope (you edit
its numbers, you cannot remove it).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.db import Database

COMPONENTS = ("rules", "ml", "graph", "aml", "behavior")
DEFAULT_WEIGHTS = {"rules": 0.35, "ml": 0.25, "graph": 0.15, "aml": 0.15, "behavior": 0.10}


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_dict(r) -> dict:
    return {
        "profile_id": r["profile_id"],
        "scope": r["scope"],
        "tenant_id": r["tenant_id"],
        "rules": float(r["rules"]),
        "ml": float(r["ml"]),
        "graph": float(r["graph"]),
        "aml": float(r["aml"]),
        "behavior": float(r["behavior"]),
        "active": int(r["active"]),
        "created_by": r["created_by"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
        "note": r["note"],
        "total": round(float(r["rules"]) + float(r["ml"]) + float(r["graph"]) + float(r["aml"]) + float(r["behavior"]), 4),
    }


class WeightRepository:
    def __init__(self, db: Database):
        self.db = db

    # -- reads ------------------------------------------------------------
    def get_default(self) -> dict:
        r = self.db.query_one("SELECT * FROM weight_profiles WHERE scope='default'")
        if not r:
            self._seed_default()
            r = self.db.query_one("SELECT * FROM weight_profiles WHERE scope='default'")
        return _row_to_dict(r)

    def get_override(self, tenant_id: str) -> dict | None:
        r = self.db.query_one(
            "SELECT * FROM weight_profiles WHERE scope='tenant' AND tenant_id=?",
            (tenant_id,),
        )
        return _row_to_dict(r) if r else None

    def list_overrides(self) -> list[dict]:
        rows = self.db.query(
            "SELECT * FROM weight_profiles WHERE scope='tenant' ORDER BY created_at ASC"
        )
        return [_row_to_dict(r) for r in rows]

    def effective_weights(self, tenant_id: str | None) -> dict:
        """The weights the fusion engine must use for this tenant right now.

        Active tenant override wins; else the platform default. A disabled or
        absent override transparently falls back to the default.
        """
        if tenant_id:
            ov = self.get_override(tenant_id)
            if ov and ov["active"] == 1:
                return {k: ov[k] for k in COMPONENTS} | {"source": "override", "profile_id": ov["profile_id"]}
        d = self.get_default()
        return {k: d[k] for k in COMPONENTS} | {"source": "default", "profile_id": d["profile_id"]}

    # -- writes -----------------------------------------------------------
    def update_default(self, *, actor: str, note: str | None = None, **weights) -> dict:
        cur = self.get_default()
        merged = {k: float(weights.get(k, cur[k])) for k in COMPONENTS}
        self._validate_sum(merged)
        self.db.execute(
            "UPDATE weight_profiles SET rules=?, ml=?, graph=?, aml=?, behavior=?, updated_at=?, note=? "
            "WHERE scope='default'",
            (merged["rules"], merged["ml"], merged["graph"], merged["aml"], merged["behavior"], utcnow(), note),
        )
        return self.get_default()

    def set_override(self, tenant_id: str, *, actor: str, note: str | None = None, active: bool = True, **weights) -> dict:
        merged = {k: float(weights[k]) for k in COMPONENTS if k in weights}
        for k in COMPONENTS:
            merged.setdefault(k, DEFAULT_WEIGHTS[k])
        self._validate_sum(merged)
        existing = self.get_override(tenant_id)
        now = utcnow()
        if existing:
            self.db.execute(
                "UPDATE weight_profiles SET rules=?, ml=?, graph=?, aml=?, behavior=?, active=?, updated_at=?, note=? "
                "WHERE scope='tenant' AND tenant_id=?",
                (merged["rules"], merged["ml"], merged["graph"], merged["aml"], merged["behavior"],
                 1 if active else 0, now, note, tenant_id),
            )
        else:
            self.db.execute(
                "INSERT INTO weight_profiles (profile_id,scope,tenant_id,rules,ml,graph,aml,behavior,active,created_by,created_at,updated_at,note) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"wp_{uuid4().hex[:24]}", "tenant", tenant_id, merged["rules"], merged["ml"], merged["graph"],
                 merged["aml"], merged["behavior"], 1 if active else 0, actor, now, now, note),
            )
        return self.get_override(tenant_id)

    def set_override_active(self, tenant_id: str, active: bool) -> dict | None:
        if not self.get_override(tenant_id):
            return None
        self.db.execute(
            "UPDATE weight_profiles SET active=?, updated_at=? WHERE scope='tenant' AND tenant_id=?",
            (1 if active else 0, utcnow(), tenant_id),
        )
        return self.get_override(tenant_id)

    def delete_override(self, tenant_id: str) -> bool:
        """Remove the override row => tenant transparently reverts to default."""
        if not self.get_override(tenant_id):
            return False
        self.db.execute(
            "DELETE FROM weight_profiles WHERE scope='tenant' AND tenant_id=?",
            (tenant_id,),
        )
        return True

    # -- helpers ------------------------------------------------------------
    def _seed_default(self) -> None:
        now = utcnow()
        try:
            self.db.execute(
                "INSERT INTO weight_profiles (profile_id,scope,tenant_id,rules,ml,graph,aml,behavior,active,created_by,created_at,updated_at) "
                "VALUES ('wp_default','default',NULL,?,?,?,?,?,1,'system',?,?)",
                (DEFAULT_WEIGHTS["rules"], DEFAULT_WEIGHTS["ml"], DEFAULT_WEIGHTS["graph"],
                 DEFAULT_WEIGHTS["aml"], DEFAULT_WEIGHTS["behavior"], now, now),
            )
        except Exception:
            pass

    @staticmethod
    def _validate_sum(weights: dict) -> None:
        total = sum(float(weights[k]) for k in COMPONENTS)
        if abs(total - 1.0) >= 0.0001:
            raise ValueError(f"weights must sum to 1.0 (got {total:.4f})")
