"""Post-transaction feedback — labels lifecycle: decision → outcome → label → dataset."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_registry
from app.security import generate_id, verify_signature

router = APIRouter()

VALID_OUTCOMES = {
    "confirmed_fraud", "confirmed_legitimate", "suspected_fraud",
    "chargeback", "dispute", "unknown",
}


@router.post("/feedback", summary="Institution post-transaction outcome feedback")
async def submit_feedback(request: Request, registry=Depends(get_registry)):
    api_key = request.headers.get("x-api-key", "")
    signature = request.headers.get("x-wallet-signature", "")
    if not api_key or not signature:
        raise HTTPException(401, "missing_auth_headers")
    registry.db.set_tenant("platform")
    tenant = registry.tenants.by_api_key(api_key)
    if not tenant:
        raise HTTPException(401, "invalid_api_key")
    raw = await request.body()
    if not verify_signature(tenant["hmac_secret"], raw, signature):
        raise HTTPException(401, "invalid_signature")
    registry.db.set_tenant(tenant["tenant_id"])

    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "invalid_json") from None
    tx_id = body.get("tx_id")
    outcome = str(body.get("outcome", "")).lower()
    if not tx_id:
        raise HTTPException(400, "tx_id_required")
    if outcome not in VALID_OUTCOMES:
        raise HTTPException(400, f"invalid_outcome: must be one of {sorted(VALID_OUTCOMES)}")
    source = body.get("source") or "institution"

    fid = generate_id("fb")
    now = datetime.now(UTC).isoformat()
    try:
        registry.db.execute(
            "INSERT INTO feedback (id,tx_id,tenant_id,outcome,source,occurred_at,"
            "confidence,case_id,notes,created_at) VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(tx_id,outcome,source) DO NOTHING",
            (fid, tx_id, tenant["tenant_id"], outcome, source,
             body.get("occurred_at"), body.get("confidence"),
             body.get("case_id"), body.get("notes"), now),
        )
    except Exception as e:
        raise HTTPException(500, f"feedback_store_error:{type(e).__name__}") from None
    registry.audit.log(tenant["tenant_id"], tenant.get("name", "tenant"),
                       "feedback.received", "transaction", tx_id, None,
                       {"outcome": outcome, "source": source})
    return {"status": "recorded", "feedback_id": fid, "tx_id": tx_id, "outcome": outcome}
