"""Transaction ingestion & scoring API — owner-secured direct scoring."""
from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_registry, require_owner
from app.api.v1.webhook import normalize_transaction

router = APIRouter()


@router.post("/score", summary="Score a transaction synchronously (owner only)")
async def score_transaction(
    body: dict,
    request: Request,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    tenant_id = body.get("tenant_id") or (body.get("transaction") or {}).get("tenant_id")

    if not tenant_id:
        raise HTTPException(400, "tenant_id_required")

    tenant = registry.tenants.get(tenant_id)
    if not tenant:
        raise HTTPException(404, "tenant_not_found")

    tx = normalize_transaction(body, tenant_id)

    idem_key = request.headers.get("x-idempotency-key")
    if not idem_key:
        idem_key = f"{tenant_id}:{tx.tx_id}"

    return await registry.orchestrator.evaluate_and_persist(
        tx,
        body,
        actor="owner",
        request_id=getattr(request.state, "request_id", None),
        idempotency_key=idem_key,
    )


@router.get("/{tx_id}", summary="Fetch a scored transaction + its decision")
async def get_transaction(
    tx_id: str,
    request: Request,
    owner=Depends(require_owner),
    registry=Depends(get_registry),
):
    tx = registry.transactions.get(tx_id)
    if not tx:
        raise HTTPException(404, "not_found")

    decision = registry.decisions.get_by_tx(tx_id)

    return {
        "transaction": tx,
        "decision": decision,
    }