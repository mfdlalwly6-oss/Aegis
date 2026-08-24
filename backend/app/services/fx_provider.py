"""FX rate provider abstraction — pluggable source for reference rates.

Implementations:
- StaticFxProvider: reads from fx_rates table (current behavior, deterministic).
- HttpFxProvider: fetches from an external rate API (configurable URL).
- CachedFxProvider: wraps any provider with TTL cache.

The service (fx_service.py) consumes whatever provider is wired in registry.py.
Adding a real bank/Oracle API later = one new provider class, zero schema change.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Protocol

import httpx


class FxRateResult:
    def __init__(self, base_ccy: str, quote_ccy: str, rate: float, *,
                 rate_type: str = "mid", source: str = "provider",
                 region: str = "global", spread_pct: float | None = None,
                 valid_from: datetime | None = None, valid_to: datetime | None = None):
        self.base_ccy = base_ccy
        self.quote_ccy = quote_ccy
        self.rate = rate
        self.rate_type = rate_type
        self.source = source
        self.region = region
        self.spread_pct = spread_pct
        self.valid_from = valid_from or datetime.now(timezone.utc)
        self.valid_to = valid_to


class FxProvider(Protocol):
    def fetch(self, base_ccy: str, quote_ccy: str, *, region: str = "global") -> FxRateResult | None: ...


class StaticFxProvider:
    """Reads from the existing fx_rates table. Deterministic, offline, test-safe."""
    def __init__(self, fx_repo):
        self.fx_repo = fx_repo

    def fetch(self, base_ccy: str, quote_ccy: str, *, region: str = "global") -> FxRateResult | None:
        row = self.fx_repo.latest_valid(base_ccy, quote_ccy, region=region)
        if row is None:
            return None
        return FxRateResult(
            base_ccy, quote_ccy, float(row["rate"]),
            rate_type=row.get("rate_type", "mid"),
            source=row.get("source", "aegis_reference"),
            region=row.get("region", region),
            spread_pct=row.get("spread_pct"),
            valid_from=datetime.fromisoformat(row["valid_from"]) if row.get("valid_from") else None,
            valid_to=datetime.fromisoformat(row["valid_to"]) if row.get("valid_to") else None,
        )


class HttpFxProvider:
    """Fetches from an external rate API (e.g., exchangerate.host, bank API).
    Configurable via env: FX_PROVIDER_URL. Falls back gracefully on network failure."""
    def __init__(self, base_url: str, api_key: str = "", timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def fetch(self, base_ccy: str, quote_ccy: str, *, region: str = "global") -> FxRateResult | None:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                params = {"base": base_ccy.upper(), "symbols": quote_ccy.upper()}
                if self.api_key:
                    params["api_key"] = self.api_key
                r = client.get(f"{self.base_url}/latest", params=params)
                r.raise_for_status()
                data = r.json()
                rate = data.get("rates", {}).get(quote_ccy.upper())
                if rate is None:
                    return None
                return FxRateResult(
                    base_ccy, quote_ccy, float(rate),
                    rate_type="mid", source="provider:http",
                    region=region,
                )
        except Exception:
            return None


class CachedFxProvider:
    """TTL cache wrapper around any FxProvider."""
    def __init__(self, provider: FxProvider, ttl_sec: int = 300):
        self.provider = provider
        self.ttl = ttl_sec
        self._cache: dict[tuple[str, str, str], tuple[float, FxRateResult]] = {}

    def fetch(self, base_ccy: str, quote_ccy: str, *, region: str = "global") -> FxRateResult | None:
        key = (base_ccy.upper(), quote_ccy.upper(), region)
        now = time.monotonic()
        if key in self._cache:
            ts, result = self._cache[key]
            if now - ts < self.ttl:
                return result
        result = self.provider.fetch(base_ccy, quote_ccy, region=region)
        if result is not None:
            self._cache[key] = (now, result)
        return result


def build_provider(fx_repo, config_url: str = "", config_key: str = "", cache_ttl: int = 300) -> FxProvider:
    """Factory: returns StaticFxProvider if no URL configured, else Cached(HttpFxProvider)."""
    if config_url:
        return CachedFxProvider(HttpFxProvider(config_url, config_key), ttl_sec=cache_ttl)
    return StaticFxProvider(fx_repo)
