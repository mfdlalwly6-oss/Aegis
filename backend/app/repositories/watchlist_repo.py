from __future__ import annotations

import json

from app.db import Database


class WatchlistRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(self, list_type: str, value: str, meta: dict | None = None) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO watchlist (list_type,value,meta_json) VALUES (?,?,?)",
            (list_type, value, json.dumps(meta or {})),
        )

    def check(self, list_type: str, value: str) -> dict | None:
        return self.db.query_one("SELECT * FROM watchlist WHERE list_type=? AND value=?", (list_type, value))

    def list_all(self, list_type: str | None = None) -> list[dict]:
        if list_type:
            return self.db.query("SELECT * FROM watchlist WHERE list_type=?", (list_type,))
        return self.db.query("SELECT * FROM watchlist")

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
