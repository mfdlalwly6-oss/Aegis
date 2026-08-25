"""FX service tests — conversion, staleness, missing, divergent, cross-rate, inverse."""

from datetime import UTC, datetime, timedelta

import pytest
from app.db import Database
from app.repositories.currency_repo import CurrencyRepository
from app.repositories.fx_rate_repo import FxRateRepository
from app.services.fx_service import FxService


@pytest.fixture()
def fx_db(tmp_path, monkeypatch):
    """Fresh SQLite DB per test (same pattern as conftest)."""
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AEGIS_DB_PATH", str(tmp_path / "aegis-test.db"))
    monkeypatch.setenv("AEGIS_ENV", "development")
    monkeypatch.setenv("AEGIS_DB_DRIVER", "sqlite")  # isolate: never touch live PG
    from app.core.config import clear_settings_cache

    clear_settings_cache()
    # Explicit path: module-level `settings` in app.db binds at import time, so
    # clear_settings_cache() alone does NOT rebind it — without this the fixture
    # can fall back to the shared default DB (/tmp/aegis-data/aegis.db).
    db = Database(str(tmp_path / "aegis-test.db"))
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
    fx_repo.add("YER", "USD", 0.000636942675, source="aegis_reference", region="global")  # 1/1570
    fx_repo.add("YER", "USD", 0.001666666667, source="aegis_reference", region="aden")  # 1/600
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
        # EUR -> USD direct pair; EUR must be registered as a known currency first
        CurrencyRepository(fx_db).add("EUR", "Euro", minor_unit=2)
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
        CurrencyRepository(fx_db).add("GBP", "Pound Sterling", minor_unit=2)
        fx_repo = FxRateRepository(fx_db)
        row = fx_repo.add("GBP", "USD", 1.25, source="aegis_reference", region="global")
        # Backdate fetched_at so the rate is older than FX_STALE_HOURS
        old_time = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
        fx_db.execute("UPDATE fx_rates SET fetched_at=? WHERE rate_id=?", (old_time, row["rate_id"]))
        money = fx_svc.normalize(100.0, "GBP", region="global")
        assert money.reference_amount is not None
        assert money.fx.status.value == "stale"

    def test_divergent_rate_flag(self, fx_svc, fx_db):
        CurrencyRepository(fx_db).add("JPY", "Japanese Yen", minor_unit=0)
        fx_repo = FxRateRepository(fx_db)
        fx_repo.add("JPY", "USD", 0.0067, source="aegis_reference", region="global")
        # institution reports 0.0070 (>3% divergence from 0.0067)
        money = fx_svc.normalize(10000.0, "JPY", region="global", institution_rate=0.0070)
        assert money.reference_amount is not None
        assert money.fx.status.value == "divergent"
        assert money.fx.divergence_pct is not None
        assert money.fx.divergence_pct > 3.0

    def test_region_specific_rate(self, fx_svc):
        # aden rate 1/600 -> 166.67 USD; global rate 1/1570 -> 63.69 USD. Must differ.
        money = fx_svc.normalize(100000.0, "YER", region="aden")
        assert money.reference_amount is not None
        assert abs(money.reference_amount - 166.6667) < 0.01
        assert money.fx.region == "aden"
        money_g = fx_svc.normalize(100000.0, "YER", region="global")
        assert abs(money_g.reference_amount - 63.6943) < 0.01
        assert money_g.fx.region == "global"
        assert abs(money_g.reference_amount - money.reference_amount) > 100.0

    def test_fx_snapshot_immutable(self, fx_svc):
        money1 = fx_svc.normalize(1000.0, "SAR", region="global")
        money2 = fx_svc.normalize(1000.0, "SAR", region="global")
        assert money1.fx.rate == money2.fx.rate
        assert money1.fx.source == money2.fx.source
        assert money1.fx.fetched_at == money2.fx.fetched_at
