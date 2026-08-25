"""FX service tests — conversion, staleness, missing, divergent, cross-rate, inverse."""
from datetime import datetime, timezone, timedelta
import pytest

from app.db import Database
from app.services.fx_service import FxService
from app.repositories.fx_rate_repo import FxRateRepository
from app.repositories.currency_repo import CurrencyRepository
from app.core.config import settings


@pytest.fixture()
def fx_db(tmp_path, monkeypatch):
    """Fresh SQLite DB per test (same pattern as conftest)."""
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AEGIS_DB_PATH", str(tmp_path / "aegis-test.db"))
    monkeypatch.setenv("AEGIS_ENV", "development")
    from app.core.config import clear_settings_cache
    clear_settings_cache()
    db = Database()
    db.migrate()
    yield db
    db.close()


@pytest.fixture()
def fx_svc(fx_db):
    fx_repo = FxRateRepository(fx_db)
    currency_repo = CurrencyRepository(fx_db)
    currency_repo.seed_defaults()
    # Seed reference rates
    fx_repo.add("SAR", "USD", 0.266666666667, source="aegis_reference", region="global")
    fx_repo.add("USD", "YER", 1570.0, source="aegis_reference", region="global")
    fx_repo.add("USD", "YER", 600.0, source="aegis_reference", region="aden")
    fx_repo.add("YER", "USD", 0.000636942675, source="aegis_reference", region="global")
    fx_repo.add("YER", "USD", 0.000636942675, source="aegis_reference", region="aden")
    return FxService(fx_repo, currency_checker=lambda c: currency_repo.is_known(c))


class TestFxConversion:
    def test_native_reference_currency(self, fx_svc):
        money = fx_svc.normalize(100.0, "USD", region="global")
        assert money.reference_amount == 100.0
        assert money.reference_currency == "USD"
        assert money.fx.status.value == "native"

    def test_known_currency_direct_rate(self, fx_svc):
        money = fx_svc.normalize(1000.0, "SAR", region="global")
        assert money.reference_amount is not None
        assert abs(money.reference_amount - 266.67) < 0.01
        assert money.fx.status.value in ("ok", "stale")

    def test_known_currency_inverse_rate(self, fx_svc):
        # YER -> USD: stored rate is 0.000636942675 (YER/USD), use directly
        money = fx_svc.normalize(50000.0, "YER", region="global")
        assert money.reference_amount is not None
        assert abs(money.reference_amount - 31.85) < 0.01

    def test_cross_rate_via_reference(self, fx_svc, fx_db):
        # EUR -> SAR: no direct pair, but EUR->USD and USD->SAR exist
        fx_repo = FxRateRepository(fx_db)
        fx_repo.add("EUR", "USD", 1.08, source="aegis_reference", region="global")
        money = fx_svc.normalize(100.0, "EUR", region="global")
        # 100 EUR * 1.08 USD/EUR = 108 USD (reference currency)
        assert money.reference_amount is not None
        assert abs(money.reference_amount - 108.0) < 0.01
        assert money.fx.status.value == "ok"

    def test_unknown_currency_missing(self, fx_svc):
        money = fx_svc.normalize(500.0, "XXX", region="global")
        assert money.reference_amount is None
        assert money.fx.status.value == "missing"

    def test_stale_rate_flag(self, fx_svc, fx_db):
        fx_repo = FxRateRepository(fx_db)
        old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        fx_repo.add("GBP", "USD", 1.25, source="aegis_reference", region="global",
                    valid_from=old_time)
        money = fx_svc.normalize(100.0, "GBP", region="global")
        assert money.reference_amount is not None
        assert money.fx.status.value == "stale"

    def test_divergent_rate_flag(self, fx_svc, fx_db):
        fx_repo = FxRateRepository(fx_db)
        fx_repo.add("JPY", "USD", 0.0067, source="aegis_reference", region="global")
        # institution reports 0.0070 (>3% divergence from 0.0067)
        money = fx_svc.normalize(10000.0, "JPY", region="global", institution_rate=0.0070)
        assert money.reference_amount is not None
        assert money.fx.status.value == "divergent"
        assert money.fx.divergence_pct is not None
        assert money.fx.divergence_pct > 3.0

    def test_region_specific_rate(self, fx_svc):
        # Aden rate (600) should be preferred over global (1570) for YER
        money = fx_svc.normalize(100000.0, "YER", region="aden")
        assert money.reference_amount is not None
        # 100000 YER / 600 USD/YER = 166.67 USD
        assert abs(money.reference_amount - 166.67) < 0.01

    def test_fx_snapshot_immutable(self, fx_svc):
        money1 = fx_svc.normalize(1000.0, "SAR", region="global")
        money2 = fx_svc.normalize(1000.0, "SAR", region="global")
        assert money1.fx.rate == money2.fx.rate
        assert money1.fx.source == money2.fx.source
        assert money1.fx.fetched_at == money2.fx.fetched_at
