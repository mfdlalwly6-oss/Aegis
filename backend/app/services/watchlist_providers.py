"""Watchlist external-data providers — pluggable, source-tracked, sync-audited.

A provider fetches entries from an external source and normalizes them into
AEGIS watchlist entries. Each provider:
  * declares its source tag (stored on every entry for provenance),
  * is idempotent (re-syncing updates/re-activates instead of duplicating),
  * records a row in watchlist_sync_log (added/updated/removed/error),
  * fails gracefully (HTTP/network errors -> raised -> logged -> 502 to caller).

Add a new provider by subclassing ``WatchlistProvider`` and registering it in
``PROVIDERS`` — no other change is required (the API resolves by name).
"""
from __future__ import annotations

import csv
import io
import json
import urllib.request
import urllib.error
from typing import Any

try:
    from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
    _HAVE_TENACITY = True
except Exception:  # tenacity optional — provide a tiny equivalent retry decorator
    _HAVE_TENACITY = False

    def retry(*, stop=None, wait=None, retry=None):  # type: ignore
        import functools, time
        attempts = getattr(stop, "stop", None) or 3

        def deco(fn):
            @functools.wraps(fn)
            def wrapper(*a, **k):
                last = None
                for _ in range(attempts):
                    try:
                        return fn(*a, **k)
                    except Exception as e:  # noqa: BLE001
                        last = e
                        time.sleep(0.5)
                raise last
            return wrapper
        return deco

    def retry_if_exception_type(*a, **k):  # type: ignore
        return None

    def stop_after_attempt(n):  # type: ignore
        class _S: stop = n
        return _S()

    def wait_exponential(**k):  # type: ignore
        return None


class ProviderError(Exception):
    pass


class WatchlistProvider:
    """Base provider. ``name`` is the registry key; ``source`` is stamped on entries."""

    name = "base"
    source = "external"

    async def fetch(self, cfg: dict[str, Any]) -> list[dict]:
        raise NotImplementedError

    async def sync(self, repo, tenant_id: str, list_type: str, cfg: dict[str, Any]) -> dict:
        rows = await self.fetch(cfg)
        added = updated = 0
        seen: set[str] = set()
        for r in rows:
            value = (r.get("value") or "").strip()
            if not value:
                continue
            seen.add(value.upper())
            existed = repo.db.query_one(
                "SELECT id FROM watchlist WHERE tenant_id=? AND list_type=? AND value=?",
                (tenant_id, list_type, value.upper()),
            )
            repo.add_entry(
                list_type, value.upper(), tenant_id=tenant_id,
                entity_kind=r.get("entity_kind", "entity"),
                aliases=r.get("aliases", []), dob=r.get("dob"),
                country=r.get("country"), identifiers=r.get("identifiers", {}),
                source=self.source, external_id=r.get("external_id"),
                meta=r.get("meta", {}),
            )
            if existed:
                updated += 1
            else:
                added += 1
        # soft-remove entries from this source that disappeared from the feed
        removed = 0
        current = repo.list_all(list_type=list_type, tenant_id=tenant_id)
        for e in current:
            if e.get("source") == self.source and (e.get("value") or "").upper() not in seen:
                repo.set_status(e["id"], "disabled", tenant_id)
                removed += 1
        return {"added": added, "updated": updated, "removed": removed,
                "total_fetched": len(rows)}


class GenericCsvUrlProvider(WatchlistProvider):
    """Fetch a CSV over HTTP(S) and import it. Columns: value[,aliases,country,
    dob,entity_kind,external_id]. Auth via optional Authorization header."""

    name = "generic_csv_url"
    source = "provider:csv_url"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=5),
           retry=retry_if_exception_type((urllib.error.URLError, TimeoutError, ProviderError)))
    def _get(self, url: str, headers: dict[str, str]) -> bytes:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read(5_000_001)

    async def fetch(self, cfg: dict[str, Any]) -> list[dict]:
        url = (cfg or {}).get("url", "")
        if not url:
            raise ProviderError("url_required")
        headers = {}
        if cfg.get("auth_header"):
            headers["Authorization"] = cfg["auth_header"]
        raw = self._get(url, headers)
        text = raw.decode("utf-8-sig", errors="replace")
        rdr = csv.DictReader(io.StringIO(text))
        if not rdr.fieldnames or "value" not in rdr.fieldnames:
            raise ProviderError("csv_requires_value_column")
        out = []
        for row in rdr:
            aliases = [a.strip() for a in (row.get("aliases") or "").split("|") if a.strip()]
            out.append({
                "value": row.get("value", ""),
                "aliases": aliases,
                "country": (row.get("country") or "").strip().upper() or None,
                "dob": (row.get("dob") or "").strip() or None,
                "entity_kind": (row.get("entity_kind") or "entity").strip(),
                "external_id": (row.get("external_id") or "").strip() or None,
                "meta": {k: v for k, v in row.items()
                         if k not in {"value", "aliases", "country", "dob", "entity_kind", "external_id"} and v},
            })
        return out


PROVIDERS: dict[str, WatchlistProvider] = {
    p.name: p for p in (GenericCsvUrlProvider(),)
}


def get_provider(name: str) -> WatchlistProvider | None:
    return PROVIDERS.get(name)
