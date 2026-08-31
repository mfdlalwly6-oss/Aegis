"""Decision confidence — explicit, interpretable, non-retroactive.

confidence = fraction of NOMINAL policy weight backed by component state at
decision time: healthy=1.0, degraded=0.5, unavailable=0.0. A failed engine must
LOWER confidence by its nominal share — never leave it at 1.0. Persisted with
the decision (migration 020) and reconstructible from component_health.
"""

import uuid
from datetime import UTC, datetime

from tests.conftest import OWNER_HEADERS, create_tenant

BASE = "/api/v1"

# Nominal weights (policy defaults) — must mirror settings for the math below.
W = {"rules": 0.35, "ml": 0.25, "graph": 0.15, "aml": 0.15, "behavior": 0.10}


def _post_tx(client, tenant, tx_id, currency="USD", amount=100, behavior=None):
    import hashlib, hmac, json

    body = {
        "tx_id": tx_id,
        "amount": amount,
        "currency": currency,
        "sender_account_id": "a1",
        "beneficiary_account_id": "b1",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if behavior:
        body["behavior"] = behavior
    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()
    sig = hmac.new(tenant["hmac_secret"].encode(), raw, hashlib.sha256).hexdigest()
    return client.post(
        f"{BASE}/wallet/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "x-api-key": tenant["api_key"],
            "x-wallet-signature": sig,
            "x-idempotency-key": tx_id,
        },
    )


def _decision_row(client, tx_id):
    r = client.get(f"{BASE}/admin/decisions/recent?limit=50", headers=OWNER_HEADERS)
    rows = r.json() if isinstance(r.json(), list) else r.json().get("decisions", [])
    return next((d for d in rows if d.get("tx_id") == tx_id), None)


def test_clean_tx_full_behavior_has_max_confidence(client, monkeypatch):
    """All components healthy (incl. behavior payload + trained ML) -> confidence == 1.0."""
    # Test env has no trained ML model by default; force it ready so all five
    # components are healthy and confidence reaches its ceiling.
    monkeypatch.setattr(client.app.state.registry.ml_scorer, "ready", True, raising=False)
    t = create_tenant(client, name=f"CF-{uuid.uuid4().hex[:6]}")
    tx = f"cf-full-{uuid.uuid4().hex[:6]}"
    r = _post_tx(
        client, t, tx,
        behavior={"biometric_match_score": 0.95, "keystroke_entropy": 3.0, "session_duration_ms": 60000},
    )
    assert r.status_code == 200, r.text
    conf = r.json().get("confidence")
    assert conf == 1.0, f"expected 1.0 with all healthy, got {conf}"


def test_ml_unavailable_lowers_confidence_by_its_weight(client, monkeypatch):
    """ML engine down -> ml unavailable (0x). confidence = 1 - 0.25 = 0.75.
    This is the core invariant: a failed component must shrink confidence by
    exactly its nominal policy weight, never leave it at 1.0."""
    reg = client.app.state.registry
    monkeypatch.setattr(reg.ml_scorer, "ready", False, raising=False)
    t = create_tenant(client, name=f"CF-{uuid.uuid4().hex[:6]}")
    tx = f"cf-noml-{uuid.uuid4().hex[:6]}"
    r = _post_tx(client, t, tx, behavior={"biometric_match_score": 0.95, "keystroke_entropy": 3.0, "session_duration_ms": 60000})
    assert r.status_code == 200, r.text
    conf = r.json().get("confidence")
    assert abs(conf - 0.75) < 1e-3, f"expected ~0.75 with ML down, got {conf}"


def test_missing_behavior_lowers_confidence_by_half_its_weight(client, monkeypatch):
    """No behavior payload -> behavior degraded (0.5x). confidence = 1 - 0.5*0.10 = 0.95.
    ML forced ready so only the behavior gap affects the value."""
    monkeypatch.setattr(client.app.state.registry.ml_scorer, "ready", True, raising=False)
    t = create_tenant(client, name=f"CF-{uuid.uuid4().hex[:6]}")
    tx = f"cf-nobehav-{uuid.uuid4().hex[:6]}"
    r = _post_tx(client, t, tx)  # no behavior key at all
    assert r.status_code == 200, r.text
    conf = r.json().get("confidence")
    # behavior degraded -> contributes 0.5 * 0.10 = 0.05 instead of 0.10
    assert abs(conf - 0.95) < 1e-3, f"expected ~0.95, got {conf}"


def test_confidence_persisted_and_matches_response(client):
    """confidence is stored on the decision row (migration 020) and matches the
    webhook response — the persisted value, not a recomputation."""
    t = create_tenant(client, name=f"CF-{uuid.uuid4().hex[:6]}")
    tx = f"cf-persist-{uuid.uuid4().hex[:6]}"
    r = _post_tx(client, t, tx)
    assert r.status_code == 200, r.text
    resp_conf = r.json().get("confidence")
    row = _decision_row(client, tx)
    assert row is not None, "decision not persisted"
    assert "confidence" in row, f"confidence column missing from decision row: {list(row.keys())}"
    assert abs(float(row["confidence"]) - resp_conf) < 1e-6, (
        f"persisted {row['confidence']} != response {resp_conf}"
    )


def test_confidence_bounds_and_type(client):
    """confidence is always a float within [0, 1] regardless of path."""
    t = create_tenant(client, name=f"CF-{uuid.uuid4().hex[:6]}")
    for i, cur in enumerate(("USD", "XXX")):  # XXX -> fx_missing -> review path
        tx = f"cf-bound-{i}-{uuid.uuid4().hex[:4]}"
        r = _post_tx(client, t, tx, currency=cur)
        assert r.status_code == 200, r.text
        conf = r.json().get("confidence")
        assert isinstance(conf, (int, float)), f"confidence not numeric: {conf!r}"
        assert 0.0 <= conf <= 1.0, f"confidence out of bounds: {conf}"


def test_confidence_reconstructible_from_component_health(client, monkeypatch):
    """confidence must be re-derivable from component_health status + nominal
    weights — auditable, never a black box. Degraded counts half."""
    monkeypatch.setattr(client.app.state.registry.ml_scorer, "ready", True, raising=False)
    t = create_tenant(client, name=f"CF-{uuid.uuid4().hex[:6]}")
    tx = f"cf-recon-{uuid.uuid4().hex[:6]}"
    r = _post_tx(client, t, tx)  # no behavior -> degraded
    assert r.status_code == 200, r.text
    body = r.json()
    health = body.get("component_health", {})
    frac = {"healthy": 1.0, "degraded": 0.5, "unavailable": 0.0}
    expected = round(
        min(1.0, max(0.0, sum(frac.get(health.get(k, {}).get("status", "unavailable"), 0.0) * W[k] for k in W))),
        4,
    )
    assert abs(body["confidence"] - expected) < 1e-3, (
        f"confidence {body['confidence']} not reconstructible from health {health} (expected {expected})"
    )
