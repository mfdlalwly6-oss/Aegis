"""Rules API — list platform+tenant rules, reload from payload (owner only)."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.deps import get_registry, require_owner

router = APIRouter()


class ToggleBody(BaseModel):
    enabled: bool


@router.get("/")
def list_rules(request: Request, owner=Depends(require_owner), registry=Depends(get_registry)):
    return [
        {
            "id": r.id,
            "name": r.name,
            "severity": r.severity.value,
            "score": r.score,
            "enabled": r.enabled,
            "tags": r.tags,
        }
        for r in registry.rule_engine.rules
    ]


@router.get("/{rule_id}")
def rule_detail(rule_id: str, owner=Depends(require_owner), registry=Depends(get_registry)):
    for r in registry.rule_engine.rules:
        if r.id == rule_id:
            return {
                "id": r.id,
                "name": r.name,
                "severity": r.severity.value,
                "score": r.score,
                "enabled": r.enabled,
                "tags": r.tags,
                "description": r.description,
                "when": r.when,
            }
    raise HTTPException(404, "rule_not_found")


@router.post("/{rule_id}/toggle")
def rule_toggle(
    rule_id: str,
    body: ToggleBody,
    request: Request,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    """Enable/disable a rule — persisted to DB then hot-reloaded into the engine."""
    current = None
    for r in registry.rule_engine.rules:
        if r.id == rule_id:
            current = r
            break
    if current is None:
        raise HTTPException(404, "rule_not_found")
    registry.rule_repo.upsert(
        {
            "id": current.id,
            "name": current.name,
            "severity": current.severity.value,
            "score": current.score,
            "enabled": body.enabled,
            "tags": current.tags,
            "description": current.description,
            "when": current.when,
        },
        tenant_id=None,
    )
    registry.rule_engine.reload(registry.rule_repo.list_all())
    registry.audit.log(
        None,
        "owner",
        "rules.toggled",
        "rules",
        rule_id,
        getattr(request.state, "request_id", None),
        {"enabled": body.enabled},
    )
    return {"id": rule_id, "enabled": body.enabled}


@router.post("/reload")
def reload_rules(body: dict, request: Request, owner=Depends(require_owner), registry=Depends(get_registry)):
    rules = body.get("rules", [])
    for rule in rules:
        registry.rule_repo.upsert(rule, tenant_id=rule.get("tenant_id"))
    all_rules = registry.rule_repo.list_all()
    registry.rule_engine.reload(all_rules)
    registry.audit.log(
        None,
        "owner",
        "rules.reloaded",
        "rules",
        None,
        getattr(request.state, "request_id", None),
        {"count": len(all_rules)},
    )
    return {"reloaded": len(all_rules)}
