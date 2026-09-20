"""Fraud check webhook — used by any connected bank/wallet via api_key + HMAC-SHA256.
Pipeline: auth → signature → idempotency → normalize → orchestrator → persist → respond.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_registry, require_investigator
from app.core.config import settings
from app.models.schemas import (AuthenticationContext, BehaviorSignals, CardContext,
                                DeviceContext, GeoPoint, Transaction)
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

    card_raw = src.get("card") or ctx.get("card") or None
    auth_raw = src.get("authentication") or ctx.get("authentication") or None
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

    card_ctx = CardContext(**card_raw) if isinstance(card_raw, dict) else None
    auth_ctx = AuthenticationContext(**auth_raw) if isinstance(auth_raw, dict) else None
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
        card=card_ctx,
        authentication=auth_ctx,
        metadata=metadata,
    )


def _apply_fx(registry, tx, body):
    # FX removed: AEGIS keeps amount+currency as-is; no conversion.
    return tx
