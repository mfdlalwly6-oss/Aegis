"""Decision-threshold admin endpoints — platform default + per-tenant overrides.

Threshold profiles drive the decision engine's challenge / review / block cutoffs
and the FX-missing action. Resolution: an ACTIVE tenant override wins; otherwise
the single platform default row. Disabling or deleting an override reverts the
tenant to the default instantly (live inheritance — no row copy).

Every mutation is audit-logged with old/new values so the full history of the
risk posture is preserved; historical decisions keep the thresholds they were
scored with (thresholds only affect future decisions). Safety bounds + ordering
(challenge<=review<=block) and the no-silent-allow FX rule are enforced here and
in the repository and via DB CHECK constraints.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_registry, require_owner

router = APIRouter()

_TH_KEYS = ("challenge", "review", "block")


class ThresholdsIn(BaseModel):
    challenge: float = Field(ge=0.20, le=0.50)
    review: float = Field(ge=0.40, le=0.75)
    block: float = Field(ge=0.60, le=0.95)
    fx_missing_action: str | None = Field(default=None)
    note: str | None = Field(default=None, max_length=200)

    def validate(self) -> None:
        if not (self.challenge <= self.review <= self.block):
            raise HTTPException(
                status_code=422,
                detail=(
                    "thresholds must satisfy challenge<=review<=block "
                    f"(got {self.challenge}/{self.review}/{self.block})"
                ),
            )
        if self.fx_missing_action is not None and self.fx_missing_action not in ("review", "block"):
            raise HTTPException(
                status_code=422,
                detail="fx_missing_action must be 'review' or 'block' (never a silent allow)",
            )

    def as_dict(self) -> dict:
        return {"challenge": self.challenge, "review": self.review, "block": self.block}


def _snap(d: dict) -> dict:
    return {k: d[k] for k in _TH_KEYS} | {"fx_missing_action": d.get("fx_missing_action")}


# ---------------------------------------------------------------- default ---
@router.get("/admin/thresholds/default")
def get_default_thresholds(owner=Depends(require_owner), registry=Depends(get_registry)):
    return registry.thresholds.get_default()


@router.put("/admin/thresholds/default")
def update_default_thresholds(body: ThresholdsIn, owner=Depends(require_owner), registry=Depends(get_registry)):
    body.validate()
    before = registry.thresholds.get_default()
    try:
        after = registry.thresholds.update_default(
            actor=owner, note=body.note, fx_missing_action=body.fx_missing_action, **body.as_dict()
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    registry.audit.log(
        "platform", owner, "thresholds.default.updated", "thresholds",
        after["profile_id"], None,
        {"old": _snap(before), "new": _snap(after), "note": body.note},
    )
    return after


# --------------------------------------------------------------- overrides --
@router.get("/admin/thresholds/overrides")
def list_threshold_overrides(owner=Depends(require_owner), registry=Depends(get_registry)):
    rows = registry.thresholds.list_overrides()
    names = {t["tenant_id"]: t.get("name") for t in registry.tenants.list()}
    for r in rows:
        r["tenant_name"] = names.get(r["tenant_id"], r["tenant_id"])
    return {"total": len(rows), "overrides": rows}


@router.get("/admin/tenants/{tenant_id}/thresholds")
def get_tenant_thresholds(tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)):
    if not registry.tenants.get(tenant_id):
        raise HTTPException(status_code=404, detail="tenant_not_found")
    override = registry.thresholds.get_override(tenant_id)
    effective = registry.thresholds.effective_thresholds(tenant_id)
    return {"tenant_id": tenant_id, "override": override, "effective": effective}


@router.put("/admin/tenants/{tenant_id}/thresholds")
def set_tenant_thresholds(tenant_id: str, body: ThresholdsIn, owner=Depends(require_owner), registry=Depends(get_registry)):
    if not registry.tenants.get(tenant_id):
        raise HTTPException(status_code=404, detail="tenant_not_found")
    body.validate()
    before = registry.thresholds.get_override(tenant_id)
    try:
        after = registry.thresholds.set_override(
            tenant_id, actor=owner, note=body.note, active=True,
            fx_missing_action=body.fx_missing_action, **body.as_dict(),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    registry.audit.log(
        tenant_id, owner,
        "thresholds.override.updated" if before else "thresholds.override.created",
        "thresholds", after["profile_id"], None,
        {"old": (_snap(before) if before else None), "new": _snap(after), "note": body.note},
    )
    return after


@router.post("/admin/tenants/{tenant_id}/thresholds/disable")
def disable_tenant_thresholds(tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)):
    after = registry.thresholds.set_override_active(tenant_id, False)
    if not after:
        raise HTTPException(status_code=404, detail="threshold_override_not_found")
    registry.audit.log(tenant_id, owner, "thresholds.override.disabled", "thresholds",
                       after["profile_id"], None, {"tenant_id": tenant_id})
    return after


@router.post("/admin/tenants/{tenant_id}/thresholds/enable")
def enable_tenant_thresholds(tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)):
    after = registry.thresholds.set_override_active(tenant_id, True)
    if not after:
        raise HTTPException(status_code=404, detail="threshold_override_not_found")
    registry.audit.log(tenant_id, owner, "thresholds.override.enabled", "thresholds",
                       after["profile_id"], None, {"tenant_id": tenant_id})
    return after


@router.delete("/admin/tenants/{tenant_id}/thresholds")
def delete_tenant_thresholds(tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)):
    before = registry.thresholds.get_override(tenant_id)
    if not before:
        raise HTTPException(status_code=404, detail="threshold_override_not_found")
    registry.thresholds.delete_override(tenant_id)
    registry.audit.log(
        tenant_id, owner, "thresholds.override.deleted", "thresholds",
        before["profile_id"], None, {"old": _snap(before)},
    )
    return {"deleted": True, "tenant_id": tenant_id, "reverted_to": "default"}
