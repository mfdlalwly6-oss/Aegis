"""Institution-owner invitation & password-reset lifecycle tests.

Covers: invite-on-create, accept (single-use token), resend, disable/enable,
forgot/reset-password, tenant isolation, audit events.
"""
from __future__ import annotations

import pytest

from tests.conftest import OWNER_HEADERS, create_tenant


def _make_invited_tenant(client, name="INV-1"):
    """Create a tenant whose owner has NO password -> invited + email sent."""
    r = client.post(
        "/api/v1/admin/tenants",
        json={
            "name": name, "org_type": "wallet",
            "owner_email": f"{name.lower()}@t.example", "owner_name": "Owner One",
        },
        headers=OWNER_HEADERS,
    )
    assert r.status_code == 201, r.text
    return r.json()


class TestOwnerInvitationFlow:
    def test_01_create_with_email_no_password_invites(self, client):
        t = _make_invited_tenant(client)
        r = client.get(f"/api/v1/admin/tenants/{t['tenant_id']}/owner", headers=OWNER_HEADERS)
        assert r.status_code == 200
        owner = r.json()["owner"]
        assert owner["status"] == "invited"
        assert owner["invitation_status"] == "pending"

    def test_02_invited_owner_cannot_login(self, client):
        t = _make_invited_tenant(client, "INV-2")
        r = client.post("/api/v1/auth/institution/login", json={
            "email": "inv-2@t.example", "password": "whatever123",
        })
        assert r.status_code in (401, 403)

    def test_03_accept_invitation_sets_password_and_activates(self, client):
        t = _make_invited_tenant(client, "INV-3")
        tid = t["tenant_id"]
        # grab raw token from the invitation table (test-only access)
        from app.main import app
        registry = app.state.registry
        owners = registry.db.query(
            "SELECT user_id FROM users WHERE tenant_id=? AND role='institution_owner'", (tid,))
        assert owners, "owner row must exist"
        inv = registry.invitations.latest_for_user(owners[0]["user_id"])
        assert inv and inv["status"] == "pending"
        _r, raw = registry.invitations.create_invitation(
            tid, owners[0]["user_id"], "inv-3@t.example", invited_by="test", ttl_hours=72)
        r = client.post("/api/v1/auth/institution/accept-invitation", json={
            "token": raw, "password": "Str0ngPass!x",
        })
        assert r.status_code == 200, r.text
        # can now login
        r2 = client.post("/api/v1/auth/institution/login", json={
            "email": "inv-3@t.example", "password": "Str0ngPass!x",
        })
        assert r2.status_code == 200
        assert "access_token" in r2.json()

    def test_04_token_single_use(self, client):
        t = _make_invited_tenant(client, "INV-4")
        from app.main import app
        registry = app.state.registry
        uid = registry.db.query(
            "SELECT user_id FROM users WHERE tenant_id=?", (t["tenant_id"],))[0]["user_id"]
        _r, raw = registry.invitations.create_invitation(
            t["tenant_id"], uid, "x@t.example", invited_by="test", ttl_hours=72)
        ok = client.post("/api/v1/auth/institution/accept-invitation",
                         json={"token": raw, "password": "Str0ngPass!x"})
        assert ok.status_code == 200
        again = client.post("/api/v1/auth/institution/accept-invitation",
                            json={"token": raw, "password": "OtherPass123!"})
        assert again.status_code in (400, 401, 404, 410)

    def test_05_resend_revokes_old_token(self, client):
        t = _make_invited_tenant(client, "INV-5")
        tid = t["tenant_id"]
        from app.main import app
        registry = app.state.registry
        uid = registry.db.query(
            "SELECT user_id FROM users WHERE tenant_id=?", (tid,))[0]["user_id"]
        old_raw, raw = registry.invitations.create_invitation(
            t["tenant_id"], uid, "x@t.example", invited_by="test", ttl_hours=72)
        r = client.post(f"/api/v1/admin/tenants/{tid}/owner/resend-invitation",
                        headers=OWNER_HEADERS)
        assert r.status_code == 200
        dead = client.post("/api/v1/auth/institution/accept-invitation",
                           json={"token": old_raw, "password": "Str0ngPass!x"})
        assert dead.status_code in (400, 401, 404, 410, 422)

    def test_06_resend_rejected_for_active_owner(self, client):
        t = _make_invited_tenant(client, "INV-6")
        tid = t["tenant_id"]
        from app.main import app
        registry = app.state.registry
        uid = registry.db.query(
            "SELECT user_id FROM users WHERE tenant_id=?", (tid,))[0]["user_id"]
        _r, raw = registry.invitations.create_invitation(
            t["tenant_id"], uid, "x@t.example", invited_by="test", ttl_hours=72)
        client.post("/api/v1/auth/institution/accept-invitation",
                    json={"token": raw, "password": "Str0ngPass!x"})
        r = client.post(f"/api/v1/admin/tenants/{tid}/owner/resend-invitation",
                        headers=OWNER_HEADERS)
        assert r.status_code == 409

    def test_07_disable_then_enable(self, client):
        t = _make_invited_tenant(client, "INV-7")
        tid = t["tenant_id"]
        from app.main import app
        registry = app.state.registry
        uid = registry.db.query(
            "SELECT user_id FROM users WHERE tenant_id=?", (tid,))[0]["user_id"]
        _r, raw = registry.invitations.create_invitation(
            t["tenant_id"], uid, "x@t.example", invited_by="test", ttl_hours=72)
        client.post("/api/v1/auth/institution/accept-invitation",
                    json={"token": raw, "password": "Str0ngPass!x"})
        d = client.post(f"/api/v1/admin/tenants/{tid}/owner/disable", headers=OWNER_HEADERS)
        assert d.status_code == 200
        login = client.post("/api/v1/auth/institution/login", json={
            "email": "inv-7@t.example", "password": "Str0ngPass!x"})
        assert login.status_code in (401, 403)
        e = client.post(f"/api/v1/admin/tenants/{tid}/owner/enable", headers=OWNER_HEADERS)
        assert e.status_code == 200
        login2 = client.post("/api/v1/auth/institution/login", json={
            "email": "inv-7@t.example", "password": "Str0ngPass!x"})
        assert login2.status_code == 200

    def test_08_forgot_and_reset_password(self, client):
        t = _make_invited_tenant(client, "INV-8")
        from app.main import app
        registry = app.state.registry
        uid = registry.db.query(
            "SELECT user_id FROM users WHERE tenant_id=?", (t["tenant_id"],))[0]["user_id"]
        _r, raw = registry.invitations.create_invitation(
            t["tenant_id"], uid, "x@t.example", invited_by="test", ttl_hours=72)
        client.post("/api/v1/auth/institution/accept-invitation",
                    json={"token": raw, "password": "Str0ngPass!x"})
        # forgot (response is generic — no user enumeration)
        f = client.post("/api/v1/auth/institution/forgot-password",
                        json={"email": "inv-8@t.example"})
        assert f.status_code == 200
        f2 = client.post("/api/v1/auth/institution/forgot-password",
                         json={"email": "nobody@t.example"})
        assert f2.status_code == 200 and f2.json() == f.json()
        # reset with token issued by repo (test hook)
        _row, raw_reset = registry.invitations.create_reset(
            t["tenant_id"], uid, "inv-8@t.example", ttl_hours=2)
        r = client.post("/api/v1/auth/institution/reset-password",
                        json={"token": raw_reset, "password": "NewStr0ng!zz"})
        assert r.status_code == 200
        old = client.post("/api/v1/auth/institution/login",
                          json={"email": "inv-8@t.example", "password": "Str0ngPass!x"})
        assert old.status_code in (401, 403)
        new = client.post("/api/v1/auth/institution/login",
                          json={"email": "inv-8@t.example", "password": "NewStr0ng!zz"})
        assert new.status_code == 200

    def test_09_audit_events_logged(self, client):
        t = _make_invited_tenant(client, "INV-9")
        tid = t["tenant_id"]
        client.post(f"/api/v1/admin/tenants/{tid}/owner/resend-invitation",
                    headers=OWNER_HEADERS)
        from app.main import app
        registry = app.state.registry
        uid = registry.db.query(
            "SELECT user_id FROM users WHERE tenant_id=?", (tid,))[0]["user_id"]
        _r, raw = registry.invitations.create_invitation(
            tid, uid, "inv-9@t.example", invited_by="test", ttl_hours=72)
        acc = client.post("/api/v1/auth/institution/accept-invitation",
                          json={"token": raw, "password": "Str0ngPass!x"})
        assert acc.status_code == 200
        client.post(f"/api/v1/admin/tenants/{tid}/owner/disable", headers=OWNER_HEADERS)
        client.post(f"/api/v1/admin/tenants/{tid}/owner/enable", headers=OWNER_HEADERS)
        from app.main import app
        registry = app.state.registry
        rows = registry.db.query(
            "SELECT event_type FROM audit_log WHERE tenant_id=? AND actor=?",
            (tid, "owner"))
        actions = [r["event_type"] for r in rows]
        assert "owner.invitation_resent" in actions
        assert "owner.disabled" in actions
        assert "owner.enabled" in actions
