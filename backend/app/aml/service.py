"""AML screening — technical detection platform, NOT a legal compliance substitute.
Uses DB-backed watchlists + pattern detection on transaction data.
"""
from __future__ import annotations

from typing import Any

from app.models.schemas import AMLSignal, Transaction
from app.repositories.watchlist_repo import WatchlistRepository


class AMLService:
    def __init__(self, watchlist_repo: WatchlistRepository):
        self.watchlist = watchlist_repo

    async def screen(self, tx: Transaction, features: dict[str, Any]) -> AMLSignal:
        signal = AMLSignal()
        score = 0.0
        flags: list[str] = []

        beneficiary_country = tx.beneficiary_country or (
            tx.device.ip_country if tx.device else None
        )
        if beneficiary_country:
            hit = self.watchlist.check("sanctions", beneficiary_country.upper())
            if hit:
                signal.sanctions_hit = True
                score += 0.60
                flags.append(f"SANCTIONS_HIT:{beneficiary_country}")
            hr = self.watchlist.check("high_risk_country", beneficiary_country.upper())
            if hr:
                signal.fatf_high_risk_country = True
                score += 0.20
                flags.append(f"HIGH_RISK_COUNTRY:{beneficiary_country}")

        amount = float(tx.amount)
        vel = features.get("velocity", {})

        structuring_count = vel.get("count_9k_10k_30d", 0)
        if 9000 <= amount < 10000 and structuring_count >= 2:
            signal.typology_matches.append("structuring_smurfing")
            score += 0.30
            flags.append("STRUCTURING_PATTERN")

        if vel.get("tx_count_1h", 0) >= 8 and vel.get("amount_1h", 0) > 20000:
            signal.typology_matches.append("rapid_movement_of_funds")
            score += 0.25
            flags.append("RAPID_FUND_MOVEMENT")

        if features.get("amount_flags", {}).get("is_round_1000") and features.get("beneficiary", {}).get("offshore"):
            signal.typology_matches.append("round_amount_offshore")
            score += 0.15
            flags.append("ROUND_AMOUNT_OFFSHORE")

        if features.get("device", {}).get("tor") or features.get("device", {}).get("vpn"):
            if amount > 5000:
                signal.typology_matches.append("anonymity_tool_high_value")
                score += 0.10
                flags.append("ANONYMITY_TOOL_HIGH_VALUE")

        signal.score = min(1.0, score)
        signal.risk_flags = flags
        return signal
