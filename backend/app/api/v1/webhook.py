"""Fraud check webhook — used by any connected bank/wallet via api_key + HMAC-SHA256.
Pipeline: auth → signature → idempotency → normalize → orchestrator → persist → respond.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_registry
from app.core.config import settings
from app.models.schemas import (BehaviorSignals, DeviceContext, EventType,
                                GeoPoint, Transaction)
from app.security import verify_signature

router = APIRouter()

# Timestamp trust bounds — a sender-supplied timestamp outside these is untrusted
# and must not be allowed to poison velocity or behavioral time features.
MAX_FUTURE_SKEW_SEC = 300          # 5 min clock-skew tolerance
MAX_PAST_AGE_DAYS = 45             # older than this => backfill / suspect


def _validate_timestamp(ts: datetime, received_at: datetime) -> tuple[datetime, list[str]]:
    """Return (effective_time, flags). effective_time is clamped into a trusted window
    so a forged timestamp cannot distort velocity or time-of-day features."""
    flags: list[str] = []
    if (ts - received_at).total_seconds() > MAX_FUTURE_SKEW_SEC:
        flags.append("TS_FUTURE")
        return received_at, flags            # clamp to receipt time
    age_days = (received_at - ts).total_seconds() / 86400.0
    if age_days > MAX_PAST_AGE_DAYS:
        flags.append("TS_STALE")            # keep event time but flag it
    return ts, flags

DEFAULT_REVIEW_MESSAGE = (
    "تم تعليق العملية مؤقتًا للمراجعة الأمنية. يرجى التواصل مع البنك أو "
    "المؤسسة المالية لإتمام المراجعة.")


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

    received_at = datetime.now(timezone.utc)
    ts_raw = src.get("timestamp") or src.get("ts") or body.get("timestamp")
    ts_flags: list[str] = []
    try:
        parsed_ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")) if ts_raw else received_at
        if parsed_ts.tzinfo is None:
            parsed_ts = parsed_ts.replace(tzinfo=timezone.utc)
    except Exception:
        parsed_ts, ts_flags = received_at, ["TS_MALFORMED"]
    timestamp, vflags = _validate_timestamp(parsed_ts, received_at)
    ts_flags.extend(vflags)

    amount = src.get("amount")
    if amount is None:
        raise HTTPException(400, "amount_required")

    metadata = dict(src.get("metadata") or {})
    for k in ("velocity", "account", "beneficiary", "geo", "customer"):
        if isinstance(ctx.get(k), dict):
            metadata.setdefault(k, ctx[k])
    for k in ("account_age_days", "seconds_since_password_change", "previous_declines",
              "previous_chargebacks", "high_risk_merchant", "impossible_travel",
              "offshore", "emulator", "rooted", "mfa_recently_disabled",
              "distinct_merchants_1h", "card_declines_1h", "billing_country"):
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

    # Financial-event semantics + FX/region hints + sender-reported institution rate.
    try:
        event_type = EventType(str(src.get("event_type") or src.get("type") or "transfer").lower())
    except ValueError:
        event_type = EventType.TRANSFER
    fx_ctx = src.get("fx") if isinstance(src.get("fx"), dict) else (ctx.get("fx") if isinstance(ctx.get("fx"), dict) else {})
    institution_rate = (fx_ctx.get("rate") or src.get("actual_fx_rate") or ctx.get("actual_fx_rate"))
    region = src.get("region") or ctx.get("region") or fx_ctx.get("region")
    if institution_rate is not None:
        metadata.setdefault("institution_fx_rate", institution_rate)
    if ts_flags:
        metadata.setdefault("ts_flags", ts_flags)
        metadata.setdefault("received_at", received_at.isoformat())
        metadata.setdefault("event_time", parsed_ts.isoformat())

    return Transaction(
        tx_id=str(src.get("tx_id") or src.get("transaction_id") or uuid.uuid4()),
        tenant_id=tenant_id,
        timestamp=timestamp,
        channel=src.get("channel", "wallet"),
        amount=float(amount),
        currency=src.get("currency", "USD"),
        event_type=event_type,
        direction=str(src.get("direction") or "out"),
        is_internal=bool(src.get("is_internal")) or event_type == EventType.FX_CONVERSION,
        linked_tx_id=src.get("linked_tx_id"),
        region=region,
        sender_account_id=str(src.get("sender_account_id") or src.get("account_id")
                              or src.get("from_account") or src.get("sender") or "unknown_sender"),
        sender_user_id=src.get("sender_user_id") or src.get("user_id"),
        beneficiary_account_id=str(src.get("beneficiary_account_id") or src.get("to_account")
                                   or src.get("receiver") or src.get("merchant_id")
                                   or "unknown_beneficiary"),
        beneficiary_user_id=src.get("beneficiary_user_id"),
        beneficiary_country=src.get("beneficiary_country") or metadata.get("country"),
        merchant_id=src.get("merchant_id"),
        merchant_name=src.get("merchant_name"),
        device=DeviceContext(**{k: v for k, v in device_raw.items()
                                if k in DeviceContext.model_fields}) if device_raw else None,
        behavior=BehaviorSignals(**{k: v for k, v in behavior_raw.items()
                                    if k in BehaviorSignals.model_fields}) if behavior_raw else None,
        geo=GeoPoint(**geo_raw) if geo_raw and "lat" in geo_raw and "lon" in geo_raw else None,
        session_id=src.get("session_id") or ctx.get("session_id"),
        metadata=metadata,
    )


@router.post("/wallet/webhook", summary="Multi-tenant fraud check webhook")
async def fraud_webhook(request: Request, registry=Depends(get_registry)):
    request_id = getattr(request.state, "request_id", None)
    api_key = request.headers.get("x-api-key", "")
    signature = request.headers.get("x-wallet-signature", "")
    if not api_key or not signature:
        raise HTTPException(401, "missing_auth_headers")

    tenant = registry.tenants.by_api_key(api_key)
    if not tenant:
        legacy = settings.LEGACY_SECRET
        if legacy:
            tenant = {"tenant_id": "legacy", "name": "Legacy", "hmac_secret": legacy}
        else:
            registry.audit.log(None, api_key[:10], "authentication.failure",
                               "wallet_webhook", None, request_id, {"reason": "invalid_api_key"})
            raise HTTPException(401, "invalid_api_key")

    raw = await request.body()
    if not verify_signature(tenant["hmac_secret"], raw, signature):
        registry.audit.log(tenant["tenant_id"], tenant["name"], "authentication.failure",
                           "wallet_webhook", None, request_id, {"reason": "invalid_signature"})
        raise HTTPException(401, "invalid_signature")

    # Suspended/deleted tenants are hard-blocked at ingestion time.
    if tenant.get("status") != "active":
        registry.audit.log(tenant["tenant_id"], tenant["name"], "transaction.rejected",
                           "wallet_webhook", None, request_id, {"reason": "tenant_suspended"})
        raise HTTPException(403, "tenant_suspended")

    try:
        body = json.loads(raw)
    except Exception:
        raise HTTPException(400, "invalid_json")

    tx = normalize_transaction(body, tenant["tenant_id"])

    idem_key = request.headers.get("x-idempotency-key") or f"{tenant['tenant_id']}:{tx.tx_id}"
    result = await registry.orchestrator.evaluate_and_persist(
        tx, body, actor=tenant["name"], request_id=request_id,
        idempotency_key=idem_key,
    )
    if result.pop("duplicate", False):
        return {"tx_id": result["tx_id"], "decision": result["decision"],
                "risk_score": result["risk_score"], "duplicate": True,
                "money": result.get("money")}

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
        # Multi-currency transparency: original truth + reference value + FX status,
        # so the institution sees exactly how the money was valued for risk.
        "money": result.get("money"),
        "fx_proof": result.get("fx_proof"),
    }


@router.get("/decisions/recent")
async def recent_decisions(limit: int = 20, request: Request = None,
                           registry=Depends(get_registry)):
    """Public read of recent decisions — intentionally limited fields.
    Owner sees full data via /admin/decisions/recent. Merchants via /admin/merchant/decisions.
    """
    rows = registry.decisions.recent(limit=min(limit, 100))
    return [{"tx_id": r["tx_id"], "tenant_id": r["tenant_id"], "ts": r["ts"],
             "decision": r["decision"], "risk_score": r["risk_score"],
             "risk_band": r["risk_band"], "typology": r["typology"],
             "reasoning_ar": r["reasoning_ar"], "ai_model": r["ai_model"]}
            for r in rows]
