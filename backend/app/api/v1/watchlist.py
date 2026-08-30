"""Watchlist management API — role-scoped, tenant-isolated, audited.

Access model (analyzed from app/api/deps.py):
- Platform OWNER  (require_owner)  → manage ANY tenant's list + the shared
  'platform' defaults; may import CSV for any tenant; may trigger provider sync.
- INSTITUTION     (require_merchant: merchant/institution_owner/tenant_admin)
                                  → manage ONLY their own tenant's custom + pep
                                  lists and import CSV for themselves; read the
                                  effective (platform+own) sanctions list.
- INVESTIGATOR    (require_investigator) → read-only view of the effective
                                  watchlist that produced alerts (no mutation).

Every mutation writes an audit event (actor + tenant + resource + detail).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.deps import get_registry, require_investigator, require_merchant, require_owner
from app.services.watchlist_importer import import_csv
from app.services.watchlist_providers import get_provider

router = APIRouter()

_TYPES = {"sanctions", "pep", "high_risk_country", "custom"}
# institution (bank) may author these types; sanctions defaults are platform-owned
_INSTITUTION_WRITABLE = {"pep", "custom", "high_risk_country"}


class EntryIn(BaseModel):
    list_type: str
    value: str
    entity_kind: str = "entity"
    aliases: list[str] = []
    dob: str | None = None
    country: str | None = None
    identifiers: dict = {}
    source: str = "manual"
    external_id: str | None = None
    meta: dict = {}
    valid_from: str | None = None
    valid_to: str | None = None


def _validate_type(list_type: str) -> None:
    if list_type not in _TYPES:
        raise HTTPException(422, f"invalid_list_type:{list_type}")


def _row_public(r: dict) -> dict:
    return {k: r.get(k) for k in (
        "id", "list_type", "value", "entity_kind", "aliases_json", "dob", "country",
        "identifiers_json", "source", "external_id", "meta_json", "status",
        "valid_from", "valid_to", "created_at", "updated_at", "tenant_id")}


# ─────────────────────────────── OWNER (platform) ────────────────────────────
@router.get("/admin/watchlist")
def owner_list(tenant_id: str | None = None, list_type: str | None = None,
               owner=Depends(require_owner), registry=Depends(get_registry)):
    rows = registry.watchlist_repo.list_for_owner(tenant_id=tenant_id, list_type=list_type)
    return {"total": len(rows), "entries": [_row_public(r) for r in rows]}


@router.post("/admin/tenants/{tenant_id}/watchlist", status_code=201)
def owner_add(tenant_id: str, body: EntryIn, owner=Depends(require_owner), registry=Depends(get_registry)):
    _validate_type(body.list_type)
    if not registry.tenants.get(tenant_id) and tenant_id != "platform":
        raise HTTPException(404, "tenant_not_found")
    row = registry.watchlist_repo.add_entry(
        body.list_type, body.value, tenant_id=tenant_id, entity_kind=body.entity_kind,
        aliases=body.aliases, dob=body.dob, country=body.country, identifiers=body.identifiers,
        source=body.source, external_id=body.external_id, meta=body.meta,
        valid_from=body.valid_from, valid_to=body.valid_to)
    registry.audit.log(tenant_id, "owner", "watchlist.entry_added", "watchlist",
                       str(row.get("id")), None,
                       {"list_type": body.list_type, "value": body.value, "source": body.source})
    return _row_public(row)


@router.post("/admin/watchlist/{entry_id}/status")
def owner_set_status(entry_id: int, body: dict, tenant_id: str,
                     owner=Depends(require_owner), registry=Depends(get_registry)):
    status = (body or {}).get("status", "")
    if status not in ("active", "disabled"):
        raise HTTPException(422, "invalid_status")
    row = registry.watchlist_repo.set_status(entry_id, status, tenant_id)
    if not row:
        raise HTTPException(404, "entry_not_found")
    registry.audit.log(tenant_id, "owner", f"watchlist.entry_{status}", "watchlist",
                       str(entry_id), None, {"value": row.get("value")})
    return _row_public(row)


@router.post("/admin/tenants/{tenant_id}/watchlist/import")
async def import_watchlist(tenant_id: str, file: UploadFile = File(...),
                           owner=Depends(require_owner), registry=Depends(get_registry)):
    if file.content_type not in {"text/csv", "application/csv", "application/vnd.ms-excel"}:
        raise HTTPException(415, "csv_required")
    data = await file.read(2_000_001)
    if len(data) > 2_000_000:
        raise HTTPException(413, "file_too_large")
    if not registry.tenants.get(tenant_id) and tenant_id != "platform":
        raise HTTPException(404, "tenant_not_found")
    try:
        summary = import_csv(registry.watchlist_repo, tenant_id, data)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    registry.audit.log(tenant_id, "owner", "watchlist.imported", "watchlist", tenant_id, None, summary)
    return summary


# ─────────────────────────────── PROVIDER SYNC (owner) ───────────────────────
@router.post("/admin/tenants/{tenant_id}/watchlist/sync")
async def owner_sync(tenant_id: str, body: dict, owner=Depends(require_owner), registry=Depends(get_registry)):
    provider_name = (body or {}).get("provider", "")
    list_type = (body or {}).get("list_type", "custom")
    _validate_type(list_type)
    provider = get_provider(provider_name)
    if not provider:
        raise HTTPException(400, f"unknown_provider:{provider_name}")
    if not registry.tenants.get(tenant_id) and tenant_id != "platform":
        raise HTTPException(404, "tenant_not_found")
    log_id = registry.watchlist_repo.sync_log_start(provider_name, tenant_id)
    try:
        summary = await provider.sync(registry.watchlist_repo, tenant_id, list_type, body or {})
        registry.watchlist_repo.sync_log_finish(
            log_id, status="ok",
            added=int(summary.get("added", 0)), updated=int(summary.get("updated", 0)),
            removed=int(summary.get("removed", 0)), detail=summary)
        registry.audit.log(tenant_id, "owner", "watchlist.synced", "watchlist", tenant_id,
                           None, {"provider": provider_name, **summary})
        return {"status": "ok", "provider": provider_name, **summary}
    except Exception as e:
        registry.watchlist_repo.sync_log_finish(log_id, status="failed", error=str(e))
        registry.audit.log(tenant_id, "owner", "watchlist.sync_failed", "watchlist", tenant_id,
                           None, {"provider": provider_name, "error": str(e)})
        raise HTTPException(502, f"provider_sync_failed:{e}") from e


@router.get("/admin/tenants/{tenant_id}/watchlist/sync-log")
def owner_sync_log(tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)):
    return {"entries": registry.watchlist_repo.sync_history(tenant_id)}


# ─────────────────────────────── INSTITUTION (bank) ──────────────────────────
@router.get("/merchant/watchlist")
def merchant_list(list_type: str | None = None, claims=Depends(require_merchant),
                  registry=Depends(get_registry)):
    tid = claims["tenant_id"]
    # effective view = platform defaults + own tenant entries
    rows = registry.watchlist_repo.list_all(list_type=list_type, tenant_id=tid)
    platform = registry.watchlist_repo.list_all(list_type=list_type, tenant_id="platform")
    return {"total": len(rows) + len(platform),
            "entries": [_row_public(r) for r in rows + platform]}


@router.post("/merchant/watchlist", status_code=201)
def merchant_add(body: EntryIn, claims=Depends(require_merchant), registry=Depends(get_registry)):
    _validate_type(body.list_type)
    if body.list_type not in _INSTITUTION_WRITABLE:
        raise HTTPException(403, "list_type_not_writable_by_institution")
    tid = claims["tenant_id"]
    row = registry.watchlist_repo.add_entry(
        body.list_type, body.value, tenant_id=tid, entity_kind=body.entity_kind,
        aliases=body.aliases, dob=body.dob, country=body.country, identifiers=body.identifiers,
        source=body.source, external_id=body.external_id, meta=body.meta,
        valid_from=body.valid_from, valid_to=body.valid_to)
    registry.audit.log(tid, claims.get("sub", "merchant"), "watchlist.entry_added",
                       "watchlist", str(row.get("id")), None,
                       {"list_type": body.list_type, "value": body.value})
    return _row_public(row)


@router.post("/merchant/watchlist/{entry_id}/status")
def merchant_set_status(entry_id: int, body: dict, claims=Depends(require_merchant),
                        registry=Depends(get_registry)):
    status = (body or {}).get("status", "")
    if status not in ("active", "disabled"):
        raise HTTPException(422, "invalid_status")
    tid = claims["tenant_id"]
    row = registry.watchlist_repo.set_status(entry_id, status, tid)
    if not row:
        raise HTTPException(404, "entry_not_found")
    registry.audit.log(tid, claims.get("sub", "merchant"), f"watchlist.entry_{status}",
                       "watchlist", str(entry_id), None, {"value": row.get("value")})
    return _row_public(row)


@router.post("/merchant/watchlist/import")
async def merchant_import(file: UploadFile = File(...), claims=Depends(require_merchant),
                          registry=Depends(get_registry)):
    if file.content_type not in {"text/csv", "application/csv", "application/vnd.ms-excel"}:
        raise HTTPException(415, "csv_required")
    data = await file.read(2_000_001)
    if len(data) > 2_000_000:
        raise HTTPException(413, "file_too_large")
    tid = claims["tenant_id"]
    try:
        summary = import_csv(registry.watchlist_repo, tid, data)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    registry.audit.log(tid, claims.get("sub", "merchant"), "watchlist.imported",
                       "watchlist", tid, None, summary)
    return summary


# ─────────────────────────────── INVESTIGATOR (read-only) ────────────────────
@router.get("/investigator/watchlist")
def investigator_list(list_type: str | None = None, claims=Depends(require_investigator),
                      registry=Depends(get_registry)):
    tid = claims["tenant_id"]
    rows = registry.watchlist_repo.list_all(list_type=list_type, tenant_id=tid)
    platform = registry.watchlist_repo.list_all(list_type=list_type, tenant_id="platform")
    return {"total": len(rows) + len(platform),
            "entries": [_row_public(r) for r in rows + platform]}
