from __future__ import annotations

import json

from app.db import Database


class WatchlistRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(self, list_type: str, value: str, meta: dict | None = None, tenant_id: str = "platform") -> bool:
        cur = self.db.execute(
            "INSERT OR IGNORE INTO watchlist (tenant_id,list_type,value,meta_json) VALUES (?,?,?,?)",
            (tenant_id, list_type, value, json.dumps(meta or {}, ensure_ascii=False)),
        )
        return cur.rowcount > 0

    def check(self, list_type: str, value: str, tenant_id: str = "platform") -> dict | None:
        return self.db.query_one(
            "SELECT * FROM watchlist WHERE list_type=? AND value=? AND tenant_id IN (?, 'platform') "
            "ORDER BY CASE WHEN tenant_id=? THEN 0 ELSE 1 END LIMIT 1",
            (list_type, value, tenant_id, tenant_id),
        )

    def list_all(self, list_type: str | None = None, tenant_id: str = "platform") -> list[dict]:
        if list_type:
            return self.db.query(
                "SELECT * FROM watchlist WHERE list_type=? AND tenant_id=?", (list_type, tenant_id)
            )
        return self.db.query("SELECT * FROM watchlist WHERE tenant_id=?", (tenant_id,))

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
