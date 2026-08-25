"""Cases API — investigation management."""

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_registry, require_owner

router = APIRouter()


@router.get("/")
def list_cases(
    status: str | None = None, limit: int = 100, owner=Depends(require_owner), registry=Depends(get_registry)
):
    return registry.cases.list(status=status, limit=limit)


@router.get("/{case_id}")
def get_case(case_id: str, owner=Depends(require_owner), registry=Depends(get_registry)):
    case = registry.cases.get(case_id)
    if not case:
        raise HTTPException(404, "not_found")
    return case


@router.post("/{case_id}/notes")
def add_note(
    case_id: str, body: dict, request: Request, owner=Depends(require_owner), registry=Depends(get_registry)
):
    case = registry.cases.add_note(case_id, body.get("author", "owner"), body.get("text", ""))
    if not case:
        raise HTTPException(404, "not_found")
    registry.audit.log(
        case["tenant_id"],
        "owner",
        "case.note_added",
        "case",
        case_id,
        getattr(request.state, "request_id", None),
        {},
    )
    return case


@router.post("/{case_id}/status")
def update_case_status(
    case_id: str, body: dict, request: Request, owner=Depends(require_owner), registry=Depends(get_registry)
):
    case = registry.cases.update_status(case_id, body.get("status", "open"), assignee=body.get("assignee"))
    if not case:
        raise HTTPException(404, "not_found")
    registry.audit.log(
        case["tenant_id"],
        "owner",
        "case.status_changed",
        "case",
        case_id,
        getattr(request.state, "request_id", None),
        {"status": body.get("status")},
    )
    return case
