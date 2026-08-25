from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

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
    registry.audit.log(tenant_id, "owner", "watchlist.imported", "watchlist", tenant_id, None, summary)
    return summary
