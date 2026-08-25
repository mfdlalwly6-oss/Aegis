"""TASK 9 — security hardening: demo login removal + hmac_secret encryption at rest."""

import hashlib
import hmac as hmac_mod
import json
from datetime import UTC, datetime


class TestCryptoModule:
    def test_encrypt_decrypt_roundtrip(self):
        from app.crypto import decrypt_secret, encrypt_secret

        secret = "test-secret-value-123"
        enc = encrypt_secret(secret)
        assert enc != secret
        assert enc.startswith("gAAAA")
        assert decrypt_secret(enc) == secret

    def test_encrypt_is_idempotent(self):
        from app.crypto import encrypt_secret, is_encrypted

        enc = encrypt_secret("abc")
        assert is_encrypted(enc)
        assert encrypt_secret(enc) == enc

    def test_decrypt_legacy_plaintext_passthrough(self):
        from app.crypto import decrypt_secret, is_encrypted

        assert not is_encrypted("plain-legacy")
        assert decrypt_secret("plain-legacy") == "plain-legacy"


class TestDemoLoginRemoved:
    def test_no_hardcoded_demo_constants(self):
        import inspect

        import app.api.v1.auth as auth_mod

        src = inspect.getsource(auth_mod)
        assert "_DEMO_USER" not in src
        assert "_DEMO_PASSWORD" not in src
        assert "ChangeMe!2026" not in src

    def test_demo_credentials_rejected(self, client):
        r = client.post(
            "/api/v1/auth/login", json={"email": "admin@aegis.local", "password": "ChangeMe!2026"}
        )
        assert r.status_code == 401

    def test_unknown_user_rejected(self, client):
        r = client.post("/api/v1/auth/login", json={"email": "nobody@nowhere.test", "password": "wrong"})
        assert r.status_code == 401


class TestPlatformAdminAuth:
    def test_admin_login_via_users_table(self, client):
        registry = client.app.state.registry
        # create platform tenant + admin user in the test DB
        registry.db.execute(
            "INSERT OR IGNORE INTO tenants (tenant_id, name, type, country, plan,"
            " contact_email, contact_phone, api_key, hmac_secret, status,"
            " policy_json, created_at, secret_rotated_at, deleted_at,"
            " investigator_limit, timezone, review_message)"
            " VALUES ('platform','AEGIS Platform','platform','YE','internal',"
            " NULL, NULL, 'ak_test', 'gAAAA_test', 'active', '{}', ?, NULL, NULL, 999, 'UTC', '')",
            (datetime.now(UTC).isoformat(),),
        )
        registry.user_repo.create(
            "platform", "admin@test.local", "Test Admin", role="admin", password="TestPass#123"
        )
        r = client.post("/api/v1/auth/login", json={"email": "admin@test.local", "password": "TestPass#123"})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_non_admin_role_rejected(self, client):
        registry = client.app.state.registry
        registry.db.execute(
            "INSERT OR IGNORE INTO tenants (tenant_id, name, type, country, plan,"
            " contact_email, contact_phone, api_key, hmac_secret, status,"
            " policy_json, created_at, secret_rotated_at, deleted_at,"
            " investigator_limit, timezone, review_message)"
            " VALUES ('platform','AEGIS Platform','platform','YE','internal',"
            " NULL, NULL, 'ak_test', 'gAAAA_test', 'active', '{}', ?, NULL, NULL, 999, 'UTC', '')",
            (datetime.now(UTC).isoformat(),),
        )
        registry.user_repo.create(
            "platform", "viewer@test.local", "Viewer", role="viewer", password="ViewPass#123"
        )
        r = client.post("/api/v1/auth/login", json={"email": "viewer@test.local", "password": "ViewPass#123"})
        assert r.status_code == 401


class TestHmacSecretEncryption:
    def test_new_tenant_secret_stored_encrypted(self, client):
        registry = client.app.state.registry
        t = registry.tenants.create({"name": "EncTest", "type": "wallet"})
        raw = registry.db.query_one("SELECT hmac_secret FROM tenants WHERE tenant_id=?", (t["tenant_id"],))
        assert raw["hmac_secret"].startswith("gAAAA")
        # internal callers still receive plaintext via reveal path
        revealed = registry.tenants.get(t["tenant_id"], reveal=True)
        assert not revealed["hmac_secret"].startswith("gAAAA")

    def test_webhook_hmac_with_encrypted_secret(self, client):
        registry = client.app.state.registry
        t = registry.tenants.create({"name": "HmacEnc", "type": "wallet"})
        revealed = registry.tenants.get(t["tenant_id"], reveal=True)
        body = {
            "transaction_id": "tx_enc_hmac_t9",
            "tenant_id": t["tenant_id"],
            "amount": 100.0,
            "currency": "USD",
            "sender_id": "s",
            "beneficiary_id": "b",
            "timestamp": datetime.now(UTC).isoformat(),
            "channel": "card_not_present",
        }
        raw = json.dumps(body, separators=(",", ":")).encode()
        sig = hmac_mod.new(revealed["hmac_secret"].encode(), raw, hashlib.sha256).hexdigest()
        r = client.post(
            "/api/v1/wallet/webhook",
            content=raw,
            headers={
                "content-type": "application/json",
                "x-wallet-signature": sig,
                "x-api-key": revealed["api_key"],
            },
        )
        assert r.status_code == 200
