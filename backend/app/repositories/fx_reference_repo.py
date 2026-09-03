"""FX reference-set repository — named rate sets assignable to many institutions.

A reference set holds USD/YER + SAR/YER and can be edited in place (members are
preserved; old decisions are never re-priced because each decision keeps its own
immutable snapshot). A tenant belongs to at most ONE active set at a time —
assigning to a new set auto-removes it from the previous one (with audit).
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.db import Database
from app.security import generate_id


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class FxReferenceRepository:
    def __init__(self, db: Database):
        self.db = db

    # ── sets ──────────────────────────────────────────────────────────────────
    def create_set(self, name: str, usd_yer: float, sar_yer: float, created_by: str = "owner") -> dict:
        sid = generate_id("fxs")
        now = utcnow()
        self.db.execute(
            "INSERT INTO fx_reference_sets (set_id,name,usd_yer,sar_yer,active,created_by,created_at,updated_at) "
            "VALUES (?,?,?,?,1,?,?,?)",
            (sid, name, float(usd_yer), float(sar_yer), created_by, now, now),
        )
        return self.get_set(sid)

    def get_set(self, set_id: str) -> dict | None:
        return self.db.query_one("SELECT * FROM fx_reference_sets WHERE set_id=?", (set_id,))

    def list_sets(self) -> list[dict]:
        rows = self.db.query("SELECT * FROM fx_reference_sets ORDER BY created_at DESC")
        return [self._with_members(r) for r in rows]

    def update_set(self, set_id: str, usd_yer: float | None = None, sar_yer: float | None = None) -> dict | None:
        cur = self.get_set(set_id)
        if not cur:
            return None
        self.db.execute(
            "UPDATE fx_reference_sets SET usd_yer=?, sar_yer=?, updated_at=? WHERE set_id=?",
            (float(usd_yer if usd_yer is not None else cur["usd_yer"]),
             float(sar_yer if sar_yer is not None else cur["sar_yer"]),
             utcnow(), set_id),
        )
        return self.get_set(set_id)

    def set_active(self, set_id: str, active: bool) -> dict | None:
        self.db.execute("UPDATE fx_reference_sets SET active=?, updated_at=? WHERE set_id=?",
                        (1 if active else 0, utcnow(), set_id))
        return self.get_set(set_id)

    # ── membership ────────────────────────────────────────────────────────────
    def assign(self, set_id: str, tenant_id: str, actor: str = "owner") -> dict:
        """Assign tenant to this set, auto-removing it from any other set first
        (prevents conflicting reference assignments). Returns the move record."""
        prev = self.db.query("SELECT set_id FROM fx_reference_members WHERE tenant_id=?", (tenant_id,))
        moved_from = None
        for r in prev:
            if r["set_id"] != set_id:
                moved_from = r["set_id"]
                self.db.execute("DELETE FROM fx_reference_members WHERE tenant_id=? AND set_id=?",
                                (tenant_id, r["set_id"]))
        self.db.execute(
            "INSERT INTO fx_reference_members (set_id,tenant_id,added_by,added_at) VALUES (?,?,?,?) "
            "ON CONFLICT(set_id,tenant_id) DO NOTHING",
            (set_id, tenant_id, actor, utcnow()),
        )
        return {"set_id": set_id, "tenant_id": tenant_id, "moved_from": moved_from}

    def unassign(self, tenant_id: str) -> bool:
        """Remove a tenant's reference assignment (falls back to institution/general)."""
        cur = self.db.execute("DELETE FROM fx_reference_members WHERE tenant_id=?", (tenant_id,))
        return cur.rowcount > 0

    def members(self, set_id: str) -> list[str]:
        rows = self.db.query("SELECT tenant_id FROM fx_reference_members WHERE set_id=?", (set_id,))
        return [r["tenant_id"] for r in rows]

    def set_for_tenant(self, tenant_id: str) -> dict | None:
        """The active reference set governing this tenant, if any."""
        row = self.db.query_one(
            "SELECT s.* FROM fx_reference_members m JOIN fx_reference_sets s ON s.set_id=m.set_id "
            "WHERE m.tenant_id=? AND s.active=1",
            (tenant_id,),
        )
        return row

    def _with_members(self, r: dict) -> dict:
        out = dict(r)
        out["active"] = bool(out.get("active"))
        out["members"] = self.members(out["set_id"])
        out["member_count"] = len(out["members"])
        return out
