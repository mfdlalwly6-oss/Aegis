"""FX service — converts transaction money into a single reference value for risk.

Source-precedence architecture (§6). The resolver picks ONE authoritative rate per
transaction, highest priority first, and records which layer won in the snapshot:

    1. institution   — a rate the institution itself provides AND the platform can
                       trust (present in payload, sane, and within the configured
                       divergence budget of the platform reference). This is the
                       first tier per spec, but an untrusted/absent value never
                       drives risk valuation on its own.
    2. manual        — a Manual FX Override row scoped to this tenant.
    3. reference     — a Reference FX Group the tenant is assigned to.
    4. general       — the platform-wide rate store (region-aware).

Every transaction gets an immutable FxSnapshot at decision time — old decisions are
NEVER re-evaluated with newer rates. Missing rate for a known currency -> FX_STALE
(fallback to newest known rate + flag); missing rate for an unknown currency ->
FX_MISSING (policy: REVIEW, never silent ALLOW).
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from app.core.config import settings
from app.models.schemas import FxSnapshot, FxStatus, Money
from app.repositories.fx_rate_repo import FxRateRepository

logger = structlog.get_logger(__name__)


class FxService:
    def __init__(self, fx_repo: FxRateRepository, currency_checker=None, reference_repo=None):
        self.fx_repo = fx_repo
        # currency_checker(code)->bool tells whether the currency is known/active.
        self._is_known_currency = currency_checker or (lambda code: True)
        # reference_repo: named USD/YER + SAR/YER sets assignable to institutions.
        self.reference_repo = reference_repo

    # ── tier helpers ──────────────────────────────────────────────────────────
    def _reference_set_rate(self, base: str, quote: str, tenant_id: str | None, at):
        """If this tenant is assigned to an active reference set, build a synthetic
        rate row for base->quote (or its inverse) from the set's USD/YER & SAR/YER.
        Returns (row, inverted) or (None, False)."""
        if not (self.reference_repo and tenant_id):
            return None, False
        s = self.reference_repo.set_for_tenant(tenant_id)
        if not s:
            return None, False
        usd_yer = float(s["usd_yer"]); sar_yer = float(s["sar_yer"])
        pair = {("USD", "YER"): usd_yer, ("SAR", "YER"): sar_yer}
        if (base, quote) in pair:
            rate, inv = pair[(base, quote)], False
        elif (quote, base) in pair:
            rate, inv = pair[(quote, base)], True
        else:
            return None, False
        row = {"rate_id": f"refset_{s['set_id']}", "base_ccy": base, "quote_ccy": quote,
               "rate": rate, "rate_type": "reference_set", "source": "reference",
               "region": "global", "spread_pct": None, "fetched_at": s["updated_at"],
               "valid_from": s["created_at"], "valid_to": None, "_rank": 35,
               "set_id": s["set_id"], "set_name": s.get("name")}
        return row, inv

    def _platform_reference(self, base: str, quote: str, *, region: str | None,
                            at: datetime | None, tenant_id: str | None) -> float | None:
        """Best-effort platform reference rate for base->quote, used ONLY to judge
        whether an institution-provided rate is trustworthy (divergence budget).
        Never returned as the chosen rate by itself here."""
        for b, q, inv in ((base, quote, False), (quote, base, True)):
            r = self.fx_repo.latest_valid(b, q, region=region, at=at, tenant_id=None)
            if r is not None and float(r["rate"]) > 0:
                rate = float(r["rate"])
                return (1.0 / rate) if inv else rate
        return None

    def _institution_row(self, base: str, quote: str, institution_rate: float | None,
                         *, region: str | None, at: datetime, tenant_id: str | None) -> tuple[dict | None, bool]:
        """Tier 1: institution-provided rate, used only when the platform can trust it.

        Trusted when: present, finite, > 0, and either no platform reference exists
        to compare against OR within the divergence budget of that reference.
        Returns (row, inverted) or (None, False)."""
        if not institution_rate:
            return None, False
        try:
            rate = float(institution_rate)
        except (TypeError, ValueError):
            return None, False
        if rate <= 0:
            return None, False
        ref = self._platform_reference(base, quote, region=region, at=at, tenant_id=tenant_id)
        if ref is not None and ref > 0:
            divergence_pct = abs(rate - ref) / ref * 100.0
            budget = float(getattr(settings, "FX_INSTITUTION_TRUST_PCT", settings.FX_DIVERGENCE_PCT * 2))
            if divergence_pct > budget:
                logger.warning(
                    "fx.institution_rate_rejected",
                    tenant_id=tenant_id, base=base, quote=quote,
                    institution_rate=rate, platform_ref=ref,
                    divergence_pct=round(divergence_pct, 2), budget=budget,
                )
                return None, False  # untrusted -> fall through to lower tiers
        return ({
            "rate_id": f"inst_{base}_{quote}", "base_ccy": base, "quote_ccy": quote,
            "rate": rate, "rate_type": "institution", "source": "institution",
            "region": region or "global", "spread_pct": None,
            "fetched_at": at.isoformat(), "valid_from": at.isoformat(), "valid_to": None,
            "_rank": 50,
        }, False)

    # ── public API ────────────────────────────────────────────────────────────
    def normalize(
        self,
        amount: float,
        currency: str,
        *,
        region: str | None = None,
        institution_rate: float | None = None,
        at: datetime | None = None,
        tenant_id: str | None = None,
    ) -> Money:
        """Produce the Money object: original untouched + reference value + FX proof."""
        ccy = (currency or "").upper()
        ref_ccy = settings.REFERENCE_CURRENCY.upper()
        region = region or settings.FX_DEFAULT_REGION
        at = at or datetime.now(UTC)

        money = Money(original_amount=amount, original_currency=ccy, reference_currency=ref_ccy)

        # Native reference currency — no conversion needed, no FX risk.
        if ccy == ref_ccy:
            money.reference_amount = amount
            money.fx = FxSnapshot(
                rate_id="native", base_ccy=ccy, quote_ccy=ref_ccy, rate=1.0,
                rate_type="native", source="aegis_reference", region=region,
                fetched_at=at, valid_from=at, status=FxStatus.NATIVE,
                institution_rate=institution_rate,
            )
            return money

        # Unknown currency entirely — cannot be valued. Never invent a rate.
        if not self._is_known_currency(ccy):
            money.reference_amount = None
            money.fx = FxSnapshot(
                base_ccy=ccy, quote_ccy=ref_ccy, rate=None, source="none",
                region=region, fetched_at=at, status=FxStatus.MISSING,
                institution_rate=institution_rate,
            )
            logger.warning("fx.missing_currency", currency=ccy, region=region)
            return money

        # Look up the AEGIS-managed rate valid at the transaction time.
        rate_row, inverted = self._lookup(ccy, ref_ccy, region=region, at=at,
                                          tenant_id=tenant_id, institution_rate=institution_rate)
        if rate_row is None:
            # Try cross-rate via reference currency (e.g., YER->SAR via USD)
            rate_row, inverted = self.cross_rate(ccy, ref_ccy, region=region, at=at, tenant_id=tenant_id)
        if rate_row is None:
            # Fallback: newest known rate regardless of validity window, flagged STALE.
            stale_row = self.fx_repo.latest_valid(
                ccy, ref_ccy, region=region, at=datetime.max.replace(tzinfo=UTC),
                tenant_id=tenant_id,
            )
            if stale_row is None:
                money.reference_amount = None
                money.fx = FxSnapshot(
                    base_ccy=ccy, quote_ccy=ref_ccy, rate=None, source="none",
                    region=region, fetched_at=at, status=FxStatus.MISSING,
                    institution_rate=institution_rate,
                )
                return money
            rate_row = stale_row
            is_stale = True
        else:
            fetched = datetime.fromisoformat(rate_row["fetched_at"])
            age_h = (at - fetched).total_seconds() / 3600.0
            is_stale = age_h > settings.FX_STALE_HOURS

        ref_rate = float(rate_row["rate"])
        if inverted:
            ref_rate = 1.0 / ref_rate
        money.reference_amount = round(amount * ref_rate, 6)

        # Divergence check: institution-reported rate vs the rate the resolver
        # would have used WITHOUT the institution tier (manual -> reference set
        # -> general). Comparing against the selected rate is wrong when the
        # institution rate ITSELF was selected (that would always yield 0%).
        status = FxStatus.STALE if is_stale else FxStatus.OK
        divergence_pct = None
        if institution_rate:
            baseline = ref_rate
            if rate_row["source"] == "institution":
                alt_row, alt_inv = self._lookup(ccy, ref_ccy, region=region, at=at,
                                                tenant_id=tenant_id)  # no institution_rate -> skips Tier 1
                if alt_row is not None:
                    baseline = float(alt_row["rate"])
                    if alt_inv:
                        baseline = 1.0 / baseline
            divergence_pct = abs(float(institution_rate) - baseline) / baseline * 100.0
            # Divergence is an AUDIT signal, recorded whenever the institution rate
            # deviates from the platform reference — even when the institution rate
            # itself was trusted enough to be selected (trust budget decides usage,
            # this flag records deviation for later review).
            if divergence_pct > settings.FX_DIVERGENCE_PCT:
                status = FxStatus.DIVERGENT
                logger.warning(
                    "fx.divergent", currency=ccy, region=region,
                    institution_rate=institution_rate, ref_rate=ref_rate,
                    divergence_pct=round(divergence_pct, 2),
                )

        money.fx = FxSnapshot(
            rate_id=rate_row.get("rate_id"),
            base_ccy=ccy,
            quote_ccy=ref_ccy,
            rate=ref_rate,
            rate_type=rate_row.get("rate_type", "mid"),
            source=rate_row["source"],
            region=rate_row["region"],
            spread_pct=rate_row.get("spread_pct"),
            fetched_at=datetime.fromisoformat(rate_row["fetched_at"]),
            valid_from=datetime.fromisoformat(rate_row["valid_from"]),
            valid_to=(datetime.fromisoformat(rate_row["valid_to"]) if rate_row.get("valid_to") else None),
            is_stale=is_stale,
            status=status,
            institution_rate=institution_rate,
            divergence_pct=divergence_pct,
        )
        return money

    def _lookup(
        self, base: str, quote: str, *, region: str | None, at: datetime | None,
        tenant_id: str | None = None, institution_rate: float | None = None,
    ) -> tuple[dict | None, bool]:
        """Resolve the authoritative rate row by source precedence. Returns
        (row, inverted). Order: institution -> manual override -> reference set
        -> general platform rates (each tier both directions where applicable)."""
        now = at or datetime.now(UTC)

        # Tier 1 — institution-provided rate, only when the platform trusts it.
        inst_row, inst_inv = self._institution_row(
            base, quote, institution_rate, region=region, at=now, tenant_id=tenant_id)
        if inst_row is not None:
            return inst_row, inst_inv

        candidates: list[tuple[dict, bool]] = []
        if tenant_id:
            # Tier 2 — Manual FX Override (tenant-scoped row), both directions.
            for b, q, inv_flag in ((base, quote, False), (quote, base, True)):
                t = self.fx_repo.latest_valid(b, q, region=region, at=at,
                                              tenant_id=tenant_id, tenant_only=True)
                if t is not None and float(t["rate"]) > 0:
                    candidates.append((t, inv_flag))
            if candidates:
                return candidates[0]

        # Tier 3 — Reference FX Group assigned to this tenant (USD/YER & SAR/YER).
        rs_row, rs_inv = self._reference_set_rate(base, quote, tenant_id, at)
        if rs_row is not None:
            return rs_row, rs_inv

        # Tier 4 — General platform rates, both directions, ranked by source trust.
        for b, q, inv_flag in ((base, quote, False), (quote, base, True)):
            r = self.fx_repo.latest_valid(b, q, region=region, at=at)
            if r is not None and float(r["rate"]) > 0:
                candidates.append((r, inv_flag))
        if not candidates:
            return None, False
        candidates.sort(
            key=lambda c: (c[0].get("_rank", 0), not c[1], c[0].get("fetched_at", "")),
            reverse=True,
        )
        return candidates[0]

    def cross_rate(
        self, base: str, quote: str, *, region: str | None = None, at: datetime | None = None,
        tenant_id: str | None = None,
    ) -> tuple[dict | None, bool]:
        """Find a cross rate via the reference currency when no direct pair exists.
        Example: YER->SAR when only YER->USD and USD->SAR are stored. Uses the SAME
        resolver (so the same tenant's precedence applies to both legs)."""
        ref = settings.REFERENCE_CURRENCY.upper()
        if base == ref or quote == ref:
            return None, False  # not a cross-rate case
        row1, inv1 = self._lookup(base, ref, region=region, at=at, tenant_id=tenant_id)
        if row1 is None:
            return None, False
        row2, inv2 = self._lookup(ref, quote, region=region, at=at, tenant_id=tenant_id)
        if row2 is None:
            return None, False
        rate1 = float(row1["rate"]); rate2 = float(row2["rate"])
        if inv1:
            rate1 = 1.0 / rate1
        if inv2:
            rate2 = 1.0 / rate2
        cross_rate_val = rate1 * rate2
        synthetic = {
            "rate_id": f"cross_{base}_{quote}", "base_ccy": base, "quote_ccy": quote,
            "rate": cross_rate_val, "rate_type": "cross",
            "source": f"cross:{row1['source']}+{row2['source']}",
            "region": region or "global", "spread_pct": None,
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
        row, inverted = self._lookup(
            settings.REFERENCE_CURRENCY, disp, region=region or settings.FX_DEFAULT_REGION, at=None
        )
        if row is None:
            return None
        rate = float(row["rate"])
        if inverted:
            rate = 1.0 / rate
        return round(money.reference_amount * rate, 2)
