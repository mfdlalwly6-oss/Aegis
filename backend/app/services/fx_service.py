"""FX service — converts transaction money into a single reference value for risk.

Principles (enforced here, not by convention):
- The institution/sender-reported rate is STORED but never drives risk valuation alone.
- Risk reference rate comes from the AEGIS-managed rate store (fx_rates), region-aware.
- Every transaction gets an immutable FxSnapshot at decision time — old decisions
  are NEVER re-evaluated with newer rates.
- Missing rate for a known currency  -> FX_STALE (fallback to newest known rate + flag).
- Missing rate for unknown currency  -> FX_MISSING (policy: REVIEW, never silent ALLOW).
- Institution rate diverging from reference beyond threshold -> FX_DIVERGENT flag.
"""
from __future__ import annotations

from datetime import datetime, timezone

import structlog

from app.core.config import settings
from app.models.schemas import FxSnapshot, FxStatus, Money
from app.repositories.fx_rate_repo import FxRateRepository

logger = structlog.get_logger(__name__)


class FxService:
    def __init__(self, fx_repo: FxRateRepository, currency_checker=None):
        self.fx_repo = fx_repo
        # currency_checker(code)->bool tells whether the currency is known/active.
        self._is_known_currency = currency_checker or (lambda code: True)

    def normalize(self, amount: float, currency: str, *,
                  region: str | None = None,
                  institution_rate: float | None = None,
                  at: datetime | None = None) -> Money:
        """Produce the Money object: original untouched + reference value + FX proof."""
        ccy = (currency or "").upper()
        ref_ccy = settings.REFERENCE_CURRENCY.upper()
        region = region or settings.FX_DEFAULT_REGION
        at = at or datetime.now(timezone.utc)

        money = Money(original_amount=amount, original_currency=ccy,
                      reference_currency=ref_ccy)

        # Native reference currency — no conversion needed, no FX risk.
        if ccy == ref_ccy:
            money.reference_amount = amount
            money.fx = FxSnapshot(base_ccy=ccy, quote_ccy=ref_ccy, rate=1.0,
                                  rate_type="native", source="aegis_reference",
                                  region=region, fetched_at=at, valid_from=at,
                                  status=FxStatus.NATIVE,
                                  institution_rate=institution_rate)
            return money

        # Unknown currency entirely — cannot be valued. Never invent a rate.
        if not self._is_known_currency(ccy):
            money.reference_amount = None
            money.fx = FxSnapshot(base_ccy=ccy, quote_ccy=ref_ccy, rate=None,
                                  source="none", region=region, fetched_at=at,
                                  status=FxStatus.MISSING,
                                  institution_rate=institution_rate)
            logger.warning("fx.missing_currency", currency=ccy, region=region)
            return money

        # Look up the AEGIS reference rate valid at the transaction time.
        # Try direct pair first, then the inverse pair (1/rate) — rates are often
        # stored in one direction only.
        rate_row, inverted = self._lookup(ccy, ref_ccy, region=region, at=at)
        if rate_row is None:
            # Try cross-rate via reference currency (e.g., YER->SAR via USD)
            rate_row, inverted = self.cross_rate(ccy, ref_ccy, region=region, at=at)
        if rate_row is None:
            # Fallback: newest known rate regardless of validity window, flagged STALE.
            stale_row = self.fx_repo.latest_valid(ccy, ref_ccy, region=region,
                                                  at=datetime.max.replace(tzinfo=timezone.utc))
            if stale_row is None:
                money.reference_amount = None
                money.fx = FxSnapshot(base_ccy=ccy, quote_ccy=ref_ccy, rate=None,
                                      source="none", region=region, fetched_at=at,
                                      status=FxStatus.MISSING,
                                      institution_rate=institution_rate)
                return money
            rate_row = stale_row
            is_stale = True
        else:
            # Rate found within window — still check age against FX_STALE_HOURS.
            fetched = datetime.fromisoformat(rate_row["fetched_at"])
            age_h = (at - fetched).total_seconds() / 3600.0
            is_stale = age_h > settings.FX_STALE_HOURS

        ref_rate = float(rate_row["rate"])
        if inverted:
            ref_rate = 1.0 / ref_rate
        money.reference_amount = round(amount * ref_rate, 6)

        # Divergence check: institution-reported rate vs AEGIS reference.
        status = FxStatus.STALE if is_stale else FxStatus.OK
        divergence_pct = None
        if institution_rate:
            divergence_pct = abs(institution_rate - ref_rate) / ref_rate * 100.0
            if divergence_pct > settings.FX_DIVERGENCE_PCT:
                status = FxStatus.DIVERGENT
                logger.warning("fx.divergent", currency=ccy, region=region,
                               institution_rate=institution_rate, ref_rate=ref_rate,
                               divergence_pct=round(divergence_pct, 2))

        money.fx = FxSnapshot(
            base_ccy=ccy, quote_ccy=ref_ccy, rate=ref_rate,
            rate_type=rate_row.get("rate_type", "mid"),
            source=rate_row["source"], region=rate_row["region"],
            spread_pct=rate_row.get("spread_pct"),
            fetched_at=datetime.fromisoformat(rate_row["fetched_at"]),
            valid_from=datetime.fromisoformat(rate_row["valid_from"]),
            valid_to=(datetime.fromisoformat(rate_row["valid_to"])
                      if rate_row.get("valid_to") else None),
            is_stale=is_stale, status=status,
            institution_rate=institution_rate, divergence_pct=divergence_pct,
        )
        return money

    def _lookup(self, base: str, quote: str, *, region: str | None,
                at: datetime | None) -> tuple[dict | None, bool]:
        """Find a usable rate row. Returns (row, inverted). Tries direct pair,
        then the inverse pair which is inverted to serve the requested direction."""
        row = self.fx_repo.latest_valid(base, quote, region=region, at=at)
        if row is not None:
            return row, False
        inv = self.fx_repo.latest_valid(quote, base, region=region, at=at)
        if inv is not None and float(inv["rate"]) > 0:
            return inv, True
        return None, False

    def cross_rate(self, base: str, quote: str, *, region: str | None = None,
                   at: datetime | None = None) -> tuple[dict | None, bool]:
        """Find a cross rate via the reference currency when no direct pair exists.
        Example: YER->SAR when only YER->USD and USD->SAR are stored.
        Returns (synthetic_row, inverted) or (None, False)."""
        ref = settings.REFERENCE_CURRENCY.upper()
        if base == ref or quote == ref:
            return None, False  # not a cross-rate case
        # Try base->ref and ref->quote
        row1, inv1 = self._lookup(base, ref, region=region, at=at)
        row2, inv2 = self._lookup(ref, quote, region=region, at=at)
        if row1 is None or row2 is None:
            return None, False
        rate1 = float(row1["rate"])
        rate2 = float(row2["rate"])
        if inv1: rate1 = 1.0 / rate1
        if inv2: rate2 = 1.0 / rate2
        cross_rate_val = rate1 * rate2
        # Build a synthetic row for the snapshot
        synthetic = {
            "rate_id": f"cross_{base}_{quote}",
            "base_ccy": base, "quote_ccy": quote,
            "rate": cross_rate_val,
            "rate_type": "cross",
            "source": f"cross:{row1['source']}+{row2['source']}",
            "region": region or "global",
            "spread_pct": None,
            "fetched_at": max(row1.get("fetched_at", ""), row2.get("fetched_at", "")),
            "valid_from": max(row1.get("valid_from", ""), row2.get("valid_from", "")),
            "valid_to": None,
        }
        return synthetic, False

    def display_amount(self, money: Money, *, region: str | None = None) -> float | None:
        """Derived local-currency display value (default YER). Never stored as truth."""
        disp = settings.DISPLAY_CURRENCY.upper()
        if money.original_currency == disp:
            return money.original_amount
        if money.reference_amount is None:
            return None
        row, inverted = self._lookup(settings.REFERENCE_CURRENCY, disp,
                                     region=region or settings.FX_DEFAULT_REGION,
                                     at=None)
        if row is None:
            return None
        rate = float(row["rate"])
        if inverted:
            rate = 1.0 / rate
        return round(money.reference_amount * rate, 2)
