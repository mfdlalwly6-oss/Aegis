"""Webhook tests — HMAC verification, idempotency, pipeline."""
import json

from tests.conftest import create_tenant, sign


def test_webhook_rejects_missing_headers(client):
    r = client.post("/api/v1/wallet/webhook", json={})
    assert r.status_code == 401


def test_webhook_rejects_bad_api_key(client):
    r = client.post("/api/v1/wallet/webhook",
                    headers={"X-API-Key": "bad", "X-Wallet-Signature": "bad"},
                    json={"transaction": {"amount": 1}})
    assert r.status_code == 401


def test_webhook_rejects_bad_signature(client):
    tenant = create_tenant(client)
    r = client.post("/api/v1/wallet/webhook",
                    headers={"X-API-Key": tenant["api_key"], "X-Wallet-Signature": "bad"},
                    json={"transaction": {"amount": 100, "sender_account_id": "a", "beneficiary_account_id": "b"}})
    assert r.status_code == 401


def test_webhook_valid_flow(client):
    tenant = create_tenant(client)
    payload = {"transaction": {"tx_id": "tx_test_1", "amount": 500,
                               "sender_account_id": "acct_a", "beneficiary_account_id": "acct_b"}}
    sig, body = sign(tenant["hmac_secret"], payload)
    r = client.post("/api/v1/wallet/webhook",
                    headers={"Content-Type": "application/json",
                             "X-API-Key": tenant["api_key"],
                             "X-Wallet-Signature": sig},
                    content=body)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["tx_id"] == "tx_test_1"
    assert d["decision"] in ("allow", "challenge", "review", "block")
    assert 0.0 <= d["risk_score"] <= 1.0


def test_webhook_idempotency(client):
    tenant = create_tenant(client)
    payload = {"transaction": {"tx_id": "tx_idem_1", "amount": 100,
                               "sender_account_id": "acct_a", "beneficiary_account_id": "acct_b"}}
    sig, body = sign(tenant["hmac_secret"], payload)
    headers = {"Content-Type": "application/json", "X-API-Key": tenant["api_key"],
               "X-Wallet-Signature": sig}
    r1 = client.post("/api/v1/wallet/webhook", headers=headers, content=body)
    assert r1.status_code == 200
    r2 = client.post("/api/v1/wallet/webhook", headers=headers, content=body)
    assert r2.status_code == 200
    assert r2.json().get("duplicate") is True


def test_no_legacy_fallback_by_default(client):
    payload = {"transaction": {"tx_id": "tx_x", "amount": 10,
                               "sender_account_id": "a", "beneficiary_account_id": "b"}}
    sig, body = sign("some-secret", payload)
    r = client.post("/api/v1/wallet/webhook",
                    headers={"Content-Type": "application/json",
                             "X-API-Key": "unknown_key",
                             "X-Wallet-Signature": sig},
                    content=body)
    assert r.status_code == 401
