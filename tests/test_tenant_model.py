"""Multi-tenant model: limits, tenant-scoped investigators, isolation, review flow."""

import uuid

from conftest import OWNER_HEADERS, create_tenant

BASE = "/api/v1"


def test_tenant_create_and_investigator_limit(client):
    r = client.post(
        f"{BASE}/admin/tenants",
        json={
            "name": f"Bank-{uuid.uuid4().hex[:6]}",
            "type": "bank",
            "country": "YE",
            "plan": "production",
            "investigator_limit": 2,
        },
        headers=OWNER_HEADERS,
    )
    assert r.status_code == 201, r.text
    tid = r.json()["tenant_id"]
    assert r.json()["investigator_limit"] == 2
    for i in (1, 2):
        rr = client.post(
            f"{BASE}/admin/tenants/{tid}/investigators",
            json={"email": f"inv{i}@t.test", "name": f"Inv{i}", "password": "InvPass!2026"},
            headers=OWNER_HEADERS,
        )
        assert rr.status_code == 201, rr.text
    rr = client.post(
        f"{BASE}/admin/tenants/{tid}/investigators",
        json={"email": "inv3@t.test", "name": "Inv3", "password": "InvPass!2026"},
        headers=OWNER_HEADERS,
    )
    assert rr.status_code == 409, rr.text
    rr = client.put(f"{BASE}/admin/tenants/{tid}", json={"investigator_limit": 3}, headers=OWNER_HEADERS)
    assert rr.status_code == 200, rr.text
    rr = client.post(
        f"{BASE}/admin/tenants/{tid}/investigators",
        json={"email": "inv3@t.test", "name": "Inv3", "password": "InvPass!2026"},
        headers=OWNER_HEADERS,
    )
    assert rr.status_code == 201, rr.text


def test_investigator_tenant_scope_and_suspend(client):
    ta = create_tenant(client, name=f"A-{uuid.uuid4().hex[:6]}", investigator_limit=3)
    tb = create_tenant(client, name=f"B-{uuid.uuid4().hex[:6]}", investigator_limit=3)
    ia = client.post(
        f"{BASE}/admin/tenants/{ta['tenant_id']}/investigators",
        json={"email": f"ia{uuid.uuid4().hex[:6]}@a.test", "name": "IA", "password": "InvPass!2026"},
        headers=OWNER_HEADERS,
    ).json()
    lg = client.post(f"{BASE}/investigator/login", json={"email": ia["email"], "password": "InvPass!2026"})
    assert lg.status_code == 200, lg.text
    tok = lg.json()["access_token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    me = client.get(f"{BASE}/investigator/me", headers=hdr)
    assert me.status_code == 200, me.text
    assert me.json()["tenant_id"] == ta["tenant_id"]
    assert me.json()["tenant_id"] != tb["tenant_id"]
    susp = client.post(
        f"{BASE}/admin/tenants/{ta['tenant_id']}/investigators/{ia['investigator_id']}/suspend",
        json={},
        headers=OWNER_HEADERS,
    )
    assert susp.status_code == 200, susp.text
    lg2 = client.post(f"{BASE}/investigator/login", json={"email": ia["email"], "password": "InvPass!2026"})
    assert lg2.status_code == 401, lg2.text
    act = client.post(
        f"{BASE}/admin/tenants/{ta['tenant_id']}/investigators/{ia['investigator_id']}/activate",
        json={},
        headers=OWNER_HEADERS,
    )
    assert act.status_code == 200, act.text
    lg3 = client.post(f"{BASE}/investigator/login", json={"email": ia["email"], "password": "InvPass!2026"})
    assert lg3.status_code == 200, lg3.text


def test_institution_owner_login_and_scope(client):
    u = uuid.uuid4().hex[:6]
    ta = create_tenant(
        client,
        name=f"O-{u}",
        investigator_limit=3,
        owner_email=f"owner{u}@o.test",
        owner_password="OwnerPass!2026",
        owner_name="Sara",
    )
    lg = client.post(
        f"{BASE}/auth/institution/login", json={"email": f"owner{u}@o.test", "password": "OwnerPass!2026"}
    )
    assert lg.status_code == 200, lg.text
    tok = lg.json()["access_token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    dash = client.get(f"{BASE}/admin/merchant/dashboard", headers=hdr)
    assert dash.status_code == 200, dash.text
    data = dash.json()
    assert isinstance(data, dict), data
    assert data.get("tenant_id") == ta["tenant_id"], data
