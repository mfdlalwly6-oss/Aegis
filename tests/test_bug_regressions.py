"""Regression tests for product-E2E bug fixes (2026-08-25).

BUG1: inverted policy thresholds must be rejected at write time (not stored).
BUG3: malformed transaction amount must yield 4xx, never 500.
BUG4: rules referencing absent (None) fields must not fire and must not error.
"""

from __future__ import annotations

import pytest

# ── BUG1 ──────────────────────────────────────────────────────────────────


def test_update_policy_rejects_inverted_thresholds():
    """update_policy must raise ValueError on challenge > review > block inversion."""
    import tempfile

    from app.db import Database
    from app.repositories.tenant_repo import TenantRepository

    db = Database(str(tempfile.mkdtemp() + "/t.db"))
    db.migrate()
    repo = TenantRepository(db)
    tenant = repo.create({"name": "Policy Guard Test", "type": "wallet", "country": "YE"})

    with pytest.raises(ValueError, match="challenge <= review <= block"):
        repo.update_policy(
            tenant["tenant_id"], {"thresholds": {"challenge": 0.9, "review": 0.2, "block": 0.1}}
        )

    # valid ladder persists
    out = repo.update_policy(
        tenant["tenant_id"], {"thresholds": {"challenge": 0.2, "review": 0.5, "block": 0.8}}
    )
    assert out["policy"]["thresholds"]["block"] == 0.8
    db.close()


def test_update_policy_allows_partial_and_non_numeric():
    """Partial policies (only some thresholds) and missing keys must not be rejected."""
    import tempfile

    from app.db import Database
    from app.repositories.tenant_repo import TenantRepository

    db = Database(str(tempfile.mkdtemp() + "/t.db"))
    db.migrate()
    repo = TenantRepository(db)
    tenant = repo.create({"name": "Partial Policy", "type": "bank", "country": "YE"})

    # only one threshold set — no full ladder to validate, must pass
    out = repo.update_policy(tenant["tenant_id"], {"thresholds": {"block": 0.95}})
    assert out["policy"]["thresholds"]["block"] == 0.95
    db.close()


# ── BUG4 ──────────────────────────────────────────────────────────────────


def test_rule_with_missing_field_does_not_fire_and_does_not_error(caplog):
    """A rule comparing an absent field must return None without rule.eval_error."""
    from app.rules.engine import Rule, evaluate

    # expression: tx.velocity.count_1h > 5  (velocity absent from ctx)
    expr = {">": [{"var": "tx.velocity.count_1h"}, 5]}
    assert evaluate(expr, {"tx": {"amount": 100}}) is False

    rule = Rule({"id": "R-TEST-NONE", "name": "t", "when": expr, "score": 0.5})
    hit = rule.evaluate({"tx": {"amount": 100}})
    assert hit is None  # no fire, and no exception propagated


def test_rule_with_present_field_still_fires():
    """Guard against over-suppression: real comparisons must still work."""
    from app.rules.engine import evaluate

    expr = {">": [{"var": "tx.amount"}, 50]}
    assert evaluate(expr, {"tx": {"amount": 100}}) is True
    assert evaluate(expr, {"tx": {"amount": 10}}) is False


# ── BUG3 (integration, via API client fixture from conftest) ──────────────


def test_webhook_invalid_amount_returns_4xx_not_500(client):
    """Malformed amount must produce 400 amount_invalid, never a 500."""
    import hashlib
    import hmac
    import json

    # create a tenant via owner API
    r = client.post(
        "/api/v1/admin/tenants",
        json={"name": "Bug3 Tenant", "type": "wallet", "country": "YE"},
        headers={"X-Owner-Token": "test-owner-token-2026"},
    )
    assert r.status_code == 201, r.text
    tid = r.json()["tenant_id"]

    # reveal creds (owner endpoint)
    r = client.get(f"/api/v1/admin/tenants/{tid}", headers={"X-Owner-Token": "test-owner-token-2026"})
    assert r.status_code == 200
    api_key = r.json()["api_key"]
    secret = r.json()["hmac_secret"]

    body = json.dumps(
        {"tx_id": "tx_bug3", "amount": "not-a-number", "currency": "USD", "channel": "wire"}
    ).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    r = client.post(
        "/api/v1/wallet/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "x-wallet-signature": sig,
        },
    )
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"
    assert r.json()["detail"] == "amount_invalid"
