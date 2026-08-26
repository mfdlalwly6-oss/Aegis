"""Alerts API — real DB-backed alerts."""

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_registry, require_owner

router = APIRouter()


@router.get("/")
def list_alerts(
    status: str | None = None,
    limit: int = 100,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    return registry.alerts.list(status=status, limit=limit)


@router.post("/{alert_id}/status")
def update_alert(
    alert_id: str,
    body: dict,
    request: Request,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    alert = registry.alerts.update_status(
        alert_id, body.get("status", "open"), assignee=body.get("assignee")
    )
    if not alert:
        raise HTTPException(404, "not_found")
    registry.audit.log(
        alert["tenant_id"],
        "owner",
        "alert.status_changed",
        "alert",
        alert_id,
        getattr(request.state, "request_id", None),
        {"status": body.get("status")},
    )
    return alert
