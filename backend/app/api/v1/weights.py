"""Risk-weight admin endpoints — platform default + per-tenant overrides.

Weight profiles drive the fusion engine's component blending (rules / ml /
graph / aml / behavior). Resolution: an ACTIVE tenant override wins; otherwise
the single platform default row. Disabling or deleting an override reverts the
tenant to the default instantly (no row copy — inheritance is live).

Every mutation is audit-logged with old/new values so the full history of the
risk posture is preserved; historical decisions keep the weights they were
scored with (weights only affect future decisions).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_registry, require_owner

router = APIRouter()


class WeightsIn(BaseModel):
    rules: float = Field(ge=0.0, le=1.0)
    ml: float = Field(ge=0.0, le=1.0)
    graph: float = Field(ge=0.0, le=1.0)
    aml: float = Field(ge=0.0, le=1.0)
    behavior: float = Field(ge=0.0, le=1.0)
    note: str | None = Field(default=None, max_length=200)

    def validate_sum(self) -> None:
        total = self.rules + self.ml + self.graph + self.aml + self.behavior
        if abs(total - 1.0) >= 0.0001:
            raise HTTPException(
                status_code=422,
                detail=f"weights must sum to 1.0 (got {round(total, 4)})",
            )

    def as_dict(self) -> dict:
        return {
            "rules": self.rules, "ml": self.ml, "graph": self.graph,
            "aml": self.aml, "behavior": self.behavior,
        }


# ---------------------------------------------------------------- default ---
@router.get("/admin/weights/default")
def get_default_weights(owner=Depends(require_owner), registry=Depends(get_registry)):
    return registry.weights.get_default()


@router.put("/admin/weights/default")
def update_default_weights(body: WeightsIn, owner=Depends(require_owner), registry=Depends(get_registry)):
    body.validate_sum()
    before = registry.weights.get_default()
    try:
        after = registry.weights.update_default(actor=owner, note=body.note, **body.as_dict())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    registry.audit.log(
        "platform", owner, "weights.default.updated", "weights",
        after["profile_id"], None,
        {"old": {k: before[k] for k in ("rules", "ml", "graph", "aml", "behavior")},
         "new": {k: after[k] for k in ("rules", "ml", "graph", "aml", "behavior")},
         "note": body.note},
    )
    return after


# --------------------------------------------------------------- overrides --
@router.get("/admin/weights/overrides")
def list_weight_overrides(owner=Depends(require_owner), registry=Depends(get_registry)):
    rows = registry.weights.list_overrides()
    names = {t["tenant_id"]: t.get("name") for t in registry.tenants.list()}
    for r in rows:
        r["tenant_name"] = names.get(r["tenant_id"], r["tenant_id"])
    return {"total": len(rows), "overrides": rows}


@router.get("/admin/tenants/{tenant_id}/weights")
def get_tenant_weights(tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)):
    if not registry.tenants.get(tenant_id):
        raise HTTPException(status_code=404, detail="tenant_not_found")
    override = registry.weights.get_override(tenant_id)
    effective = registry.weights.effective_weights(tenant_id)
    return {"tenant_id": tenant_id, "override": override, "effective": effective}


@router.put("/admin/tenants/{tenant_id}/weights")
def set_tenant_weights(tenant_id: str, body: WeightsIn, owner=Depends(require_owner), registry=Depends(get_registry)):
    if not registry.tenants.get(tenant_id):
        raise HTTPException(status_code=404, detail="tenant_not_found")
    body.validate_sum()
    before = registry.weights.get_override(tenant_id)
    try:
        after = registry.weights.set_override(tenant_id, actor=owner, note=body.note, active=True, **body.as_dict())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    registry.audit.log(
        tenant_id, owner,
        "weights.override.updated" if before else "weights.override.created",
        "weights", after["profile_id"], None,
        {"old": ({k: before[k] for k in ("rules", "ml", "graph", "aml", "behavior")} if before else None),
         "new": {k: after[k] for k in ("rules", "ml", "graph", "aml", "behavior")},
         "note": body.note},
    )
    return after


@router.post("/admin/tenants/{tenant_id}/weights/disable")
def disable_tenant_weights(tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)):
    after = registry.weights.set_override_active(tenant_id, False)
    if not after:
        raise HTTPException(status_code=404, detail="weight_override_not_found")
    registry.audit.log(tenant_id, owner, "weights.override.disabled", "weights",
                       after["profile_id"], None, {"tenant_id": tenant_id})
    return after


@router.post("/admin/tenants/{tenant_id}/weights/enable")
def enable_tenant_weights(tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)):
    after = registry.weights.set_override_active(tenant_id, True)
    if not after:
        raise HTTPException(status_code=404, detail="weight_override_not_found")
    registry.audit.log(tenant_id, owner, "weights.override.enabled", "weights",
                       after["profile_id"], None, {"tenant_id": tenant_id})
    return after


@router.delete("/admin/tenants/{tenant_id}/weights")
def delete_tenant_weights(tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)):
    before = registry.weights.get_override(tenant_id)
    if not before:
        raise HTTPException(status_code=404, detail="weight_override_not_found")
    registry.weights.delete_override(tenant_id)
    registry.audit.log(
        tenant_id, owner, "weights.override.deleted", "weights",
        before["profile_id"], None,
        {"old": {k: before[k] for k in ("rules", "ml", "graph", "aml", "behavior")}},
    )
    return {"deleted": True, "tenant_id": tenant_id, "reverted_to": "default"}
