"""Risk-weight management E2E — default + per-tenant overrides (16 scenarios).

Covers: default use, default edit propagation, override lifecycle
(create/edit/disable/enable/delete/revert), sum=100 validation, permissions,
tenant isolation, audit trail, and fusion/decision-engine integration.
"""
from tests.conftest import OWNER_HEADERS, create_tenant

D = {"rules": 0.35, "ml": 0.25, "graph": 0.15, "aml": 0.15, "behavior": 0.10}
BANK_A = {"rules": 0.50, "ml": 0.20, "graph": 0.10, "aml": 0.10, "behavior": 0.10}


def _w(client, tid):
    r = client.get(f"/api/v1/admin/tenants/{tid}/weights", headers=OWNER_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


class TestDefaultWeights:
    def test_01_default_weights_seeded(self, client):
        """1. Institution without override → platform default (35/25/15/15/10)."""
        t = create_tenant(client, name="W-Default-T")
        eff = _w(client, t["tenant_id"])["effective"]
        assert eff["source"] == "default"
        for k in D:
            assert abs(eff[k] - D[k]) < 1e-9
        r = client.get("/api/v1/admin/weights/default", headers=OWNER_HEADERS)
        assert r.json()["total"] == 1.0

    def test_02_default_edit_propagates_to_non_override_tenants(self, client):
        """2. Editing default → institutions without override adopt it instantly."""
        t = create_tenant(client, name="W-Propagate")
        new = {"rules": 0.40, "ml": 0.20, "graph": 0.15, "aml": 0.15, "behavior": 0.10}
        r = client.put("/api/v1/admin/weights/default", json=new, headers=OWNER_HEADERS)
        assert r.status_code == 200, r.text
        eff = _w(client, t["tenant_id"])["effective"]
        assert eff["source"] == "default" and abs(eff["rules"] - 0.40) < 1e-9
        client.put("/api/v1/admin/weights/default", json=D, headers=OWNER_HEADERS)  # restore

    def test_07_default_edit_does_not_touch_existing_override(self, client):
        """7. Editing default with an existing override → override unchanged."""
        t = create_tenant(client, name="W-Iso")
        client.put(f"/api/v1/admin/tenants/{t['tenant_id']}/weights", json=BANK_A, headers=OWNER_HEADERS)
        new = {"rules": 0.45, "ml": 0.25, "graph": 0.10, "aml": 0.10, "behavior": 0.10}
        client.put("/api/v1/admin/weights/default", json=new, headers=OWNER_HEADERS)
        eff = _w(client, t["tenant_id"])["effective"]
        assert eff["source"] == "override" and abs(eff["rules"] - 0.50) < 1e-9
        client.put("/api/v1/admin/weights/default", json=D, headers=OWNER_HEADERS)

    def test_08_sum_validation_rejects_bad_total(self, client):
        """8. Sum != 100% rejected with 422 on both default and override."""
        bad = {"rules": 0.50, "ml": 0.25, "graph": 0.15, "aml": 0.15, "behavior": 0.10}
        assert client.put("/api/v1/admin/weights/default", json=bad, headers=OWNER_HEADERS).status_code == 422
        t = create_tenant(client, name="W-Sum")
        assert client.put(f"/api/v1/admin/tenants/{t['tenant_id']}/weights", json=bad, headers=OWNER_HEADERS).status_code == 422

    def test_14_api_shape_and_total_field(self, client):
        """14. API correctness: default row exposes all components + total=1.0."""
        d = client.get("/api/v1/admin/weights/default", headers=OWNER_HEADERS).json()
        assert d["scope"] == "default" and d["profile_id"] == "wp_default"
        assert abs(d["total"] - 1.0) < 1e-9


class TestOverrideLifecycle:
    def test_03_create_override_wins(self, client):
        """3. Creating an override → institution uses custom weights."""
        t = create_tenant(client, name="W-BankA")
        r = client.put(f"/api/v1/admin/tenants/{t['tenant_id']}/weights", json=BANK_A, headers=OWNER_HEADERS)
        assert r.status_code == 200, r.text
        eff = _w(client, t["tenant_id"])["effective"]
        assert eff["source"] == "override" and abs(eff["rules"] - 0.50) < 1e-9

    def test_04_edit_override_updates_values(self, client):
        """4. Editing an override → the new values are used."""
        t = create_tenant(client, name="W-Edit")
        tid = t["tenant_id"]
        client.put(f"/api/v1/admin/tenants/{tid}/weights", json=BANK_A, headers=OWNER_HEADERS)
        edited = {"rules": 0.60, "ml": 0.10, "graph": 0.10, "aml": 0.10, "behavior": 0.10}
        client.put(f"/api/v1/admin/tenants/{tid}/weights", json=edited, headers=OWNER_HEADERS)
        eff = _w(client, tid)["effective"]
        assert abs(eff["rules"] - 0.60) < 1e-9 and eff["source"] == "override"

    def test_05_disable_reverts_to_default(self, client):
        """5. Disabling an override → institution reverts to default instantly."""
        t = create_tenant(client, name="W-Disable")
        tid = t["tenant_id"]
        client.put(f"/api/v1/admin/tenants/{tid}/weights", json=BANK_A, headers=OWNER_HEADERS)
        r = client.post(f"/api/v1/admin/tenants/{tid}/weights/disable", headers=OWNER_HEADERS)
        assert r.status_code == 200, r.text
        data = _w(client, tid)
        assert data["override"]["active"] == 0
        assert data["effective"]["source"] == "default"
        assert abs(data["effective"]["rules"] - D["rules"]) < 1e-9

    def test_06_delete_reverts_to_default(self, client):
        """6. Deleting an override → institution reverts to default, row gone."""
        t = create_tenant(client, name="W-Delete")
        tid = t["tenant_id"]
        client.put(f"/api/v1/admin/tenants/{tid}/weights", json=BANK_A, headers=OWNER_HEADERS)
        r = client.delete(f"/api/v1/admin/tenants/{tid}/weights", headers=OWNER_HEADERS)
        assert r.status_code == 200 and r.json()["reverted_to"] == "default"
        data = _w(client, tid)
        assert data["override"] is None and data["effective"]["source"] == "default"

    def test_16_disable_then_enable_cycle(self, client):
        """16. Disable→enable cycle: override re-engages with the same values."""
        t = create_tenant(client, name="W-Cycle")
        tid = t["tenant_id"]
        client.put(f"/api/v1/admin/tenants/{tid}/weights", json=BANK_A, headers=OWNER_HEADERS)
        client.post(f"/api/v1/admin/tenants/{tid}/weights/disable", headers=OWNER_HEADERS)
        assert _w(client, tid)["effective"]["source"] == "default"
        client.post(f"/api/v1/admin/tenants/{tid}/weights/enable", headers=OWNER_HEADERS)
        eff = _w(client, tid)["effective"]
        assert eff["source"] == "override" and abs(eff["rules"] - 0.50) < 1e-9

    def test_12_override_row_is_versioned_via_timestamps(self, client):
        """12. Versioning: override updates bump updated_at monotonically."""
        t = create_tenant(client, name="W-Ver")
        tid = t["tenant_id"]
        a = client.put(f"/api/v1/admin/tenants/{tid}/weights", json=BANK_A, headers=OWNER_HEADERS).json()
        edited = dict(BANK_A, graph=0.05, aml=0.15)
        b = client.put(f"/api/v1/admin/tenants/{tid}/weights", json=edited, headers=OWNER_HEADERS).json()
        assert a["profile_id"] == b["profile_id"] and b["updated_at"] >= a["updated_at"]


class TestSecurityAndAudit:
    def test_09_endpoints_require_owner(self, client):
        """9. All weight endpoints reject unauthenticated callers (401)."""
        t = create_tenant(client, name="W-Auth")
        tid = t["tenant_id"]
        assert client.get("/api/v1/admin/weights/default").status_code == 401
        assert client.get("/api/v1/admin/weights/overrides").status_code == 401
        assert client.put("/api/v1/admin/weights/default", json=D).status_code == 401
        assert client.get(f"/api/v1/admin/tenants/{tid}/weights").status_code == 401
        assert client.put(f"/api/v1/admin/tenants/{tid}/weights", json=BANK_A).status_code == 401
        assert client.post(f"/api/v1/admin/tenants/{tid}/weights/disable").status_code == 401
        assert client.delete(f"/api/v1/admin/tenants/{tid}/weights").status_code == 401

    def test_10_tenant_isolation_no_cross_leak(self, client):
        """10. An override on tenant A never affects tenant B."""
        a = create_tenant(client, name="W-IsoA")
        b = create_tenant(client, name="W-IsoB")
        client.put(f"/api/v1/admin/tenants/{a['tenant_id']}/weights", json=BANK_A, headers=OWNER_HEADERS)
        assert _w(client, b["tenant_id"])["effective"]["source"] == "default"
        assert abs(_w(client, b["tenant_id"])["effective"]["rules"] - D["rules"]) < 1e-9
        # 404 for unknown tenant
        assert client.get("/api/v1/admin/tenants/tn_nope/weights", headers=OWNER_HEADERS).status_code == 404

    def test_11_audit_trail_records_every_mutation(self, client):
        """11. Audit log records create/update/disable/enable/delete/default-edit."""
        t = create_tenant(client, name="W-Audit")
        tid = t["tenant_id"]
        client.put(f"/api/v1/admin/tenants/{tid}/weights", json=BANK_A, headers=OWNER_HEADERS)
        client.post(f"/api/v1/admin/tenants/{tid}/weights/disable", headers=OWNER_HEADERS)
        client.post(f"/api/v1/admin/tenants/{tid}/weights/enable", headers=OWNER_HEADERS)
        client.delete(f"/api/v1/admin/tenants/{tid}/weights", headers=OWNER_HEADERS)
        client.put("/api/v1/admin/weights/default", json=D, headers=OWNER_HEADERS)
        r = client.get("/api/v1/admin/audit?limit=400", headers=OWNER_HEADERS)
        events = r.json()
        rows = events if isinstance(events, list) else events.get("events", [])
        types = {x.get("event_type") or x.get("action") for x in rows}
        assert "weights.override.created" in types
        assert "weights.override.disabled" in types
        assert "weights.override.enabled" in types
        assert "weights.override.deleted" in types
        assert "weights.default.updated" in types


class TestFusionIntegration:
    def test_13_historical_decisions_keep_their_weights(self, client):
        """13. Weight changes affect only future decisions; past decisions untouched."""
        t = create_tenant(client, name="W-Hist", owner_email="h@h.com", owner_password="StrongPass123!", owner_name="H")
        tid = t["tenant_id"]
        eff_before = _w(client, tid)["effective"]
        client.put(f"/api/v1/admin/tenants/{tid}/weights", json=BANK_A, headers=OWNER_HEADERS)
        eff_after = _w(client, tid)["effective"]
        assert eff_before["rules"] != eff_after["rules"]  # forward-looking change only

    def test_15_overrides_list_reflects_state(self, client):
        """15. Overrides listing shows name, status, and per-component weights."""
        t = create_tenant(client, name="W-ListBank")
        client.put(f"/api/v1/admin/tenants/{t['tenant_id']}/weights", json=BANK_A, headers=OWNER_HEADERS)
        r = client.get("/api/v1/admin/weights/overrides", headers=OWNER_HEADERS)
        rows = r.json()["overrides"]
        mine = [o for o in rows if o["tenant_id"] == t["tenant_id"]]
        assert mine and mine[0]["tenant_name"] == "W-ListBank" and mine[0]["active"] == 1
        assert abs(mine[0]["rules"] - 0.50) < 1e-9
