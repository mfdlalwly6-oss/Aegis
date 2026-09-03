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
