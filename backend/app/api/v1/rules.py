"""Rules API — list platform+tenant rules, reload from payload (owner only)."""
from fastapi import APIRouter, Depends, Request

from app.api.deps import get_registry, require_owner

router = APIRouter()


@router.get("/")
def list_rules(request: Request, owner=Depends(require_owner), registry=Depends(get_registry)):
    return [{"id": r.id, "name": r.name, "severity": r.severity.value,
             "score": r.score, "enabled": r.enabled, "tags": r.tags}
            for r in registry.rule_engine.rules]


@router.post("/reload")
def reload_rules(body: dict, request: Request,
                 owner=Depends(require_owner), registry=Depends(get_registry)):
    rules = body.get("rules", [])
    for rule in rules:
        registry.rule_repo.upsert(rule, tenant_id=rule.get("tenant_id"))
    all_rules = registry.rule_repo.list_all()
    registry.rule_engine.reload(all_rules)
    registry.audit.log(None, "owner", "rules.reloaded", "rules", None,
                       getattr(request.state, "request_id", None), {"count": len(all_rules)})
    return {"reloaded": len(all_rules)}
