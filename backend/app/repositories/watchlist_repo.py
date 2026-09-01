"""Watchlist repository — tenant-scoped, lifecycle-aware, provenance-tracked.

Backward-compatible: ``add`` / ``check`` / ``list_all`` / ``seed_defaults``
keep their original signatures so existing callers (AMLService, importer,
seed) and the 111-test suite keep working unchanged.

New capabilities (additive):
- lifecycle: disable/enable (soft-delete keeps historical evidence)
- provenance: source + external_id per entry
- validity window: valid_from / valid_to
- rich attributes: entity_kind, aliases, dob, country, identifiers
- screening queries used by the matching engine (active + in-window only)
- provider sync log (watchlist_sync_log)
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from app.db import Database

_TYPES = ("sanctions", "pep", "high_risk_country", "custom")


def _now() -> str:
    return datetime.now(UTC).isoformat()


class WatchlistRepository:
    def __init__(self, db: Database):
        self.db = db

    # ── legacy-compatible write (used by importer + seed) ─────────────
    def add(self, list_type: str, value: str, meta: dict | None = None, tenant_id: str = "platform") -> bool:
        cur = self.db.execute(
            "INSERT OR IGNORE INTO watchlist (tenant_id,list_type,value,meta_json) VALUES (?,?,?,?)",
            (tenant_id, list_type, value, json.dumps(meta or {}, ensure_ascii=False)),
        )
        return cur.rowcount > 0

    # ── rich write (used by new API + provider sync) ──────────────────
    def add_entry(self, list_type: str, value: str, *, tenant_id: str = "platform",
                  entity_kind: str = "entity", aliases: list[str] | None = None,
                  dob: str | None = None, country: str | None = None,
                  identifiers: dict | None = None, source: str = "manual",
                  external_id: str | None = None, meta: dict | None = None,
                  valid_from: str | None = None, valid_to: str | None = None) -> dict:
        """Insert or (if a disabled/duplicate row exists) re-activate+update it.
        Returns the stored row."""
        now = _now()
        if list_type not in _TYPES:
            raise ValueError(f"invalid_list_type:{list_type}")
        # Canonical form: normalize the value (uppercase, collapsed whitespace) so the
        # (tenant_id, list_type, value) unique constraint actually deduplicates
        # case variants, and exact-match screening stays consistent with the importer.
        value = " ".join(str(value).split()).upper()
        existing = self.db.query_one(
            "SELECT * FROM watchlist WHERE tenant_id=? AND list_type=? AND value=?",
            (tenant_id, list_type, value),
        )
        if existing:
            self.db.execute(
                "UPDATE watchlist SET entity_kind=?, aliases_json=?, dob=?, country=?, "
                "identifiers_json=?, source=?, external_id=?, meta_json=?, valid_from=?, "
                "valid_to=?, status='active', deactivated_at=NULL, updated_at=? WHERE id=?",
                (entity_kind, json.dumps(aliases or [], ensure_ascii=False), dob, country,
                 json.dumps(identifiers or {}, ensure_ascii=False), source, external_id,
                 json.dumps(meta or {}, ensure_ascii=False), valid_from, valid_to, now,
                 existing["id"]),
            )
            out = dict(existing)
            out.update({"status": "active", "updated_at": now, "_reactivated": True})
            return out
        row = self.db.query_one(
            "INSERT INTO watchlist (tenant_id,list_type,value,entity_kind,aliases_json,dob,"
            "country,identifiers_json,source,external_id,meta_json,valid_from,valid_to,"
            "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id",
            (tenant_id, list_type, value, entity_kind,
             json.dumps(aliases or [], ensure_ascii=False), dob, country,
             json.dumps(identifiers or {}, ensure_ascii=False), source, external_id,
             json.dumps(meta or {}, ensure_ascii=False), valid_from, valid_to, now, now),
        )
        return self.db.query_one("SELECT * FROM watchlist WHERE id=?", (row["id"],))

    # ── legacy-compatible read (single, exact, country codes) ─────────
    def check(self, list_type: str, value: str, tenant_id: str = "platform") -> dict | None:
        # Entries are stored canonically (uppercased, whitespace-collapsed) by
        # add_entry; screening must normalize the same way or case variants of
        # a listed entity slip through exact-match checks.
        value = " ".join(str(value).split()).upper()
        return self.db.query_one(
            "SELECT * FROM watchlist WHERE list_type=? AND value=? AND tenant_id IN (?, 'platform') "
            "AND status='active' "
            "ORDER BY CASE WHEN tenant_id=? THEN 0 ELSE 1 END LIMIT 1",
            (list_type, value, tenant_id, tenant_id),
        )

    # ── screening read: active + in-window entries for a type/tenant ──
    def list_active(self, list_type: str, tenant_id: str) -> list[dict]:
        now = _now()
        return self.db.query(
            "SELECT * FROM watchlist WHERE list_type=? AND tenant_id IN (?, 'platform') "
            "AND status='active' AND (valid_from IS NULL OR valid_from<=?) "
            "AND (valid_to IS NULL OR valid_to>=?)",
            (list_type, tenant_id, now, now),
        )

    def list_all(self, list_type: str | None = None, tenant_id: str = "platform",
                 include_disabled: bool = False) -> list[dict]:
        sql = "SELECT * FROM watchlist WHERE tenant_id=?"
        params: list = [tenant_id]
        if list_type:
            sql += " AND list_type=?"
            params.append(list_type)
        if not include_disabled:
            sql += " AND status='active'"
        sql += " ORDER BY id DESC"
        return self.db.query(sql, tuple(params))

    # ── platform-wide listing for the owner console ───────────────────
    def list_for_owner(self, tenant_id: str | None = None, list_type: str | None = None) -> list[dict]:
        sql = "SELECT * FROM watchlist WHERE 1=1"
        params: list = []
        if tenant_id:
            sql += " AND tenant_id=?"
            params.append(tenant_id)
        if list_type:
            sql += " AND list_type=?"
            params.append(list_type)
        sql += " ORDER BY id DESC LIMIT 2000"
        return self.db.query(sql, tuple(params))

    # ── lifecycle (soft disable keeps point-in-time evidence) ─────────
    def set_status(self, entry_id: int, status: str, tenant_id: str) -> dict | None:
        if status not in ("active", "disabled"):
            raise ValueError("invalid_status")
        now = _now()
        self.db.execute(
            "UPDATE watchlist SET status=?, deactivated_at=?, updated_at=? WHERE id=? AND tenant_id=?",
            (status, now if status == "disabled" else None, now, entry_id, tenant_id),
        )
        return self.db.query_one("SELECT * FROM watchlist WHERE id=? AND tenant_id=?", (entry_id, tenant_id))

    def get(self, entry_id: int, tenant_id: str) -> dict | None:
        return self.db.query_one("SELECT * FROM watchlist WHERE id=? AND tenant_id=?", (entry_id, tenant_id))

    def seed_defaults(self) -> int:
        defaults = {
            "sanctions": ["IR", "KP", "SY", "CU"],
            "high_risk_country": ["AF", "MM", "KP", "IR", "SY"],
            "pep": [],
        }
        count = 0
        for lt, values in defaults.items():
            for v in values:
                self.add(lt, v)
                count += 1
        return count

    # ── provider sync log ─────────────────────────────────────────────
    def sync_log_start(self, provider: str, tenant_id: str) -> int:
        row = self.db.query_one(
            "INSERT INTO watchlist_sync_log (tenant_id,provider,started_at,status) VALUES (?,?,?,'running') RETURNING id",
            (tenant_id, provider, _now()),
        )
        return row["id"]

    def sync_log_finish(self, log_id: int, *, status: str, added: int = 0, updated: int = 0,
                        removed: int = 0, error: str | None = None, detail: dict | None = None) -> None:
        self.db.execute(
            "UPDATE watchlist_sync_log SET finished_at=?, status=?, added=?, updated=?, removed=?, "
            "error=?, detail_json=? WHERE id=?",
            (_now(), status, added, updated, removed, error,
             json.dumps(detail or {}, ensure_ascii=False), log_id),
        )

    def sync_history(self, tenant_id: str, limit: int = 50) -> list[dict]:
        return self.db.query(
            "SELECT * FROM watchlist_sync_log WHERE tenant_id=? ORDER BY id DESC LIMIT ?",
            (tenant_id, limit),
        )
