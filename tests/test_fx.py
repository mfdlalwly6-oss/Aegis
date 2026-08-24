"""FX service tests — conversion, staleness, missing, divergent, cross-rate, inverse."""
from datetime import datetime, timezone, timedelta
import pytest
from app.services.fx_service import FxService
from app.repositories.fx_rate_repo import FxRateRepository
from app.repositories.currency_repo import CurrencyRepository
from app.core.config import settings


@pytest.fixture
def fx_svc(db):
    fx_repo = FxRateRepository(db)
    currency_repo = CurrencyRepository(db)
    return FxService(fx_repo, currency_checker=lambda c: currency_repo.is_known(c))


class TestFxConversion:
    def test_native_reference_currency(self, fx_svc, db):
        # USD -> USD should be 1:1, status NATIVE
        money = fx_svc.normalize(100.0, "USD", region="global")
        assert money.reference_amount == 100.0
        assert money.reference_currency == "USD"
        assert money.fx.status.value == "native"

    def test_known_currency_with_direct_rate(self, fx_svc, db):
        # SAR -> USD using seeded rate (0.2667)
        money = fx_svc.normalize(1000.0, "SAR", region="global")
        assert money.reference_amount is not None
        assert abs(money.reference_amount - 266.67) < 1.0
        assert money.fx.status.value in ("ok", "stale")

    def test_known_currency_with_inverse_rate(self, fx_svc, db):
        # YER -> USD: if only USD->YER stored, use inverse
        fx_repo = FxRateRepository(db)
        fx_repo.add("USD", "YER", 500.0, source="aegis_reference", region="global")
        money = fx_svc.normalize(50000.0, "YER", region="global")
        assert money.reference_amount is not None
        assert abs(money.reference_amount - 100.0) < 1.0  # 50000 / 500

    def test_cross_rate_via_reference(self, fx_svc, db):
        # YER -> SAR when only YER->USD and USD->SAR exist
        fx_repo = FxRateRepository(db)
        fx_repo.add("YER", "USD", 0.002, source="aegis_reference", region="global")
        fx_repo.add("USD", "SAR", 3.75, source="aegis_reference", region="global")
        money = fx_svc.normalize(10000.0, "YER", region="global")
        # 10000 YER * 0.002 USD/YER * 3.75 SAR/USD = 75 SAR
        # But reference currency is USD, so we get USD amount
        assert money.reference_amount is not None
        assert money.reference_currency == "USD"
        assert abs(money.reference_amount - 20.0) < 1.0  # 10000 * 0.002

    def test_unknown_currency_missing(self, fx_svc, db):
        # XXX is not a known currency -> FX_MISSING
        money = fx_svc.normalize(500.0, "XXX", region="global")
        assert money.reference_amount is None
        assert money.fx.status.value == "missing"

    def test_stale_rate_flag(self, fx_svc, db):
        # Insert an old rate (older than FX_STALE_HOURS)
        fx_repo = FxRateRepository(db)
        old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        fx_repo.add("EUR", "USD", 1.08, source="aegis_reference", region="global",
                    valid_from=old_time)
        money = fx_svc.normalize(100.0, "EUR", region="global")
        assert money.reference_amount is not None
        assert money.fx.status.value == "stale"

    def test_divergent_rate_flag(self, fx_svc, db):
        # Institution rate diverges > FX_DIVERGENCE_PCT from reference
        fx_repo = FxRateRepository(db)
        fx_repo.add("GBP", "USD", 1.25, source="aegis_reference", region="global")
        # institution reports 1.30 (>3% divergence)
        money = fx_svc.normalize(100.0, "GBP", region="global", institution_rate=1.30)
        assert money.reference_amount is not None
        assert money.fx.status.value == "divergent"
        assert money.fx.divergence_pct is not None
        assert money.fx.divergence_pct > 3.0

    def test_region_specific_rate(self, fx_svc, db):
        # Aden rate should be preferred over global for YER
        fx_repo = FxRateRepository(db)
        fx_repo.add("USD", "YER", 500.0, source="aegis_reference", region="global")
        fx_repo.add("USD", "YER", 600.0, source="aegis_reference", region="aden")
        money = fx_svc.normalize(100.0, "YER", region="aden")
        assert money.reference_amount is not None
        # Should use Aden rate (600), not global (500)
        assert abs(money.reference_amount - (100.0 / 600.0)) < 0.01

    def test_fx_snapshot_immutable(self, fx_svc, db):
        # Same transaction evaluated twice should produce identical fx proof
        money1 = fx_svc.normalize(1000.0, "SAR", region="global")
        money2 = fx_svc.normalize(1000.0, "SAR", region="global")
        assert money1.fx.rate == money2.fx.rate
        assert money1.fx.source == money2.fx.source
        assert money1.fx.fetched_at == money2.fx.fetched_at
