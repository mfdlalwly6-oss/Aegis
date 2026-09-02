"""Fraud check webhook — used by any connected bank/wallet via api_key + HMAC-SHA256.
Pipeline: auth → signature → idempotency → normalize → orchestrator → persist → respond.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_registry
from app.core.config import settings
from app.models.schemas import BehaviorSignals, DeviceContext, GeoPoint, Transaction
from app.security import verify_signature

router = APIRouter()

DEFAULT_REVIEW_MESSAGE = "تم تعليق العملية مؤقتًا للمراجعة الأمنية. يرجى التواصل مع البنك أو المؤسسة المالية لإتمام المراجعة."


def normalize_transaction(body: dict, tenant_id: str) -> Transaction:
    """Normalize any wallet/bank payload into the canonical Transaction schema."""
    src = body.get("transaction", body)
    ctx = body.get("context", {})

    device_raw = src.get("device") or ctx.get("device") or {}
    if ctx.get("device_id") and not device_raw.get("device_id"):
        device_raw["device_id"] = ctx["device_id"]
    if ctx.get("ip") and not device_raw.get("ip"):
        device_raw["ip"] = ctx["ip"]

    behavior_raw = src.get("behavior") or ctx.get("behavior") or {}
    geo_raw = src.get("geo") or ctx.get("geo") or None

    ts_raw = src.get("timestamp") or src.get("ts") or body.get("timestamp")
    try:
        timestamp = (
            datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            if ts_raw
            else datetime.now(UTC)
        )
    except Exception:
        timestamp = datetime.now(UTC)

    amount = src.get("amount")
    if amount is None:
        raise HTTPException(400, "amount_required")
    # BUG3 fix: validate numeric amount up-front so a malformed value yields a
    # clean 400 (not an uncaught ValueError -> 500) at the float() call below.
    try:
        amount_f = float(amount)
    except (TypeError, ValueError):
        raise HTTPException(400, "amount_invalid") from None
    # G08/DEF-02: the Transaction schema enforces amount > 0 (Field(gt=0)).
    # Reject non-positive amounts here with a clean 400 instead of letting the
    # pydantic ValidationError bubble up as an uncaught 500.
    if amount_f <= 0:
        raise HTTPException(400, "amount_must_be_positive") from None

    metadata = dict(src.get("metadata") or {})
    for k in ("velocity", "account", "beneficiary", "geo", "customer"):
        if isinstance(ctx.get(k), dict):
            metadata.setdefault(k, ctx[k])
    for k in (
        "account_age_days",
        "seconds_since_password_change",
        "previous_declines",
        "previous_chargebacks",
        "high_risk_merchant",
        "impossible_travel",
        "offshore",
        "emulator",
        "rooted",
        "mfa_recently_disabled",
        "distinct_merchants_1h",
        "card_declines_1h",
        "billing_country",
    ):
        if k in ctx:
            metadata.setdefault(k, ctx[k])
    for section in ("velocity", "account"):
        if isinstance(metadata.get(section), dict):
            for k, v in metadata.pop(section).items():
                metadata.setdefault(k, v)
    if isinstance(metadata.get("beneficiary"), dict):
        b = metadata.pop("beneficiary")
        if "is_new" in b:
            metadata.setdefault("beneficiary_is_new_hint", b["is_new"])
        for k in ("offshore", "country"):
            if k in b:
                metadata.setdefault(k, b[k])
    if isinstance(metadata.get("geo"), dict):
        g = metadata.pop("geo")
        for k in ("impossible_travel", "fatf_high_risk"):
            if k in g:
                metadata.setdefault(k, g[k])
    if isinstance(metadata.get("customer"), dict):
        metadata.setdefault("billing_country", metadata["customer"].get("billing_country"))
        metadata.pop("customer", None)

    return Transaction(
        tx_id=str(src.get("tx_id") or src.get("transaction_id") or uuid.uuid4()),
        tenant_id=tenant_id,
        timestamp=timestamp,
        channel=src.get("channel", "wallet"),
        amount=float(amount),
        currency=src.get("currency", "USD"),
        sender_account_id=str(
            src.get("sender_account_id")
            or src.get("account_id")
            or src.get("from_account")
            or src.get("sender")
            or "unknown_sender"
        ),
        sender_user_id=src.get("sender_user_id") or src.get("user_id"),
        beneficiary_account_id=str(
            src.get("beneficiary_account_id")
            or src.get("to_account")
            or src.get("receiver")
            or src.get("merchant_id")
            or "unknown_beneficiary"
        ),
        beneficiary_user_id=src.get("beneficiary_user_id"),
        beneficiary_country=src.get("beneficiary_country") or metadata.get("country"),
        # entity names for watchlist screening (from sender/beneficiary/customer blocks)
        sender_name=src.get("sender_name") or (ctx.get("sender") or {}).get("name")
        or (metadata.get("sender") or {}).get("name"),
        beneficiary_name=src.get("beneficiary_name") or (ctx.get("beneficiary") or {}).get("name")
        or (metadata.get("beneficiary") or {}).get("name"),
        customer_name=src.get("customer_name") or (ctx.get("customer") or {}).get("name")
        or (metadata.get("customer") or {}).get("name"),
        customer_dob=src.get("customer_dob") or (ctx.get("customer") or {}).get("dob")
        or (metadata.get("customer") or {}).get("dob"),
        customer_country=src.get("customer_country") or (ctx.get("customer") or {}).get("country")
        or (metadata.get("customer") or {}).get("country"),
        customer_identifiers=src.get("customer_identifiers") or (ctx.get("customer") or {}).get("identifiers")
        or (metadata.get("customer") or {}).get("identifiers") or {},
        merchant_id=src.get("merchant_id"),
        merchant_name=src.get("merchant_name"),
        device=DeviceContext(
            **{k: v for k, v in device_raw.items() if k in DeviceContext.model_fields}
        )
        if device_raw
        else None,
        behavior=BehaviorSignals(
            **{k: v for k, v in behavior_raw.items() if k in BehaviorSignals.model_fields}
        )
        if behavior_raw
        else None,
        geo=GeoPoint(**geo_raw) if geo_raw and "lat" in geo_raw and "lon" in geo_raw else None,
        session_id=src.get("session_id") or ctx.get("session_id"),
        metadata=metadata,
    )


def _apply_fx(registry, tx: Transaction, body: dict) -> Transaction:
    """Populate FX fields on a Transaction after creation. Called by webhook/score endpoints.
    Mutates tx in place; returns tx for chaining."""
    src = body.get("transaction", body)
    ctx = body.get("context", {})
    ccy = (tx.currency or "USD").upper()
    region = src.get("region") or ctx.get("region") or settings.FX_DEFAULT_REGION
    institution_rate = src.get("institution_rate") or ctx.get("institution_rate")
    institution_rate = float(institution_rate) if institution_rate else None
    money = registry.fx.normalize(tx.amount, ccy, region=region, institution_rate=institution_rate)
    tx.reference_amount = money.reference_amount
    tx.reference_currency = money.reference_currency
    tx.fx_status = money.fx.status.value if money.fx else None
    tx.fx_snapshot_id = getattr(money.fx, "rate_id", None) if money.fx else None
    return tx


@router.post("/wallet/webhook", summary="Multi-tenant fraud check webhook")
async def fraud_webhook(request: Request, registry=Depends(get_registry)):
    request_id = getattr(request.state, "request_id", None)
    api_key = request.headers.get("x-api-key", "")
    signature = request.headers.get("x-wallet-signature", "")
    if not api_key or not signature:
        raise HTTPException(401, "missing_auth_headers")

    # Pre-auth lookup must run in platform/system context: RLS hides other
    # tenants' rows and the pooled connection's GUC may be stale from a
    # previous request (set_config with is_local=false is session-scoped).
    registry.db.set_tenant("platform")
    tenant = registry.tenants.by_api_key(api_key)
    if not tenant:
        legacy = settings.LEGACY_SECRET
        if legacy:
            tenant = {"tenant_id": "legacy", "name": "Legacy", "hmac_secret": legacy}
        else:
            registry.audit.log(
                None,
                api_key[:10],
                "authentication.failure",
                "wallet_webhook",
                None,
                request_id,
                {"reason": "invalid_api_key"},
            )
            raise HTTPException(401, "invalid_api_key")

    raw = await request.body()
    if not verify_signature(tenant["hmac_secret"], raw, signature):
        registry.audit.log(
            tenant["tenant_id"],
            tenant["name"],
            "authentication.failure",
            "wallet_webhook",
            None,
            request_id,
            {"reason": "invalid_signature"},
        )
        raise HTTPException(401, "invalid_signature")
    registry.db.set_tenant(tenant["tenant_id"])  # authenticated tenant RLS context

    # Replay guard on transaction timestamp: reject far-future (>5min) or very
    # stale (>72h) events — bounds replay and clock-drift abuse. Reads the
    # timestamp from the raw (already signature-verified) body.
    from datetime import datetime

    try:
        _payload = json.loads(raw.decode("utf-8"))
        _src = _payload.get("transaction", _payload) if isinstance(_payload, dict) else {}
        body_ts = (
            (_payload.get("timestamp") if isinstance(_payload, dict) else None)
            or _src.get("timestamp")
            or _src.get("ts")
        )
        if body_ts:
            ts = datetime.fromisoformat(str(body_ts).replace("Z", "+00:00"))
            skew = (ts - datetime.now(UTC)).total_seconds()
            if skew > 300:
                raise HTTPException(422, "timestamp_in_future")
            if skew < -72 * 3600:
                raise HTTPException(422, "timestamp_stale")
    except HTTPException:
        raise
    except Exception:
        pass  # unparseable payloads are rejected later by schema validation

    # Suspended/deleted tenants are hard-blocked at ingestion time.
    if tenant.get("status") != "active":
        registry.audit.log(
            tenant["tenant_id"],
            tenant["name"],
            "transaction.rejected",
            "wallet_webhook",
            None,
            request_id,
            {"reason": "tenant_suspended"},
        )
        raise HTTPException(403, "tenant_suspended")

    try:
        body = json.loads(raw)
    except Exception:
        raise HTTPException(400, "invalid_json")

    tx = normalize_transaction(body, tenant["tenant_id"])
    tx = _apply_fx(registry, tx, body)

    idem_key = request.headers.get("x-idempotency-key") or f"{tenant['tenant_id']}:{tx.tx_id}"
    result = await registry.orchestrator.evaluate_and_persist(
        tx,
        body,
        actor=tenant["name"],
        request_id=request_id,
        idempotency_key=idem_key,
    )
    if result.pop("duplicate", False):
        return {
            "tx_id": result["tx_id"],
            "decision": result["decision"],
            "risk_score": result["risk_score"],
            "duplicate": True,
        }

    review_message = None
    if result["decision"] == "review":
        review_message = tenant.get("review_message") or DEFAULT_REVIEW_MESSAGE

    return {
        "tx_id": result["tx_id"],
        "decision": result["decision"],
        "risk_score": result["risk_score"],
        "risk_band": result["risk_band"],
        "typology": result["typology"],
        "reasoning_ar": result["reasoning_ar"],
        "top_reasons": result["top_reasons"],
        "tenant_id": result["tenant_id"],
        "ai_model": result.get("ai_model"),
        "alert_id": (result.get("alert") or {}).get("alert_id"),
        "case_id": (result.get("case") or {}).get("case_id"),
        "latency_ms": result["latency_ms"],
        "review_message": review_message,
        # Degraded-mode transparency: the integrating bank must know when a
        # decision was produced without one or more risk engines (e.g. ML
        # unavailable) so it can apply its own caution. This is the bank's own
        # transaction — no cross-tenant exposure.
        "component_health": result.get("component_health", {}),
        "degraded_mode": result.get("degraded_mode", False),
        "degraded_reason": result.get("degraded_reason"),
        # Explicit decision confidence (0..1): share of nominal policy weight
        # backed by fully-healthy components at decision time. Persisted with
        # the decision; a failed/degraded engine always lowers it.
        "confidence": result.get("confidence", 0.0),
    }


@router.get("/decisions/recent")
async def recent_decisions(
    limit: int = 20, request: Request = None, registry=Depends(get_registry)
):
    """Public read of recent decisions — intentionally limited fields.
    Owner sees full data via /admin/decisions/recent. Merchants via /admin/merchant/decisions.
    """
    rows = registry.decisions.recent(limit=min(limit, 100))
    return [
        {
            "tx_id": r["tx_id"],
            "tenant_id": r["tenant_id"],
            "ts": r["ts"],
            "decision": r["decision"],
            "risk_score": r["risk_score"],
            "risk_band": r["risk_band"],
            "typology": r["typology"],
            "reasoning_ar": r["reasoning_ar"],
            "ai_model": r["ai_model"],
        }
        for r in rows
    ]
