"""Rules API — list platform+tenant rules, reload from payload (owner only)."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.deps import get_registry, require_owner

router = APIRouter()


class ToggleBody(BaseModel):
    enabled: bool


@router.get("/")
def list_rules(request: Request, owner=Depends(require_owner), registry=Depends(get_registry)):
    """Platform rules only (tenant_id IS NULL). Tenant-specific custom rules live
    in rule_overrides and are surfaced per-institution via /rules/overrides —
    they must never appear in this platform list."""
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "severity": r["severity"],
            "score": r["score"],
            "enabled": r["enabled"],
            "tags": r["tags"],
        }
        for r in registry.rule_repo.list_all()  # platform rules only
    ]


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
    registry.rule_engine.reload(registry.rule_repo.list_for_engine())
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
def reload_rules(
    body: dict, request: Request, owner=Depends(require_owner), registry=Depends(get_registry)
):
    rules = body.get("rules", [])
    for rule in rules:
        registry.rule_repo.upsert(rule, tenant_id=rule.get("tenant_id"))
    all_rules = registry.rule_repo.list_for_engine()
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


# ─────────────────────────── Per-tenant rule customization (owner) ───────────
class RuleOverrideBody(BaseModel):
    enabled: bool | None = None
    score: float | None = None
    severity: str | None = None
    name: str | None = None
    description: str | None = None
    when: dict | None = None
    tags: list[str] | None = None


@router.get("/overrides")
def list_all_overrides(owner=Depends(require_owner), registry=Depends(get_registry)):
    """All banks that have rule customization, with their overrides."""
    return registry.rule_repo.list_overrides()


@router.get("/overrides/{tenant_id}")
def tenant_effective_rules(
    tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)
):
    """The exact rule set that governs this tenant (platform + its overrides),
    plus the raw overrides for editing."""
    if not registry.tenants.get(tenant_id):
        raise HTTPException(404, "tenant_not_found")
    return {
        "tenant_id": tenant_id,
        "effective": registry.rule_repo.effective_rules_for(tenant_id),
        "overrides": registry.rule_repo.list_overrides(tenant_id),
    }


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


@router.put("/overrides/{tenant_id}/{rule_id}")
def upsert_override(
    tenant_id: str,
    rule_id: str,
    body: RuleOverrideBody,
    request: Request,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    """Create/update a bank's customization of a rule (or a tenant-only rule).
    Platform rules are never mutated — the override lives in rule_overrides and
    only affects this tenant's scoring."""
    if not registry.tenants.get(tenant_id):
        raise HTTPException(404, "tenant_not_found")
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(422, "empty_override")
    registry.rule_repo.upsert_override(tenant_id, rule_id, patch, actor="owner")
    registry.rule_engine.reload(registry.rule_repo.list_for_engine())
    registry.audit.log(
        tenant_id, "owner", "rules.override_set", "rules", rule_id,
        getattr(request.state, "request_id", None), patch,
    )
    return {"tenant_id": tenant_id, "rule_id": rule_id, "override": patch}


@router.delete("/overrides/{tenant_id}/{rule_id}")
def delete_override(
    tenant_id: str,
    rule_id: str,
    request: Request,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    """Remove a bank's customization — the tenant falls back to the platform rule."""
    removed = registry.rule_repo.delete_override(tenant_id, rule_id)
    if not removed:
        raise HTTPException(404, "override_not_found")
    registry.rule_engine.reload(registry.rule_repo.list_for_engine())
    registry.audit.log(
        tenant_id, "owner", "rules.override_removed", "rules", rule_id,
        getattr(request.state, "request_id", None), {},
    )
    return {"tenant_id": tenant_id, "rule_id": rule_id, "removed": True}
