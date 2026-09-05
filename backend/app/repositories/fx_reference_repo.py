"""FX reference-set repository — named rate sets assignable to many institutions.

A reference set holds USD/YER + SAR/YER and can be edited in place (members are
preserved). Every edit writes a NEW row to fx_reference_versions and closes the
prior version (effective_to), so the set's own rate timeline is auditable while
historical decisions stay frozen on their immutable fx snapshots.

A tenant belongs to at most ONE set at a time: enforced at the DB level by
ux_fx_ref_members_tenant (UNIQUE tenant_id) AND in code by auto-reassignment.
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

    # ── versions (immutable rate timeline) ───────────────────────────────────
    def _add_version(self, set_id: str, usd_yer: float, sar_yer: float, actor: str) -> None:
        """Close the currently-open version and open a new one effective now."""
        now = utcnow()
        self.db.execute(
            "UPDATE fx_reference_versions SET effective_to=? WHERE set_id=? AND effective_to IS NULL",
            (now, set_id),
        )
        self.db.execute(
            "INSERT INTO fx_reference_versions (version_id,set_id,usd_yer,sar_yer,effective_from,created_by) "
            "VALUES (?,?,?,?,?,?)",
            (generate_id("fxv"), set_id, float(usd_yer), float(sar_yer), now, actor),
        )

    def set_history(self, set_id: str) -> list[dict]:
        """Full rate timeline for a set, newest first."""
        return self.db.query(
            "SELECT * FROM fx_reference_versions WHERE set_id=? ORDER BY effective_from DESC",
            (set_id,),
        )

    def current_version(self, set_id: str) -> dict | None:
        return self.db.query_one(
            "SELECT * FROM fx_reference_versions WHERE set_id=? AND effective_to IS NULL "
            "ORDER BY effective_from DESC LIMIT 1",
            (set_id,),
        )

    # ── sets ──────────────────────────────────────────────────────────────────
    def create_set(self, name: str, usd_yer: float, sar_yer: float, created_by: str = "owner") -> dict:
        sid = generate_id("fxs")
        now = utcnow()
        self.db.execute(
            "INSERT INTO fx_reference_sets (set_id,name,usd_yer,sar_yer,active,created_by,created_at,updated_at) "
            "VALUES (?,?,?,?,1,?,?,?)",
            (sid, name, float(usd_yer), float(sar_yer), created_by, now, now),
        )
        self._add_version(sid, usd_yer, sar_yer, created_by)
        return self.get_set(sid)

    def get_set(self, set_id: str) -> dict | None:
        return self.db.query_one("SELECT * FROM fx_reference_sets WHERE set_id=?", (set_id,))

    def list_sets(self) -> list[dict]:
        rows = self.db.query("SELECT * FROM fx_reference_sets ORDER BY created_at DESC")
        return [self._with_members(r) for r in rows]

    def update_set(self, set_id: str, usd_yer: float | None = None, sar_yer: float | None = None,
                   actor: str = "owner") -> dict | None:
        """Edit the CURRENT set in place — members preserved. Records a new version
        so the rate change is auditable; historical decisions keep their snapshots."""
        cur = self.get_set(set_id)
        if not cur:
            return None
        new_usd = float(usd_yer if usd_yer is not None else cur["usd_yer"])
        new_sar = float(sar_yer if sar_yer is not None else cur["sar_yer"])
        self.db.execute(
            "UPDATE fx_reference_sets SET usd_yer=?, sar_yer=?, updated_at=? WHERE set_id=?",
            (new_usd, new_sar, utcnow(), set_id),
        )
        # Only record a version when the rate actually changed.
        if new_usd != float(cur["usd_yer"]) or new_sar != float(cur["sar_yer"]):
            self._add_version(set_id, new_usd, new_sar, actor)
        return self.get_set(set_id)

    def set_active(self, set_id: str, active: bool) -> dict | None:
        self.db.execute("UPDATE fx_reference_sets SET active=?, updated_at=? WHERE set_id=?",
                        (1 if active else 0, utcnow(), set_id))
        return self.get_set(set_id)

    # ── membership ────────────────────────────────────────────────────────────
    def assign(self, set_id: str, tenant_id: str, actor: str = "owner") -> dict:
        """Assign tenant to this set, auto-removing it from any other set first.
        DB unique index guarantees one set per tenant even under concurrency.
        Returns the move record (moved_from = previous set_id, if any)."""
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
        """Remove a tenant's reference assignment (resolver falls back to the next
        available tier — institution/manual/general). Never leaves a tenant broken."""
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
