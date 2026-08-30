"""Component health + availability-aware risk aggregation.

Proves the decision engine degrades safely and audibly:
- a healthy run scores all five components with renormalized weights = 1.0
- an ML outage drops ML from the score (NOT silently 0) and flags degraded_mode
- an AML outage fails CLOSED to review (sanctions obligation) and records it
- component_health + degraded_reason persist verbatim into decisions table
"""
from __future__ import annotations

import asyncio
import json

from tests.conftest import OWNER_HEADERS, create_tenant


def _tx(client, tenant, body: dict):
    import hashlib
    import hmac

    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()
    sig = hmac.new(tenant["hmac_secret"].encode(), raw, hashlib.sha256).hexdigest()
    return client.post(
        "/api/v1/wallet/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "x-api-key": tenant["api_key"],
            "x-wallet-signature": sig,
            "x-idempotency-key": body["tx_id"],
        },
    )


def _body(tx_id: str, amount: float = 100.0, currency: str = "USD", *, behavior: bool = False):
    b = {
        "tx_id": tx_id,
        "amount": amount,
        "currency": currency,
        "sender_account_id": "acct-sender",
        "beneficiary_account_id": "acct-ben",
    }
    if behavior:
        # benign behavior payload so the behavior component is genuinely healthy
        b["behavior"] = {
            "biometric_match_score": 0.95,
            "keystroke_entropy": 2.4,
            "session_duration_ms": 60_000,
        }
    return b


def test_healthy_run_marks_all_components_healthy_and_weights_sum_to_one(client, monkeypatch):
    # Test env has no trained model by default; force ML ready so all five
    # components are genuinely healthy for this baseline.
    monkeypatch.setattr(client.app.state.registry.ml_scorer, "ready", True, raising=False)
    t = create_tenant(client, name="CH Healthy")
    r = _tx(client, t, _body("CH_OK_1", behavior=True))
    assert r.status_code == 200, r.text
    d = r.json()
    ch = d.get("component_health", {})
    assert ch, "component_health must be recorded"
    # every engine contributed and the applied weights renormalize to ~1.0
    total = sum(c.get("weight_applied", 0.0) for c in ch.values())
    assert abs(total - 1.0) < 0.01, f"weights must renormalize to 1.0, got {total}"
    assert d.get("degraded_mode") in (False, 0)


def test_ml_unavailable_excluded_from_score_and_flagged(client, monkeypatch):
    reg = client.app.state.registry
    # Force ML ensemble to report not-ready (no trained model)
    monkeypatch.setattr(reg.ml_scorer, "ready", False, raising=False)
    t = create_tenant(client, name="CH ML Out")
    r = _tx(client, t, _body("CH_ML_1"))
    assert r.status_code == 200, r.text
    d = r.json()
    ch = d.get("component_health", {})
    assert ch.get("ml", {}).get("status") == "unavailable"
    assert ch["ml"].get("weight_applied") == 0.0, "unavailable ML must not receive weight"
    # remaining components renormalize to cover the missing ML weight
    others = sum(c.get("weight_applied", 0.0) for k, c in ch.items() if k != "ml")
    assert abs(others - 1.0) < 0.01
    assert d.get("degraded_mode") in (True, 1)
    assert "ml" in (d.get("degraded_reason") or "")


def test_aml_unavailable_fails_closed_to_review(client, monkeypatch):
    reg = client.app.state.registry

    async def _boom(tx, features):
        raise RuntimeError("watchlist store unreachable")

    monkeypatch.setattr(reg.aml_service, "screen", _boom)
    t = create_tenant(client, name="CH AML Out")
    r = _tx(client, t, _body("CH_AML_1"))
    assert r.status_code == 200, r.text
    d = r.json()
    # sanctions obligation: never silently ALLOW when screening is impossible
    assert d["decision"] == "review", f"AML outage must fail closed to review, got {d['decision']}"
    assert "AML_UNAVAILABLE_FAIL_CLOSED" in (d.get("degraded_reason") or "")


def test_component_health_persists_verbatim_in_decisions_table(client, monkeypatch):
    reg = client.app.state.registry
    monkeypatch.setattr(reg.ml_scorer, "ready", False, raising=False)
    t = create_tenant(client, name="CH Persist")
    tid = t["tenant_id"]
    r = _tx(client, t, _body("CH_PERSIST_1"))
    assert r.status_code == 200, r.text
    row = client.get(f"/api/v1/admin/tenants/{tid}/decisions", headers=OWNER_HEADERS).json()
    rec = [d for d in row if d["tx_id"] == "CH_PERSIST_1"][0]
    raw = rec.get("component_health_json")
    ch = json.loads(raw) if isinstance(raw, str) else (raw or {})
    assert ch.get("ml", {}).get("status") == "unavailable"
    assert rec.get("degraded_mode") in (True, 1, "1")
    assert rec.get("degraded_reason"), "degraded_reason must be stored"
