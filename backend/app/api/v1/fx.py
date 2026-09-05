"""FX & Currency admin endpoints (TASK 2/11) — list currencies, list/add FX rates.

Rates are append-only: adding a new rate never mutates history, so historical
decisions keep the exact rate snapshot they were decided with.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_registry, require_owner

router = APIRouter()


class CurrencyIn(BaseModel):
    code: str = Field(min_length=3, max_length=3)
    name: str = Field(min_length=1, max_length=100)
    minor_unit: int = Field(default=2, ge=0, le=4)
    round_unit: float = Field(default=1000, gt=0)
    active: bool = True


class FxRateIn(BaseModel):
    base_ccy: str = Field(min_length=3, max_length=3)
    quote_ccy: str = Field(min_length=3, max_length=3)
    rate: float = Field(gt=0)
    rate_type: str = Field(default="mid", pattern="^(mid|bid|ask)$")
    source: str = Field(default="aegis_reference", max_length=50)
    region: str = Field(default="global", max_length=50)
    spread_pct: float | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    # None => platform-wide (applies to every tenant). A tenant id => Tenant FX
    # Override that outranks platform rates for that tenant only.
    tenant_id: str | None = None


@router.get("/admin/fx/currencies")
def list_currencies(owner=Depends(require_owner), registry=Depends(get_registry)):
    # include inactive too for management view
    all_rows = registry.db.query("SELECT * FROM currencies ORDER BY code")
    return {"total": len(all_rows), "currencies": all_rows}


@router.post("/admin/fx/currencies", status_code=201)
def add_currency(body: CurrencyIn, owner=Depends(require_owner), registry=Depends(get_registry)):
    existing = registry.currencies.get(body.code)
    row = registry.currencies.add(
        body.code,
        body.name,
        minor_unit=body.minor_unit,
        round_unit=body.round_unit,
        active=body.active,
    )
    registry.audit.log(
        "platform",
        "owner",
        "currency.upserted",
        "currency",
        body.code.upper(),
        None,
        {
            "code": body.code.upper(),
            "minor_unit": body.minor_unit,
            "active": body.active,
            "existed": bool(existing),
        },
    )
    return row


@router.get("/admin/fx/rates")
def list_rates(tenant_id: str | None = None, active_only: bool = False,
               owner=Depends(require_owner), registry=Depends(get_registry)):
    q = "SELECT * FROM fx_rates WHERE 1=1"
    args: list = []
    if tenant_id:
        q += " AND tenant_id=?"
        args.append(tenant_id)
    if active_only:
        q += " AND (valid_to IS NULL OR valid_to>?)"
        from datetime import UTC, datetime
        args.append(datetime.now(UTC).isoformat())
    q += " ORDER BY fetched_at DESC LIMIT 500"
    rows = registry.db.query(q, tuple(args))
    return {"total": len(rows), "rates": rows}


@router.post("/admin/fx/rates", status_code=201)
def add_rate(body: FxRateIn, owner=Depends(require_owner), registry=Depends(get_registry)):
    if not registry.currencies.is_known(body.base_ccy):
        raise HTTPException(422, f"unknown_base_currency:{body.base_ccy.upper()}")
    if not registry.currencies.is_known(body.quote_ccy):
        raise HTTPException(422, f"unknown_quote_currency:{body.quote_ccy.upper()}")
    if body.tenant_id and not registry.tenants.get(body.tenant_id):
        raise HTTPException(404, "tenant_not_found")
    row = registry.fx_rates.add(
        body.base_ccy,
        body.quote_ccy,
        body.rate,
        rate_type=body.rate_type,
        source=body.source,
        region=body.region,
        spread_pct=body.spread_pct,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        tenant_id=body.tenant_id,
    )
    scope = "tenant_override" if body.tenant_id else "platform"
    registry.audit.log(
        "platform",
        "owner",
        "fx_rate.added",
        "fx_rate",
        row["rate_id"],
        None,
        {
            "pair": f"{body.base_ccy.upper()}/{body.quote_ccy.upper()}",
            "rate": body.rate,
            "source": body.source,
            "scope": scope,
            "tenant_id": body.tenant_id,
        },
    )
    return row


@router.post("/admin/fx/rates/{rate_id}/end")
def end_rate(rate_id: str, owner=Depends(require_owner), registry=Depends(get_registry)):
    """Safely retire a rate (audit-friendly): close its validity window instead of
    deleting, so historical snapshots that reference it stay intact."""
    from datetime import UTC, datetime
    row = registry.fx_rates.get(rate_id)
    if not row:
        raise HTTPException(404, "rate_not_found")
    now = datetime.now(UTC).isoformat()
    registry.db.execute("UPDATE fx_rates SET valid_to=? WHERE rate_id=?", (now, rate_id))
    registry.audit.log(
        "platform", "owner", "fx_rate.ended", "fx_rate", rate_id, None,
        {"pair": f"{row['base_ccy']}/{row['quote_ccy']}", "rate": row["rate"],
         "source": row["source"], "tenant_id": row.get("tenant_id"), "ended_at": now},
    )
    return registry.fx_rates.get(rate_id)

# ─────────────────────────── Reference Rate Sets (4-tier FX) ─────────────────
class FxRefSetIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    usd_yer: float = Field(gt=0)
    sar_yer: float = Field(gt=0)
    tenant_ids: list[str] = []


@router.get("/admin/fx/reference-sets")
def list_reference_sets(owner=Depends(require_owner), registry=Depends(get_registry)):
    return {"total": len(registry.fx_reference_repo.list_sets()),
            "sets": registry.fx_reference_repo.list_sets()}


@router.post("/admin/fx/reference-sets", status_code=201)
def create_reference_set(body: FxRefSetIn, owner=Depends(require_owner), registry=Depends(get_registry)):
    for tid in body.tenant_ids:
        if not registry.tenants.get(tid):
            raise HTTPException(404, f"tenant_not_found:{tid}")
    s = registry.fx_reference_repo.create_set(body.name, body.usd_yer, body.sar_yer)
    for tid in body.tenant_ids:
        registry.fx_reference_repo.assign(s["set_id"], tid)
    registry.audit.log("platform", "owner", "fx_reference_set.created", "fx_reference_set",
                       s["set_id"], None,
                       {"name": body.name, "usd_yer": body.usd_yer, "sar_yer": body.sar_yer,
                        "tenants": body.tenant_ids})
    return registry.fx_reference_repo.get_set(s["set_id"])


class FxRefSetUpdate(BaseModel):
    usd_yer: float | None = Field(default=None, gt=0)
    sar_yer: float | None = Field(default=None, gt=0)


@router.put("/admin/fx/reference-sets/{set_id}")
def update_reference_set(set_id: str, body: FxRefSetUpdate,
                         owner=Depends(require_owner), registry=Depends(get_registry)):
    cur = registry.fx_reference_repo.get_set(set_id)
    if not cur:
        raise HTTPException(404, "reference_set_not_found")
    row = registry.fx_reference_repo.update_set(set_id, body.usd_yer, body.sar_yer)
    registry.audit.log("platform", "owner", "fx_reference_set.updated", "fx_reference_set",
                       set_id, {"usd_yer": cur["usd_yer"], "sar_yer": cur["sar_yer"]},
                       {"usd_yer": row["usd_yer"], "sar_yer": row["sar_yer"]})
    return row


@router.post("/admin/fx/reference-sets/{set_id}/status")
def set_reference_status(set_id: str, active: bool = True,
                         owner=Depends(require_owner), registry=Depends(get_registry)):
    row = registry.fx_reference_repo.set_active(set_id, active)
    if not row:
        raise HTTPException(404, "reference_set_not_found")
    registry.audit.log("platform", "owner",
                       "fx_reference_set.activated" if active else "fx_reference_set.deactivated",
                       "fx_reference_set", set_id, None, {"active": active})
    return row


class FxRefAssignIn(BaseModel):
    tenant_ids: list[str] = Field(min_length=1)


@router.post("/admin/fx/reference-sets/{set_id}/assign")
def assign_reference_set(set_id: str, body: FxRefAssignIn,
                         owner=Depends(require_owner), registry=Depends(get_registry)):
    if not registry.fx_reference_repo.get_set(set_id):
        raise HTTPException(404, "reference_set_not_found")
    moves = []
    for tid in body.tenant_ids:
        if not registry.tenants.get(tid):
            raise HTTPException(404, f"tenant_not_found:{tid}")
        moves.append(registry.fx_reference_repo.assign(set_id, tid))
    registry.audit.log("platform", "owner", "fx_reference_set.assigned", "fx_reference_set",
                       set_id, None, {"tenants": body.tenant_ids, "moves": moves})
    return {"set_id": set_id, "moves": moves}


@router.post("/admin/fx/reference-sets/unassign/{tenant_id}")
def unassign_reference(tenant_id: str, owner=Depends(require_owner), registry=Depends(get_registry)):
    removed = registry.fx_reference_repo.unassign(tenant_id)
    registry.audit.log("platform", "owner", "fx_reference_set.unassigned", "tenant",
                       tenant_id, None, {"removed": removed})
    return {"tenant_id": tenant_id, "removed": removed}


# ── General rate management (§13) ────────────────────────────────────────────
@router.post("/admin/fx/general/activate")
def activate_general(body: dict, owner=Depends(require_owner), registry=Depends(get_registry)):
    """Make one general (tenant_id IS NULL) rate the active one for its pair+region;
    all other general rates for the same pair+region become inactive (§13)."""
    rid = body.get("rate_id")
    if not rid:
        raise HTTPException(400, "rate_id_required")
    row = registry.fx_rates.get(rid)
    if not row:
        raise HTTPException(404, "rate_not_found")
    if row.get("tenant_id"):
        raise HTTPException(422, "not_a_general_rate")
    # deactivate siblings (same pair+region, platform-wide), keep history intact
    registry.db.execute(
        "UPDATE fx_rates SET active=0 WHERE base_ccy=? AND quote_ccy=? AND region=? AND tenant_id IS NULL",
        (row["base_ccy"], row["quote_ccy"], row["region"]),
    )
    registry.db.execute("UPDATE fx_rates SET active=1 WHERE rate_id=?", (rid,))
    registry.audit.log("platform", "owner", "fx.general_activated", "fx_rate", rid, None,
                       {"pair": f"{row['base_ccy']}/{row['quote_ccy']}", "region": row["region"]})
    return registry.fx_rates.get(rid)


@router.get("/admin/fx/general/users")
def general_rate_users(owner=Depends(require_owner), registry=Depends(get_registry)):
    """§14: tenants that would currently resolve to the GENERAL tier (no manual
    override and no active reference-set assignment)."""
    tenants = registry.db.query("SELECT tenant_id, name, status FROM tenants WHERE status != 'deleted'")
    users = []
    for t in tenants:
        tid = t["tenant_id"]
        manual = registry.fx.fx_repo.latest_valid("USD", "YER", at=None, tenant_id=tid, tenant_only=True)
        refset = registry.fx.reference_repo.set_for_tenant(tid) if registry.fx.reference_repo else None
        if not manual and not refset:
            users.append({"tenant_id": tid, "name": t.get("name"), "status": t.get("status")})
    return {"total": len(users), "tenants": users}

