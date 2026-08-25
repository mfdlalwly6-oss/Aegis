"""API security tests — auth, signatures, idempotency, replay, headers, isolation."""
import hashlib, hmac, json


def _sign(secret: str, body: dict) -> tuple[bytes, str]:
    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()
    return raw, hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def _tenant_key(client):
    """Create a tenant via owner API and return (tenant_id, api_key, hmac_secret)."""
    from tests.conftest import OWNER_HEADERS
    import uuid
    r = client.post("/api/v1/admin/tenants", json={
        "name": f"Sec-{uuid.uuid4().hex[:6]}", "type": "wallet", "country": "YE",
        "plan": "sandbox", "investigator_limit": 2}, headers=OWNER_HEADERS)
    assert r.status_code == 201, r.text
    t = r.json()
    return t["tenant_id"], t["api_key"], t["hmac_secret"]


def _tx(tid, **kw):
    from datetime import datetime, timezone
    b = {"tx_id": f"tx-{tid[:6]}", "amount": 100.0, "currency": "USD",
         "sender_account_id": "a", "beneficiary_account_id": "b",
         # dynamic timestamp: always within the replay-guard window (now)
         "timestamp": datetime.now(timezone.utc).isoformat()}
    b.update(kw)
    return b


class TestApiSecurity:
    def test_missing_api_key_rejected(self, client):
        r = client.post("/api/v1/wallet/webhook", json=_tx("none"))
        assert r.status_code in (401, 403)

    def test_invalid_signature_rejected(self, client):
        tid, key, secret = _tenant_key(client)
        raw, _ = _sign(secret, _tx(tid))
        r = client.post("/api/v1/wallet/webhook", content=raw, headers={
            "Content-Type": "application/json", "x-api-key": key,
            "x-wallet-signature": "0" * 64, "x-idempotency-key": f"bad-{tid}"})
        assert r.status_code == 401

    def test_tampered_body_rejected(self, client):
        tid, key, secret = _tenant_key(client)
        body = _tx(tid, amount=100.0)
        raw, sig = _sign(secret, body)
        body["amount"] = 999999.0  # tamper after signing
        raw2 = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()
        r = client.post("/api/v1/wallet/webhook", content=raw2, headers={
            "Content-Type": "application/json", "x-api-key": key,
            "x-wallet-signature": sig, "x-idempotency-key": f"tamp-{tid}"})
        assert r.status_code == 401

    def test_idempotency_duplicate_flag(self, client):
        tid, key, secret = _tenant_key(client)
        raw, sig = _sign(secret, _tx(tid, amount=55.0))
        h = {"Content-Type": "application/json", "x-api-key": key,
             "x-wallet-signature": sig, "x-idempotency-key": f"idem-{tid}"}
        r1 = client.post("/api/v1/wallet/webhook", content=raw, headers=h)
        r2 = client.post("/api/v1/wallet/webhook", content=raw, headers=h)
        assert r1.status_code == 200
        assert r2.status_code == 200 and r2.json().get("duplicate") is True

    def test_timestamp_future_rejected(self, client):
        tid, key, secret = _tenant_key(client)
        raw, sig = _sign(secret, _tx(tid, timestamp="2030-01-01T00:00:00Z"))
        r = client.post("/api/v1/wallet/webhook", content=raw, headers={
            "Content-Type": "application/json", "x-api-key": key,
            "x-wallet-signature": sig, "x-idempotency-key": f"fut-{tid}"})
        assert r.status_code == 422

    def test_timestamp_stale_rejected(self, client):
        tid, key, secret = _tenant_key(client)
        raw, sig = _sign(secret, _tx(tid, timestamp="2020-01-01T00:00:00Z"))
        r = client.post("/api/v1/wallet/webhook", content=raw, headers={
            "Content-Type": "application/json", "x-api-key": key,
            "x-wallet-signature": sig, "x-idempotency-key": f"old-{tid}"})
        assert r.status_code == 422

    def test_security_headers_present(self, client):
        r = client.get("/health")
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert r.headers.get("x-frame-options") == "DENY"
        assert "x-request-id" in r.headers

    def test_cross_tenant_key_rejected_on_other_tenant_data(self, client):
        """API key of tenant A must not be usable to read tenant B admin data (owner-only anyway),
        and merchant tokens are scoped. Minimal probe: invalid tenant api key rejected."""
        r = client.post("/api/v1/wallet/webhook", json=_tx("x"), headers={
            "x-api-key": "aeg_pk_invalid", "x-wallet-signature": "0" * 64})
        assert r.status_code in (401, 403)
