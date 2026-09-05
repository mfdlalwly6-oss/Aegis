"""FX rate repository — append-only rate store. No UPDATE/DELETE of historical rates.

Lookup picks the newest rate that was valid at the transaction's effective time,
preferring the most specific region and the most authoritative source.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.db import Database
from app.security import generate_id

# Higher = more authoritative for risk/reference valuation.
_SOURCE_RANK = {
    "official": 40,
    "aegis_reference": 30,
    "provider": 20,  # provider:<name> ranks 20
    "market": 15,
    "manual": 10,
    "institution": 5,  # sender-reported: lowest trust for risk
}


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _rank(source: str) -> int:
    if source.startswith("provider"):
        return _SOURCE_RANK["provider"]
    return _SOURCE_RANK.get(source, 0)


class FxRateRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(
        self,
        base_ccy: str,
        quote_ccy: str,
        rate: float,
        *,
        rate_type: str = "mid",
        source: str = "aegis_reference",
        region: str = "global",
        spread_pct: float | None = None,
        valid_from: str | None = None,
        valid_to: str | None = None,
        tenant_id: str | None = None,
    ) -> dict:
        now = utcnow()
        rid = generate_id("fxr")
        vf = valid_from or now
        self.db.execute(
            "INSERT INTO fx_rates (rate_id,base_ccy,quote_ccy,rate,rate_type,source,"
            "region,spread_pct,fetched_at,valid_from,valid_to,created_at,tenant_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                rid,
                base_ccy.upper(),
                quote_ccy.upper(),
                float(rate),
                rate_type,
                source,
                region,
                spread_pct,
                now,
                vf,
                valid_to,
                now,
                tenant_id,
            ),
        )
        return self.get(rid)

    def get(self, rate_id: str) -> dict | None:
        return self.db.query_one("SELECT * FROM fx_rates WHERE rate_id=?", (rate_id,))

    def latest_valid(
        self,
        base_ccy: str,
        quote_ccy: str,
        *,
        region: str | None = None,
        at: datetime | None = None,
        tenant_id: str | None = None,
        tenant_only: bool = False,
    ) -> dict | None:
        """Newest rate valid at `at` (default now). Priority: a rate scoped to this
        tenant (Tenant FX Override) always wins; otherwise region-specific beats
        'global'. Among ties, higher-trust source wins, then most recent fetched_at."""
        base, quote = base_ccy.upper(), quote_ccy.upper()
        at_iso = (at or datetime.now(UTC)).isoformat()

        # Tier 0 — Tenant FX Override: a rate row scoped to this exact tenant.
        if tenant_id:
            trows = self.db.query(
                "SELECT * FROM fx_rates WHERE base_ccy=? AND quote_ccy=? AND tenant_id=? "
                "AND active=1 "
                "AND valid_from<=? AND (valid_to IS NULL OR valid_to>?) "
                "ORDER BY fetched_at DESC",
                (base, quote, tenant_id, at_iso, at_iso),
            )
            if trows:
                trows.sort(key=lambda r: (_rank(r["source"]), r["fetched_at"]), reverse=True)
                out = dict(trows[0]); out["_rank"] = _rank(out["source"])
                return out
            if tenant_only:
                return None  # caller wants tenant-scoped rates only

        regions = (
            [region, "global"]
            if region and region != "global"
            else ([region] if region else ["global"])
        )
        best = None
        for reg in regions:
            rows = self.db.query(
                "SELECT * FROM fx_rates WHERE base_ccy=? AND quote_ccy=? AND region=? "
                "AND tenant_id IS NULL "
                "AND valid_from<=? AND (valid_to IS NULL OR valid_to>?) "
                "ORDER BY active DESC, fetched_at DESC",
                (base, quote, reg, at_iso, at_iso),
            )
            if rows:
                # rank by source trust, then recency
                rows.sort(key=lambda r: (_rank(r["source"]), r["fetched_at"]), reverse=True)
                best = rows[0]
                break  # most specific region found — stop
        if best is None:
            return None
        out = dict(best)
        out["_rank"] = _rank(out["source"])
        return out

    def set_active(self, rate_id: str, active: bool) -> dict | None:
        """Enable/disable a rate row in place (flag only — the row and every
        historical snapshot referencing it stay intact)."""
        self.db.execute("UPDATE fx_rates SET active=? WHERE rate_id=?",
                        (1 if active else 0, rate_id))
        return self.get(rate_id)

    def end(self, rate_id: str, at_iso: str) -> dict | None:
        self.db.execute("UPDATE fx_rates SET valid_to=? WHERE rate_id=?", (at_iso, rate_id))
        return self.get(rate_id)

    def list_active(self, region: str | None = None) -> list[dict]:
        if region:
            return self.db.query(
                "SELECT * FROM fx_rates WHERE region=? AND (valid_to IS NULL OR valid_to>?) "
                "ORDER BY fetched_at DESC",
                (region, utcnow()),
            )
        return self.db.query(
            "SELECT * FROM fx_rates WHERE valid_to IS NULL OR valid_to>? ORDER BY fetched_at DESC",
            (utcnow(),),
        )
