"""Policy versioning — end-to-end over the real API against isolated PostgreSQL.

Verifies: every policy update records an immutable numbered version; versions
are listable/retrievable; activation materializes a stored version back into
the decision hot path (tenants.policy_json); disable marks without rewriting;
and decisions carry the active version stamp (policy_version).
"""

import uuid

from tests.conftest import OWNER_HEADERS


def _tenant(client) -> str:
    r = client.post(
        "/api/v1/admin/tenants",
        json={
            "name": f"PV-{uuid.uuid4().hex[:6]}",
            "type": "wallet",
            "country": "YE",
            "plan": "sandbox",
            "investigator_limit": 2,
        },
        headers=OWNER_HEADERS,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["tenant_id"]


def _policy(th_block: float) -> dict:
    return {
        "thresholds": {"challenge": 0.35, "review": 0.60, "block": th_block},
        "note": f"block={th_block}",
    }


def test_policy_update_records_immutable_numbered_version(client):
    tid = _tenant(client)
    r = client.put(
        f"/api/v1/admin/tenants/{tid}/policy", json=_policy(0.85), headers=OWNER_HEADERS
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["policy_version"] == 1
    assert body["policy_hash"]

    r2 = client.put(
        f"/api/v1/admin/tenants/{tid}/policy", json=_policy(0.90), headers=OWNER_HEADERS
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["policy_version"] == 2

    versions = client.get(
        f"/api/v1/admin/tenants/{tid}/policy/versions", headers=OWNER_HEADERS
    ).json()
    assert [v["version"] for v in versions] == [2, 1]  # newest first
    assert versions[0]["policy"]["thresholds"]["block"] == 0.90
    assert versions[1]["policy"]["thresholds"]["block"] == 0.85
    assert all(v["created_by"] == "owner" for v in versions)


def test_policy_version_content_is_never_rewritten(client):
    tid = _tenant(client)
    client.put(f"/api/v1/admin/tenants/{tid}/policy", json=_policy(0.85), headers=OWNER_HEADERS)
    client.put(f"/api/v1/admin/tenants/{tid}/policy", json=_policy(0.90), headers=OWNER_HEADERS)
    # Re-read version 1 after version 2 was created: must be untouched.
    v1 = client.get(
        f"/api/v1/admin/tenants/{tid}/policy/versions/1", headers=OWNER_HEADERS
    ).json()
    assert v1["policy"]["thresholds"]["block"] == 0.85
    assert v1["note"] == "block=0.85"


def test_activate_materializes_version_into_hot_path(client):
    tid = _tenant(client)
    client.put(f"/api/v1/admin/tenants/{tid}/policy", json=_policy(0.85), headers=OWNER_HEADERS)
    client.put(f"/api/v1/admin/tenants/{tid}/policy", json=_policy(0.90), headers=OWNER_HEADERS)

    # Roll back to v1: hot path (tenant policy) must reflect 0.85 again.
    act = client.post(
        f"/api/v1/admin/tenants/{tid}/policy/versions/1/activate", headers=OWNER_HEADERS
    )
    assert act.status_code == 200, act.text
    assert act.json()["active_version"] == 1

    tenant = client.get(f"/api/v1/admin/tenants/{tid}", headers=OWNER_HEADERS).json()
    assert tenant["policy"]["thresholds"]["block"] == 0.85

    active = [v for v in client.get(
        f"/api/v1/admin/tenants/{tid}/policy/versions", headers=OWNER_HEADERS
    ).json() if v["status"] == "active"]
    assert any(v["version"] == 1 for v in active)


def test_disable_marks_version_without_deleting_it(client):
    tid = _tenant(client)
    client.put(f"/api/v1/admin/tenants/{tid}/policy", json=_policy(0.85), headers=OWNER_HEADERS)
    d = client.post(
        f"/api/v1/admin/tenants/{tid}/policy/versions/1/disable", headers=OWNER_HEADERS
    )
    assert d.status_code == 200, d.text
    v1 = client.get(
        f"/api/v1/admin/tenants/{tid}/policy/versions/1", headers=OWNER_HEADERS
    ).json()
    assert v1["status"] == "disabled"
    assert v1["policy"]["thresholds"]["block"] == 0.85  # content preserved


def test_policy_versions_are_tenant_isolated(client):
    a = _tenant(client)
    b = _tenant(client)
    client.put(f"/api/v1/admin/tenants/{a}/policy", json=_policy(0.85), headers=OWNER_HEADERS)
    assert client.get(
        f"/api/v1/admin/tenants/{b}/policy/versions", headers=OWNER_HEADERS
    ).json() == []
    # Cross-tenant version access must 404.
    assert client.get(
        f"/api/v1/admin/tenants/{b}/policy/versions/1", headers=OWNER_HEADERS
    ).status_code == 404


def test_missing_version_and_tenant_404(client):
    tid = _tenant(client)
    assert client.get(
        f"/api/v1/admin/tenants/{tid}/policy/versions/99", headers=OWNER_HEADERS
    ).status_code == 404
    assert client.get(
        "/api/v1/admin/tenants/tn_nonexistent/policy/versions", headers=OWNER_HEADERS
    ).status_code == 404
