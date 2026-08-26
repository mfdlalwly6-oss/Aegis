from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import get_registry, require_owner
from app.services.watchlist_importer import import_csv

router = APIRouter()


@router.post("/admin/tenants/{tenant_id}/watchlist/import")
async def import_watchlist(
    tenant_id: str,
    file: UploadFile = File(...),
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    if file.content_type not in {"text/csv", "application/csv", "application/vnd.ms-excel"}:
        raise HTTPException(415, "csv_required")
    data = await file.read(2_000_001)
    if len(data) > 2_000_000:
        raise HTTPException(413, "file_too_large")
    if not registry.tenants.get(tenant_id):
        raise HTTPException(404, "tenant_not_found")
    try:
        summary = import_csv(registry.watchlist_repo, tenant_id, data)
    except ValueError as e:
        raise HTTPException(422, str(e))
    registry.audit.log(
        tenant_id, "owner", "watchlist.imported", "watchlist", tenant_id, None, summary
    )
    return summary


class _WatchEntryIn(BaseModel):
    list_type: str = Field(min_length=1, max_length=50)
    value: str = Field(min_length=1, max_length=300)
    tenant_id: str = "platform"
    meta: dict | None = None


@router.get("/admin/watchlist")
def list_watchlist(
    list_type: str | None = None,
    tenant_id: str = "platform",
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    rows = registry.watchlist_repo.list_all(list_type=list_type, tenant_id=tenant_id)
    return {"total": len(rows), "entries": rows}


@router.post("/admin/watchlist", status_code=201)
def add_watchlist_entry(
    body: _WatchEntryIn, owner=Depends(require_owner), registry=Depends(get_registry)
):
    created = registry.watchlist_repo.add(
        body.list_type, body.value, body.meta, tenant_id=body.tenant_id
    )
    registry.audit.log(
        body.tenant_id,
        "owner",
        "watchlist.entry_added",
        "watchlist",
        body.value,
        None,
        {"list_type": body.list_type, "value": body.value, "created": bool(created)},
    )
    return {"ok": True, "created": bool(created), "list_type": body.list_type, "value": body.value}
