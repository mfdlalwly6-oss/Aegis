"""Tenant policy engine — makes tenant policy_json effective at decision time,
inside hard safety bounds.

Guarantees (enforced here, not by convention):
- A tenant can NEVER disable sanctions screening, authentication, idempotency,
  audit, or the protected core rules (R-AML-*, R-GEO-002 FATF jurisdiction).
- Thresholds are clamped to safe windows; weights may only be gently re-scaled
  (±25%) and always re-normalized to sum 1.0.
- risk_sensitivity is a bounded multiplier (0.5–1.5) applied to the fused score.
- Institution profile (bank / wallet / exchange / remittance / merchant_*)
  selects behavioral defaults so a high-velocity remittance company is not
  judged with a consumer's thresholds.
- FX safety flags are policy-controlled: fx_missing_action defaults to REVIEW
  and can never be weakened to a silent ALLOW.
"""

from __future__ import annotations

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

POLICY_SCHEMA_VERSION = "policy@3.0.0"

# Rules that may never be disabled by any tenant (core protection floor).
PROTECTED_RULES = {"R-AML-001", "R-AML-002", "R-AML-003", "R-GEO-002"}

# Safe windows for decision thresholds (ordering enforced separately).
THRESHOLD_BOUNDS = {
    "challenge": (0.20, 0.50),
    "review": (0.40, 0.75),
    "block": (0.60, 0.95),
}

SENSITIVITY_BOUNDS = (0.5, 1.5)
WEIGHT_SCALE_BOUNDS = (0.75, 1.25)

# Institution-type behavioral profiles — defaults only; tenant policy may narrow
# them further but the safety bounds above always win.
PROFILES: dict[str, dict] = {
    "individual": {},
    "consumer": {},
    "bank": {},
    "wallet": {"thresholds": {"challenge": 0.35, "review": 0.60, "block": 0.80}},
    "payment": {"thresholds": {"challenge": 0.35, "review": 0.60, "block": 0.80}},
    "merchant": {"thresholds": {"challenge": 0.40, "review": 0.65, "block": 0.85}},
    "merchant_retail": {"thresholds": {"challenge": 0.40, "review": 0.65, "block": 0.85}},
    "merchant_wholesale": {"thresholds": {"challenge": 0.45, "review": 0.70, "block": 0.88}},
    "real_estate": {"thresholds": {"challenge": 0.45, "review": 0.70, "block": 0.88}},
    "exchange": {
        "thresholds": {"challenge": 0.30, "review": 0.55, "block": 0.78},
        "expected_currencies": ["YER", "SAR", "USD"],
    },
    "remittance": {
        "thresholds": {"challenge": 0.40, "review": 0.65, "block": 0.85},
        "expected_currencies": ["YER", "SAR", "USD"],
    },
}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


class PolicyEngine:
    def version(self) -> str:
        return POLICY_SCHEMA_VERSION

    def resolve(self, tenant: dict | None) -> dict:
        """Merge settings defaults <- institution profile <- tenant policy_json,
        clamped to safety bounds. Never returns something that weakens core protection."""
        tenant = tenant or {}
        raw_policy = tenant.get("policy") or {}
        if not isinstance(raw_policy, dict):
            raw_policy = {}

        ptype = (tenant.get("type") or "wallet").lower()
        profile_name = str(raw_policy.get("profile") or ptype).lower()
        profile = PROFILES.get(profile_name) or PROFILES.get(ptype) or {}

        # --- thresholds ---
        th = {
            "challenge": settings.DECISION_THRESHOLD_CHALLENGE,
            "review": settings.DECISION_THRESHOLD_REVIEW,
            "block": settings.DECISION_THRESHOLD_BLOCK,
        }
        for source in (profile.get("thresholds"), raw_policy.get("thresholds")):
            if isinstance(source, dict):
                for k in th:
                    if isinstance(source.get(k), (int, float)):
                        lo, hi = THRESHOLD_BOUNDS[k]
                        th[k] = _clamp(float(source[k]), lo, hi)
        # enforce ordering challenge < review < block
        th["review"] = max(th["review"], th["challenge"] + 0.05)
        th["block"] = max(th["block"], th["review"] + 0.05)
        th["block"] = min(th["block"], THRESHOLD_BOUNDS["block"][1])

        # --- risk sensitivity (bounded multiplier on fused score) ---
        rs = raw_policy.get("risk_sensitivity", 1.0)
        try:
            rs = float(rs)
        except (TypeError, ValueError):
            rs = 1.0
        rs = _clamp(rs, *SENSITIVITY_BOUNDS)

        # --- weights (gentle re-scale only, re-normalized) ---
        weights = {
            "rules": settings.WEIGHT_RULES,
            "ml": settings.WEIGHT_ML,
            "graph": settings.WEIGHT_GRAPH,
            "aml": settings.WEIGHT_AML,
            "behavior": settings.WEIGHT_BEHAVIOR,
        }
        raw_w = raw_policy.get("weights")
        if isinstance(raw_w, dict):
            for k in weights:
                if isinstance(raw_w.get(k), (int, float)):
                    base = weights[k]
                    lo, hi = base * WEIGHT_SCALE_BOUNDS[0], base * WEIGHT_SCALE_BOUNDS[1]
                    weights[k] = _clamp(float(raw_w[k]), lo, hi)
        total = sum(weights.values()) or 1.0
        weights = {k: v / total for k, v in weights.items()}

        # --- disabled rules (protected set always stays enabled) ---
        disabled = set(raw_policy.get("disabled_rules") or [])
        removed = disabled & PROTECTED_RULES
        if removed:
            logger.warning(
                "policy.protected_rule_disable_blocked",
                rules=sorted(removed),
                tenant=tenant.get("tenant_id"),
            )
        disabled -= PROTECTED_RULES

        # --- FX missing action (can never be a silent allow) ---
        fx_missing_action = str(
            raw_policy.get("fx_missing_action") or settings.FX_MISSING_DECISION
        ).lower()
        if fx_missing_action not in ("review", "block"):
            fx_missing_action = "review"

        return {
            "thresholds": th,
            "risk_sensitivity": rs,
            "weights": weights,
            "disabled_rules": sorted(disabled),
            "expected_currencies": raw_policy.get("expected_currencies")
            or profile.get("expected_currencies")
            or [],
            "expected_regions": raw_policy.get("expected_regions")
            or profile.get("expected_regions")
            or [],
            "fx_missing_action": fx_missing_action,
            "profile": profile_name,
            "version": POLICY_SCHEMA_VERSION,
        }
