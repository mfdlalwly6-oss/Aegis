"""Decision-threshold management E2E — default + per-tenant overrides.

Covers: default use, default edit propagation, override lifecycle
(create/edit/disable/enable/delete/revert), bounds + ordering validation,
permissions, tenant isolation, audit trail, and decision-engine consumption.
"""
from tests.conftest import OWNER_HEADERS, create_tenant

D = {"challenge": 0.35, "review": 0.60, "block": 0.80}
BANK_A = {"challenge": 0.30, "review": 0.55, "block": 0.75, "fx_missing_action": "block"}


def _th(client, tid):
    r = client.get(f"/api/v1/admin/tenants/{tid}/thresholds", headers=OWNER_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


class TestDefaultThresholds:
    def test_01_default_thresholds_seeded(self, client):
        """1. Institution without override → platform default (0.35/0.60/0.80, fx=default).

        The stored profile fx value is 'default' (follows the global behavior);
        the actual resolution to the global action (currently review) happens
        at decision time inside PolicyEngine — verified by test_fx_missing_options.
        """
        t = create_tenant(client, name="TH-Default-T")
        eff = _th(client, t["tenant_id"])["effective"]
        assert eff["source"] == "default"
        for k in D:
            assert abs(eff[k] - D[k]) < 1e-9
        assert eff["fx_missing_action"] == "default"
        r = client.get("/api/v1/admin/thresholds/default", headers=OWNER_HEADERS)
        assert abs(r.json()["challenge"] - 0.35) < 1e-9
        assert r.json()["fx_missing_action"] == "default"

    def test_02_default_edit_propagates_to_non_override_tenants(self, client):
        """2. Editing default thresholds → tenants without override inherit instantly."""
        t = create_tenant(client, name="TH-Propagate")
        tid = t["tenant_id"]
        new = {"challenge": 0.40, "review": 0.65, "block": 0.85, "fx_missing_action": "review"}
        r = client.put("/api/v1/admin/thresholds/default", json=new, headers=OWNER_HEADERS)
        assert r.status_code == 200, r.text
        eff = _th(client, tid)["effective"]
        assert eff["source"] == "default"
        assert abs(eff["challenge"] - 0.40) < 1e-9
        # restore default for other tests
        client.put("/api/v1/admin/thresholds/default", json={**D, "fx_missing_action": "review"}, headers=OWNER_HEADERS)

    def test_03_default_edit_does_not_touch_active_override(self, client):
        """3. A tenant with an ACTIVE override is NOT affected by default edits."""
        t = create_tenant(client, name="TH-Iso-Default")
        tid = t["tenant_id"]
        client.put(f"/api/v1/admin/tenants/{tid}/thresholds", json=BANK_A, headers=OWNER_HEADERS)
        client.put("/api/v1/admin/thresholds/default",
                   json={"challenge": 0.45, "review": 0.70, "block": 0.90, "fx_missing_action": "review"},
                   headers=OWNER_HEADERS)
        eff = _th(client, tid)["effective"]
        assert eff["source"] == "override"
        assert abs(eff["challenge"] - 0.30) < 1e-9
        assert abs(eff["block"] - 0.75) < 1e-9
        client.put("/api/v1/admin/thresholds/default", json={**D, "fx_missing_action": "review"}, headers=OWNER_HEADERS)
        client.delete(f"/api/v1/admin/tenants/{tid}/thresholds", headers=OWNER_HEADERS)

    def test_04_bounds_validation_rejects_out_of_range(self, client):
        """4. Out-of-bounds values are rejected (challenge max 0.50)."""
        t = create_tenant(client, name="TH-Bounds")
        tid = t["tenant_id"]
        bad = {"challenge": 0.60, "review": 0.65, "block": 0.85}  # challenge > 0.50 bound
        r = client.put(f"/api/v1/admin/tenants/{tid}/thresholds", json=bad, headers=OWNER_HEADERS)
        assert r.status_code == 422

    def test_05_ordering_validation_rejects_inverted(self, client):
        """5. challenge > review is rejected (ordering invariant)."""
        t = create_tenant(client, name="TH-Order")
        tid = t["tenant_id"]
        bad = {"challenge": 0.50, "review": 0.45, "block": 0.85}  # review < challenge
        r = client.put(f"/api/v1/admin/tenants/{tid}/thresholds", json=bad, headers=OWNER_HEADERS)
        assert r.status_code == 422

    def test_06_fx_missing_action_four_options(self, client):
        """6. fx_missing_action accepts the four official options (incl. explicit allow)."""
        t = create_tenant(client, name="TH-FX")
        tid = t["tenant_id"]
        for fx in ("default", "review", "block", "allow"):
            r = client.put(f"/api/v1/admin/tenants/{tid}/thresholds",
                           json={**D, "fx_missing_action": fx}, headers=OWNER_HEADERS)
            assert r.status_code == 200, (fx, r.text)
            assert r.json()["fx_missing_action"] == fx
        # an invalid value is still rejected
        r = client.put(f"/api/v1/admin/tenants/{tid}/thresholds",
                       json={**D, "fx_missing_action": "xyz"}, headers=OWNER_HEADERS)
        assert r.status_code == 422
        client.delete(f"/api/v1/admin/tenants/{tid}/thresholds", headers=OWNER_HEADERS)


class TestThresholdOverrides:
    def test_07_create_override_wins(self, client):
        """7. Creating an override → effective thresholds come from the override."""
        t = create_tenant(client, name="TH-Create")
        tid = t["tenant_id"]
        r = client.put(f"/api/v1/admin/tenants/{tid}/thresholds", json=BANK_A, headers=OWNER_HEADERS)
        assert r.status_code == 200, r.text
        eff = _th(client, tid)["effective"]
        assert eff["source"] == "override"
        assert abs(eff["challenge"] - 0.30) < 1e-9
        assert eff["fx_missing_action"] == "block"
        client.delete(f"/api/v1/admin/tenants/{tid}/thresholds", headers=OWNER_HEADERS)

    def test_08_edit_override_updates_values(self, client):
        """8. Editing an override updates its values."""
        t = create_tenant(client, name="TH-Edit")
        tid = t["tenant_id"]
        client.put(f"/api/v1/admin/tenants/{tid}/thresholds", json=BANK_A, headers=OWNER_HEADERS)
        edited = {"challenge": 0.25, "review": 0.50, "block": 0.70, "fx_missing_action": "review"}
        client.put(f"/api/v1/admin/tenants/{tid}/thresholds", json=edited, headers=OWNER_HEADERS)
        eff = _th(client, tid)["effective"]
        assert abs(eff["challenge"] - 0.25) < 1e-9
        assert eff["fx_missing_action"] == "review"
        client.delete(f"/api/v1/admin/tenants/{tid}/thresholds", headers=OWNER_HEADERS)

    def test_09_disable_reverts_to_default(self, client):
        """9. Disabling an override → effective reverts to default instantly."""
        t = create_tenant(client, name="TH-Disable")
        tid = t["tenant_id"]
        client.put(f"/api/v1/admin/tenants/{tid}/thresholds", json=BANK_A, headers=OWNER_HEADERS)
        r = client.post(f"/api/v1/admin/tenants/{tid}/thresholds/disable", headers=OWNER_HEADERS)
        assert r.status_code == 200, r.text
        data = _th(client, tid)
        assert data["override"]["active"] == 0
        assert data["effective"]["source"] == "default"
        for k in D:
            assert abs(data["effective"][k] - D[k]) < 1e-9
        client.delete(f"/api/v1/admin/tenants/{tid}/thresholds", headers=OWNER_HEADERS)

    def test_10_enable_re_activates_override(self, client):
        """10. Re-enabling a disabled override → effective uses it again."""
        t = create_tenant(client, name="TH-Enable")
        tid = t["tenant_id"]
        client.put(f"/api/v1/admin/tenants/{tid}/thresholds", json=BANK_A, headers=OWNER_HEADERS)
        client.post(f"/api/v1/admin/tenants/{tid}/thresholds/disable", headers=OWNER_HEADERS)
        client.post(f"/api/v1/admin/tenants/{tid}/thresholds/enable", headers=OWNER_HEADERS)
        data = _th(client, tid)
        assert data["override"]["active"] == 1
        assert data["effective"]["source"] == "override"
        client.delete(f"/api/v1/admin/tenants/{tid}/thresholds", headers=OWNER_HEADERS)

    def test_11_delete_reverts_to_default(self, client):
        """11. Deleting an override → tenant reverts to default, row is gone."""
        t = create_tenant(client, name="TH-Delete")
        tid = t["tenant_id"]
        client.put(f"/api/v1/admin/tenants/{tid}/thresholds", json=BANK_A, headers=OWNER_HEADERS)
        r = client.delete(f"/api/v1/admin/tenants/{tid}/thresholds", headers=OWNER_HEADERS)
        assert r.status_code == 200, r.text
        assert r.json()["reverted_to"] == "default"
        data = _th(client, tid)
        assert data["override"] is None
        assert data["effective"]["source"] == "default"


class TestSecurityAndAudit:
    def test_12_endpoints_require_owner(self, client):
        """12. All threshold endpoints reject unauthenticated requests."""
        t = create_tenant(client, name="TH-Auth")
        tid = t["tenant_id"]
        assert client.get("/api/v1/admin/thresholds/default").status_code == 401
        assert client.get("/api/v1/admin/thresholds/overrides").status_code == 401
        assert client.get(f"/api/v1/admin/tenants/{tid}/thresholds").status_code == 401
        assert client.put("/api/v1/admin/thresholds/default", json=D).status_code == 401
        assert client.put(f"/api/v1/admin/tenants/{tid}/thresholds", json=D).status_code == 401
        assert client.delete(f"/api/v1/admin/tenants/{tid}/thresholds").status_code == 401

    def test_13_audit_trail_records_every_mutation(self, client):
        """13. Audit log records create/update/disable/enable/delete/default-edit."""
        t = create_tenant(client, name="TH-Audit")
        tid = t["tenant_id"]
        client.put(f"/api/v1/admin/tenants/{tid}/thresholds", json=BANK_A, headers=OWNER_HEADERS)
        client.post(f"/api/v1/admin/tenants/{tid}/thresholds/disable", headers=OWNER_HEADERS)
        client.post(f"/api/v1/admin/tenants/{tid}/thresholds/enable", headers=OWNER_HEADERS)
        client.delete(f"/api/v1/admin/tenants/{tid}/thresholds", headers=OWNER_HEADERS)
        client.put("/api/v1/admin/thresholds/default", json={**D, "fx_missing_action": "review"}, headers=OWNER_HEADERS)
        r = client.get("/api/v1/admin/audit?limit=400", headers=OWNER_HEADERS)
        events = r.json()
        rows = events if isinstance(events, list) else events.get("events", [])
        types = {x.get("event_type") or x.get("action") for x in rows}
        assert "thresholds.override.created" in types
        assert "thresholds.override.disabled" in types
        assert "thresholds.override.enabled" in types
        assert "thresholds.override.deleted" in types
        assert "thresholds.default.updated" in types

    def test_14_overrides_list_reflects_state(self, client):
        """14. Overrides list shows only tenants with overrides (active or disabled)."""
        t = create_tenant(client, name="TH-List")
        tid = t["tenant_id"]
        client.put(f"/api/v1/admin/tenants/{tid}/thresholds", json=BANK_A, headers=OWNER_HEADERS)
        r = client.get("/api/v1/admin/thresholds/overrides", headers=OWNER_HEADERS)
        ids = {o["tenant_id"] for o in r.json()["overrides"]}
        assert tid in ids
        client.delete(f"/api/v1/admin/tenants/{tid}/thresholds", headers=OWNER_HEADERS)
        r2 = client.get("/api/v1/admin/thresholds/overrides", headers=OWNER_HEADERS)
        ids2 = {o["tenant_id"] for o in r2.json()["overrides"]}
        assert tid not in ids2

    def test_15_unknown_tenant_404(self, client):
        """15. Threshold ops on a non-existent tenant → 404."""
        assert client.get("/api/v1/admin/tenants/tn_nope_404/thresholds", headers=OWNER_HEADERS).status_code == 404
        assert client.put("/api/v1/admin/tenants/tn_nope_404/thresholds", json=D, headers=OWNER_HEADERS).status_code == 404

    def test_16_override_row_versioned_via_timestamps(self, client):
        """16. Override rows carry created_at/updated_at; edits bump updated_at."""
        t = create_tenant(client, name="TH-Ver")
        tid = t["tenant_id"]
        r1 = client.put(f"/api/v1/admin/tenants/{tid}/thresholds", json=BANK_A, headers=OWNER_HEADERS).json()
        assert r1["created_at"] and r1["updated_at"]
        edited = {"challenge": 0.28, "review": 0.52, "block": 0.72, "fx_missing_action": "block"}
        r2 = client.put(f"/api/v1/admin/tenants/{tid}/thresholds", json=edited, headers=OWNER_HEADERS).json()
        assert r2["profile_id"] == r1["profile_id"]
        assert r2["updated_at"] >= r1["updated_at"]
        client.delete(f"/api/v1/admin/tenants/{tid}/thresholds", headers=OWNER_HEADERS)
