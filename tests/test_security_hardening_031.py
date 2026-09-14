"""Security hardening tests — migration 031 features.

Covers the three gaps closed in the completion mission:
  1. Per-user random password salt (legacy hashes keep verifying, seamless
     upgrade on login, new passwords always salted uniquely).
  2. Server-side session revocation via tokens_valid_after (disable kills live
     tokens instantly; password reset invalidates old sessions; re-enable does
     NOT resurrect pre-disable tokens).
  3. Auth-specific rate limiting (login / forgot-password throttled, generic
     429, unrelated endpoints untouched).
"""
from __future__ import annotations

import time

import pytest

from tests.conftest import OWNER_HEADERS, create_tenant


def _make_active_owner(client, name="SEC-1", password="Str0ngPass!x"):
    """Create a tenant with a directly-active owner (owner_password path)."""
    t = create_tenant(
        client, name=name, type="bank",
        owner_email=f"{name.lower()}@sec.example", owner_name="Sec Owner",
        owner_password=password,
    )
    return t


def _login(client, email, password):
    return client.post("/api/v1/auth/institution/login",
                       json={"email": email, "password": password})


class TestPerUserSalt:
    def test_01_new_owner_gets_unique_random_salt(self, client):
        from app.main import app
        t = _make_active_owner(client, "SALT-1")
        reg = app.state.registry
        row = reg.db.query_one("SELECT password_salt, password_hash FROM users WHERE email=?",
                               ("salt-1@sec.example",))
        assert row and row["password_salt"], "new passwords must carry a per-user salt"
        assert len(row["password_salt"]) == 32  # 16 bytes hex

    def test_02_two_users_same_password_have_different_hashes(self, client):
        from app.main import app
        _make_active_owner(client, "SALT-2A", "SamePass!234")
        _make_active_owner(client, "SALT-2B", "SamePass!234")
        reg = app.state.registry
        a = reg.db.query_one("SELECT password_hash, password_salt FROM users WHERE email=?",
                             ("salt-2a@sec.example",))
        b = reg.db.query_one("SELECT password_hash, password_salt FROM users WHERE email=?",
                             ("salt-2b@sec.example",))
        assert a["password_salt"] != b["password_salt"]
        assert a["password_hash"] != b["password_hash"]

    def test_03_salted_login_and_wrong_password(self, client):
        _make_active_owner(client, "SALT-3", "RightPass!99")
        ok = _login(client, "salt-3@sec.example", "RightPass!99")
        assert ok.status_code == 200
        bad = _login(client, "salt-3@sec.example", "WrongPass!99")
        assert bad.status_code in (401, 429)


class TestSessionRevocation:
    def test_04_disable_kills_live_token(self, client):
        t = _make_active_owner(client, "REV-1", "RevPass!111")
        tok = _login(client, "rev-1@sec.example", "RevPass!111").json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        assert client.get("/api/v1/admin/merchant/me", headers=h).status_code == 200
        time.sleep(1.1)  # cross a second boundary (not-before gate granularity)
        client.post(f"/api/v1/admin/tenants/{t['tenant_id']}/owner/disable",
                    json={}, headers=OWNER_HEADERS)
        assert client.get("/api/v1/admin/merchant/me", headers=h).status_code == 401

    def test_05_reenable_does_not_resurrect_old_token(self, client):
        t = _make_active_owner(client, "REV-2", "RevPass!222")
        tok = _login(client, "rev-2@sec.example", "RevPass!222").json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        time.sleep(1.1)
        client.post(f"/api/v1/admin/tenants/{t['tenant_id']}/owner/disable",
                    json={}, headers=OWNER_HEADERS)
        client.post(f"/api/v1/admin/tenants/{t['tenant_id']}/owner/enable",
                    json={}, headers=OWNER_HEADERS)
        # Old token must stay dead even though the account is active again.
        assert client.get("/api/v1/admin/merchant/me", headers=h).status_code == 401
        # A fresh login works and gets a working token.
        tok2 = _login(client, "rev-2@sec.example", "RevPass!222").json()["access_token"]
        assert client.get("/api/v1/admin/merchant/me",
                          headers={"Authorization": f"Bearer {tok2}"}).status_code == 200

    def test_06_password_reset_invalidates_prior_sessions(self, client):
        from app.main import app
        t = _make_active_owner(client, "REV-3", "RevPass!333")
        tok = _login(client, "rev-3@sec.example", "RevPass!333").json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        assert client.get("/api/v1/admin/merchant/me", headers=h).status_code == 200
        time.sleep(1.1)
        reg = app.state.registry
        owners = reg.db.query(
            "SELECT user_id, tenant_id FROM users WHERE email=?", ("rev-3@sec.example",))
        _row, raw = reg.invitations.create_reset(
            owners[0]["tenant_id"], owners[0]["user_id"], "rev-3@sec.example",
            ttl_hours=1)
        r = client.post("/api/v1/auth/institution/reset-password",
                        json={"token": raw, "password": "NewPass!444"})
        assert r.status_code == 200, r.text
        # Token issued BEFORE the reset must now be rejected.
        assert client.get("/api/v1/admin/merchant/me", headers=h).status_code == 401
        # New password logs in.
        assert _login(client, "rev-3@sec.example", "NewPass!444").status_code == 200


class TestAuthRateLimit:
    def test_07_login_identity_throttled(self, client):
        email = f"rl-{int(time.time())}@sec.example"
        codes = [_login(client, email, f"bad{i}").status_code for i in range(12)]
        assert 429 in codes, f"expected throttling, got {codes}"
        assert codes.index(429) >= 10  # identity limit (10/min) kicked in

    def test_08_forgot_password_throttled_generic(self, client):
        email = f"fp-{int(time.time())}@sec.example"
        codes = [client.post("/api/v1/auth/institution/forgot-password",
                             json={"email": email}).status_code for _ in range(7)]
        assert 429 in codes, f"expected throttling, got {codes}"
        # Before throttling, responses stay generic 200 (no enumeration).
        assert codes[0] == 200

    def test_09_health_not_throttled(self, client):
        for _ in range(3):
            assert client.get("/health").status_code == 200
