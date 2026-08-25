"""Currency repository — registry of supported currencies (data-driven, extensible).

Adding a 4th currency = one INSERT here + rows in fx_rates. No schema/rule change.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.db import Database


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class CurrencyRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(
        self, code: str, name: str, *, minor_unit: int = 2, round_unit: float = 1000, active: bool = True
    ) -> dict:
        self.db.execute(
            "INSERT OR REPLACE INTO currencies (code,name,minor_unit,round_unit,active,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (code.upper(), name, minor_unit, round_unit, 1 if active else 0, utcnow()),
        )
        return self.get(code)

    def get(self, code: str) -> dict | None:
        return self.db.query_one("SELECT * FROM currencies WHERE code=?", (code.upper(),))

    def is_known(self, code: str) -> bool:
        row = self.get(code)
        return bool(row and row["active"])

    def list_active(self) -> list[dict]:
        return self.db.query("SELECT * FROM currencies WHERE active=1 ORDER BY code")

    def seed_defaults(self) -> int:
        """Seed YER/SAR/USD if the table is empty. Idempotent."""
        existing = self.db.query_one("SELECT COUNT(*) AS c FROM currencies")
        if existing and existing["c"]:
            return 0
        n = 0
        for code, name, mu, ru in (
            ("USD", "US Dollar", 2, 1000),
            ("SAR", "Saudi Riyal", 2, 1000),
            ("YER", "Yemeni Rial", 0, 100000),
        ):
            self.add(code, name, minor_unit=mu, round_unit=ru)
            n += 1
        return n
