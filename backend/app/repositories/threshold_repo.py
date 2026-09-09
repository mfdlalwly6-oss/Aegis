"""Threshold profiles repository — platform default + per-tenant decision thresholds.

Single source of truth for decision thresholds (challenge / review / block) and
the FX-missing action. Resolution rule (enforced by `effective_thresholds`):
an ACTIVE tenant override wins; otherwise the platform default row. Overrides
are never copied per tenant — a tenant without an override row inherits the
default live, so editing the default propagates instantly to every institution
that has no active override. Disabling or deleting an override reverts the
tenant to the default transparently.

Safety is enforced here (mirroring policy_engine.THRESHOLD_BOUNDS) so a bad
value can never reach the DB even if called directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.db import Database

KEYS = ("challenge", "review", "block")
DEFAULT_THRESHOLDS = {"challenge": 0.35, "review": 0.60, "block": 0.80}
DEFAULT_FX_ACTION = "review"

# Same safe windows as policy_engine.THRESHOLD_BOUNDS (kept in sync).
BOUNDS = {
    "challenge": (0.20, 0.50),
    "review": (0.40, 0.75),
    "block": (0.60, 0.95),
}
FX_ACTIONS = ("review", "block")


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_dict(r) -> dict:
    return {
        "profile_id": r["profile_id"],
        "scope": r["scope"],
        "tenant_id": r["tenant_id"],
        "challenge": float(r["challenge"]),
        "review": float(r["review"]),
        "block": float(r["block"]),
        "fx_missing_action": r["fx_missing_action"],
        "active": int(r["active"]),
        "created_by": r["created_by"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
        "note": r["note"],
    }


class ThresholdRepository:
    def __init__(self, db: Database):
        self.db = db

    # -- reads ------------------------------------------------------------
    def get_default(self) -> dict:
        r = self.db.query_one("SELECT * FROM threshold_profiles WHERE scope='default'")
        if not r:
            self._seed_default()
            r = self.db.query_one("SELECT * FROM threshold_profiles WHERE scope='default'")
        return _row_to_dict(r)

    def get_override(self, tenant_id: str) -> dict | None:
        r = self.db.query_one(
            "SELECT * FROM threshold_profiles WHERE scope='tenant' AND tenant_id=?",
            (tenant_id,),
        )
        return _row_to_dict(r) if r else None

    def list_overrides(self) -> list[dict]:
        rows = self.db.query(
            "SELECT * FROM threshold_profiles WHERE scope='tenant' ORDER BY created_at ASC"
        )
        return [_row_to_dict(r) for r in rows]

    def effective_thresholds(self, tenant_id: str | None) -> dict:
        """The thresholds the decision engine must use for this tenant right now.

        Active tenant override wins; else the platform default. A disabled or
        absent override transparently falls back to the default.
        """
        if tenant_id:
            ov = self.get_override(tenant_id)
            if ov and ov["active"] == 1:
                return {
                    "challenge": ov["challenge"], "review": ov["review"], "block": ov["block"],
                    "fx_missing_action": ov["fx_missing_action"],
                    "source": "override", "profile_id": ov["profile_id"],
                }
        d = self.get_default()
        return {
            "challenge": d["challenge"], "review": d["review"], "block": d["block"],
            "fx_missing_action": d["fx_missing_action"],
            "source": "default", "profile_id": d["profile_id"],
        }

    # -- writes -----------------------------------------------------------
    def update_default(self, *, actor: str, note: str | None = None,
                       fx_missing_action: str | None = None, **th) -> dict:
        cur = self.get_default()
        merged = {k: float(th.get(k, cur[k])) for k in KEYS}
        fxa = (fx_missing_action or cur["fx_missing_action"])
        self._validate(merged, fxa)
        self.db.execute(
            "UPDATE threshold_profiles SET challenge=?, review=?, block=?, fx_missing_action=?, updated_at=?, note=? "
            "WHERE scope='default'",
            (merged["challenge"], merged["review"], merged["block"], fxa, utcnow(), note),
        )
        return self.get_default()

    def set_override(self, tenant_id: str, *, actor: str, note: str | None = None,
                     active: bool = True, fx_missing_action: str | None = None, **th) -> dict:
        existing = self.get_override(tenant_id)
        base = existing if existing else DEFAULT_THRESHOLDS | {"fx_missing_action": DEFAULT_FX_ACTION}
        merged = {k: float(th.get(k, base[k])) for k in KEYS}
        fxa = (fx_missing_action or base.get("fx_missing_action") or DEFAULT_FX_ACTION)
        self._validate(merged, fxa)
        now = utcnow()
        if existing:
            self.db.execute(
                "UPDATE threshold_profiles SET challenge=?, review=?, block=?, fx_missing_action=?, active=?, updated_at=?, note=? "
                "WHERE scope='tenant' AND tenant_id=?",
                (merged["challenge"], merged["review"], merged["block"], fxa,
                 1 if active else 0, now, note, tenant_id),
            )
        else:
            self.db.execute(
                "INSERT INTO threshold_profiles (profile_id,scope,tenant_id,challenge,review,block,fx_missing_action,active,created_by,created_at,updated_at,note) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"thp_{uuid4().hex[:24]}", "tenant", tenant_id,
                 merged["challenge"], merged["review"], merged["block"], fxa,
                 1 if active else 0, actor, now, now, note),
            )
        return self.get_override(tenant_id)

    def set_override_active(self, tenant_id: str, active: bool) -> dict | None:
        if not self.get_override(tenant_id):
            return None
        self.db.execute(
            "UPDATE threshold_profiles SET active=?, updated_at=? WHERE scope='tenant' AND tenant_id=?",
            (1 if active else 0, utcnow(), tenant_id),
        )
        return self.get_override(tenant_id)

    def delete_override(self, tenant_id: str) -> bool:
        """Remove the override row => tenant transparently reverts to default."""
        if not self.get_override(tenant_id):
            return False
        self.db.execute(
            "DELETE FROM threshold_profiles WHERE scope='tenant' AND tenant_id=?",
            (tenant_id,),
        )
        return True

    # -- helpers ----------------------------------------------------------
    def _seed_default(self) -> None:
        now = utcnow()
        try:
            self.db.execute(
                "INSERT INTO threshold_profiles (profile_id,scope,tenant_id,challenge,review,block,fx_missing_action,active,created_by,created_at,updated_at) "
                "VALUES ('thp_default','default',NULL,?,?,?,?,1,'system',?,?)",
                (DEFAULT_THRESHOLDS["challenge"], DEFAULT_THRESHOLDS["review"], DEFAULT_THRESHOLDS["block"],
                 DEFAULT_FX_ACTION, now, now),
            )
        except Exception:
            pass

    @staticmethod
    def _validate(th: dict, fx_action: str) -> None:
        for k in KEYS:
            lo, hi = BOUNDS[k]
            if not (lo <= float(th[k]) <= hi):
                raise ValueError(f"{k} must be within [{lo}, {hi}] (got {th[k]})")
        if not (th["challenge"] <= th["review"] <= th["block"]):
            raise ValueError(
                f"thresholds must satisfy challenge<=review<=block "
                f"(got {th['challenge']}/{th['review']}/{th['block']})"
            )
        if fx_action not in FX_ACTIONS:
            raise ValueError(f"fx_missing_action must be one of {FX_ACTIONS} (never a silent allow)")
