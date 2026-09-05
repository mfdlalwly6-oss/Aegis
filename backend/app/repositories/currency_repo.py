"""Currency repository — registry of supported currencies (data-driven, extensible).

Adding a currency = one INSERT here + rows in fx_rates. No schema/rule change.
A currency is NEVER hard-deleted: it is only disabled (active=0) so historical
transactions, FX snapshots, rules and decisions keep their meaning.
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
        self,
        code: str,
        name: str,
        *,
        minor_unit: int = 2,
        round_unit: float = 1000,
        symbol: str | None = None,
        decimal_places: int | None = None,
        active: bool = True,
    ) -> dict:
        """Create a currency. Code is the PK (DB enforces uniqueness)."""
        dp = decimal_places if decimal_places is not None else minor_unit
        now = utcnow()
        self.db.execute(
            "INSERT INTO currencies (code,name,minor_unit,round_unit,active,created_at,symbol,decimal_places,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (code.upper(), name, minor_unit, round_unit, 1 if active else 0, now, symbol, dp, now),
        )
        return self.get(code)

    def update(
        self,
        code: str,
        *,
        name: str | None = None,
        minor_unit: int | None = None,
        round_unit: float | None = None,
        symbol: str | None = None,
        decimal_places: int | None = None,
    ) -> dict | None:
        """Edit descriptive fields. Historical records are unaffected because a
        transaction stores its own amounts/currency — the currency row is metadata."""
        cur = self.get(code)
        if not cur:
            return None
        self.db.execute(
            "UPDATE currencies SET name=?, minor_unit=?, round_unit=?, symbol=?, decimal_places=?, updated_at=? "
            "WHERE code=?",
            (
                name if name is not None else cur["name"],
                minor_unit if minor_unit is not None else cur["minor_unit"],
                round_unit if round_unit is not None else cur["round_unit"],
                symbol if symbol is not None else cur.get("symbol"),
                decimal_places if decimal_places is not None else cur.get("decimal_places"),
                utcnow(),
                code.upper(),
            ),
        )
        return self.get(code)

    def set_active(self, code: str, active: bool) -> dict | None:
        """Enable/disable a currency. Disabled => new transactions in it are rejected
        (CURRENCY_DISABLED); historical rows keep working because nothing is deleted."""
        self.db.execute(
            "UPDATE currencies SET active=?, updated_at=? WHERE code=?",
            (1 if active else 0, utcnow(), code.upper()),
        )
        return self.get(code)

    def get(self, code: str) -> dict | None:
        return self.db.query_one("SELECT * FROM currencies WHERE code=?", (code.upper(),))

    def is_known(self, code: str) -> bool:
        row = self.get(code)
        return bool(row and row["active"])

    def exists(self, code: str) -> bool:
        return self.get(code) is not None

    def is_active(self, code: str) -> bool:
        row = self.get(code)
        return bool(row and row["active"])

    def list_active(self) -> list[dict]:
        return self.db.query("SELECT * FROM currencies WHERE active=1 ORDER BY code")

    def list_all(self) -> list[dict]:
        return self.db.query("SELECT * FROM currencies ORDER BY code")

    def usage_count(self, code: str) -> dict:
        """Real usage for the disable warning (§19): transactions + fx_rates + rules.
        Best-effort — a missing table/column counts as 0, never raises."""
        code = code.upper()
        out = {"transactions": 0, "fx_rates": 0, "rules": 0}
        try:
            r = self.db.query_one("SELECT COUNT(*) AS c FROM transactions WHERE currency=?", (code,))
            out["transactions"] = int(r["c"]) if r else 0
        except Exception:
            pass
        try:
            r = self.db.query_one(
                "SELECT COUNT(*) AS c FROM fx_rates WHERE base_ccy=? OR quote_ccy=?", (code, code)
            )
            out["fx_rates"] = int(r["c"]) if r else 0
        except Exception:
            pass
        try:
            r = self.db.query_one("SELECT COUNT(*) AS c FROM rules WHERE currency=?", (code,))
            out["rules"] = int(r["c"]) if r else 0
        except Exception:
            pass
        return out

    def seed_defaults(self) -> int:
        """Seed YER/SAR/USD if the table is empty. Idempotent."""
        existing = self.db.query_one("SELECT COUNT(*) AS c FROM currencies")
        if existing and existing["c"]:
            return 0
        n = 0
        for code, name, mu, ru, sym in (
            ("USD", "US Dollar", 2, 1000, "$"),
            ("SAR", "Saudi Riyal", 2, 1000, "﷼"),
            ("YER", "Yemeni Rial", 0, 100000, "ر.ي"),
        ):
            self.add(code, name, minor_unit=mu, round_unit=ru, symbol=sym, decimal_places=mu)
            n += 1
        return n
