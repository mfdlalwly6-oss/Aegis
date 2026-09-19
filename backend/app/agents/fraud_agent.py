"""FraudAgent — optional AI explanation via OpenRouter.
Used ONLY for explanations; never overrides the deterministic decision.
"""

from __future__ import annotations

import json
import re

import structlog

from .openrouter import OpenRouterClient

logger = structlog.get_logger(__name__)


_SENSITIVE_KEYS = re.compile(
    r"\"(sender_account_id|beneficiary_account_id|sender_user_id|beneficiary_user_id|"
    r"sender_name|beneficiary_name|customer_name|customer_dob|customer_identifiers|"
    r"card_bin|card_last4|card_token_reference|device_id|fingerprint_hash|session_id|ip)\"\s*:\s*\"[^\"]*\"",
    re.IGNORECASE,
)


def _redact(payload) -> str:
    """Serialize with sensitive financial/customer identifiers redacted before any external LLM call."""
    raw = json.dumps(payload, default=str, ensure_ascii=False)
    return _SENSITIVE_KEYS.sub(lambda m: m.group(0).split(":")[0] + ':"[redacted]"', raw)


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r"(\{[\s\S]*\})", text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    cleaned = re.sub(r",\s*}", "}", text).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    return None


class FraudAgent:
    def __init__(self) -> None:
        self.client = OpenRouterClient()

    async def analyze(self, tx: dict, rules_hits: list, ml_prob: float) -> dict:
        rules_safe = [
            (h.model_dump() if hasattr(h, "model_dump") else h) for h in (rules_hits or [])
        ]
        prompt = (
            "أنت محلل احتيال مالي. أجب بـ JSON فقط بدون أي نص إضافي.\n"
            f"transaction: {_redact(tx)[:600]}\n"
            f"rules_hits: {_redact(rules_safe)[:400]}\n"
            f"ml_prob: {ml_prob}\n\n"
            'المطلوب JSON: {"typology":"نمط الاحتيال","reasoning_ar":"شرح قصير بالعربية"}'
        )
        r = await self.client.chat(prompt)
        if not r.get("ok"):
            return {"model": "fallback", "reasoning_ar": None, "error": r.get("error")}
        parsed = _extract_json(r.get("content", ""))
        if not parsed:
            return {"model": r.get("model"), "reasoning_ar": None}
        return {
            "model": r.get("model"),
            "typology": parsed.get("typology"),
            "reasoning_ar": parsed.get("reasoning_ar"),
        }
