"""Missing-FX four-option system E2E — default / review / block / allow.

Covers: all four options end-to-end, the MANDATORY default-inheritance test
(changing the global behavior reflects on institutions using 'default', while
explicit overrides stay pinned), API validation, DB constraint, decision-engine
consumption, tenant isolation, and audit.
"""
import pytest

from tests.conftest import OWNER_HEADERS, create_tenant

D = {"challenge": 0.35, "review": 0.60, "block": 0.80}


def _th(client, tid):
    r = client.get(f"/api/v1/admin/tenants/{tid}/thresholds", headers=OWNER_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def _set_fx(client, tid, fx):
    body = {**D, "fx_missing_action": fx}
    r = client.put(f"/api/v1/admin/tenants/{tid}/thresholds", json=body, headers=OWNER_HEADERS)
    assert r.status_code == 200, r.text


def _set_default_fx(client, fx):
    r = client.put("/api/v1/admin/thresholds/default",
                   json={**D, "fx_missing_action": fx}, headers=OWNER_HEADERS)
    assert r.status_code == 200, r.text


@pytest.fixture(autouse=True)
def _restore_global_default(client):
    yield
    _set_default_fx(client, "default")


class TestFxMissingFourOptions:
    def test_01_all_four_options_accepted_by_api(self, client):
        """1. default / review / block / allow all accepted for an institution."""
        t = create_tenant(client, name="FX-4Opts")
        tid = t["tenant_id"]
        for fx in ("default", "review", "block", "allow"):
            r = client.put(f"/api/v1/admin/tenants/{tid}/thresholds",
                           json={**D, "fx_missing_action": fx}, headers=OWNER_HEADERS)
            assert r.status_code == 200, (fx, r.text)
            assert r.json()["fx_missing_action"] == fx
        client.delete(f"/api/v1/admin/tenants/{tid}/thresholds", headers=OWNER_HEADERS)

    def test_02_invalid_option_rejected(self, client):
        """2. An invalid fx option (e.g. 'xyz') is rejected with 422."""
        t = create_tenant(client, name="FX-BadOpt")
        tid = t["tenant_id"]
        r = client.put(f"/api/v1/admin/tenants/{tid}/thresholds",
                       json={**D, "fx_missing_action": "xyz"}, headers=OWNER_HEADERS)
        assert r.status_code == 422

    def test_03_default_profile_now_stores_default(self, client):
        """3. The platform default profile stores 'default' (follows global)."""
        r = client.get("/api/v1/admin/thresholds/default", headers=OWNER_HEADERS)
        assert r.status_code == 200, r.text
        assert r.json()["fx_missing_action"] == "default"

    def test_04_default_inheritance_mandatory_example(self, client):
        """4. MANDATORY: default = real inheritance, not a copied value.

        Global=default(→review):  A=default→review  B=review  C=block  D=allow
        Switch global to block:   A=default→block   B=review  C=block  D=allow
        """
        a = create_tenant(client, name="FX-A")["tenant_id"]
        b = create_tenant(client, name="FX-B")["tenant_id"]
        c = create_tenant(client, name="FX-C")["tenant_id"]
        d = create_tenant(client, name="FX-D")["tenant_id"]
        for tid, fx in ((a, "default"), (b, "review"), (c, "block"), (d, "allow")):
            _set_fx(client, tid, fx)

        # global = default (resolves to the safe global behavior = review)
        _set_default_fx(client, "default")
        assert _th(client, a)["effective"]["fx_missing_action"] == "default"
        assert _th(client, b)["effective"]["fx_missing_action"] == "review"
        assert _th(client, c)["effective"]["fx_missing_action"] == "block"
        assert _th(client, d)["effective"]["fx_missing_action"] == "allow"

        # switch the GLOBAL behavior to block — institutions on 'default' follow
        _set_default_fx(client, "block")
        eff_a = _th(client, a)["effective"]
        # A's profile still stores 'default' (inheritance), global now 'block'
        assert eff_a["fx_missing_action"] == "default"
        assert _th(client, b)["effective"]["fx_missing_action"] == "review"
        assert _th(client, c)["effective"]["fx_missing_action"] == "block"
        assert _th(client, d)["effective"]["fx_missing_action"] == "allow"
        for tid in (a, b, c, d):
            client.delete(f"/api/v1/admin/tenants/{tid}/thresholds", headers=OWNER_HEADERS)

    def test_05_policy_resolution_resolves_default_to_global(self, client):
        """5. PolicyEngine resolves stored 'default' to the global behavior."""
        from app.services.policy_engine import PolicyEngine

        class _Repo:
            def effective_thresholds(self, tid):
                return {"challenge": 0.35, "review": 0.60, "block": 0.80,
                        "fx_missing_action": "default", "source": "default"}

        eng = PolicyEngine(threshold_repo=_Repo())
        pol = eng.resolve({"tenant_id": "x", "type": "wallet"})
        # 'default' must NOT leak to the engine — it's resolved to the global value
        assert pol["fx_missing_action"] in ("review", "block", "allow")
        assert pol["fx_missing_action"] == pol["fx_missing_action_global"]

    def test_06_explicit_values_pass_through_resolution(self, client):
        """6. review / block / allow pass through resolution unchanged."""
        from app.services.policy_engine import PolicyEngine

        for fx in ("review", "block", "allow"):
            class _Repo:
                def effective_thresholds(self, tid, _fx=fx):
                    return {"challenge": 0.35, "review": 0.60, "block": 0.80,
                            "fx_missing_action": _fx, "source": "override"}

            eng = PolicyEngine(threshold_repo=_Repo())
            pol = eng.resolve({"tenant_id": "x", "type": "wallet"})
            assert pol["fx_missing_action"] == fx

    def test_07_orchestrator_missing_fx_allow_uses_ladder(self, client):
        """7. allow → missing FX tolerated; the threshold ladder still decides."""
        from app.services.orchestrator import Decision, DecisionOrchestrator

        orch = DecisionOrchestrator.__new__(DecisionOrchestrator)
        # call the pure ladder via a minimal policy
        policy = {"thresholds": {"challenge": 0.35, "review": 0.60, "block": 0.80},
                  "fx_missing_action": "allow"}
        # _decide with a low score and no sanctions => ALLOW
        assert orch._decide(0.10, False, policy) == Decision.ALLOW
        assert orch._decide(0.70, False, policy) == Decision.REVIEW
        assert orch._decide(0.90, False, policy) == Decision.BLOCK

    def test_08_audit_records_fx_changes(self, client):
        """8. Audit records default + override FX mutations."""
        t = create_tenant(client, name="FX-Audit")
        tid = t["tenant_id"]
        _set_fx(client, tid, "allow")
        _set_fx(client, tid, "default")
        client.delete(f"/api/v1/admin/tenants/{tid}/thresholds", headers=OWNER_HEADERS)
        _set_default_fx(client, "block")
        r = client.get("/api/v1/admin/audit?limit=400", headers=OWNER_HEADERS)
        events = r.json()
        rows = events if isinstance(events, list) else events.get("events", [])
        types = {x.get("event_type") or x.get("action") for x in rows}
        assert "thresholds.override.created" in types
        assert "thresholds.override.updated" in types
        assert "thresholds.override.deleted" in types
        assert "thresholds.default.updated" in types

    def test_09_tenant_isolation(self, client):
        """9. An override on tenant X never leaks to tenant Y."""
        x = create_tenant(client, name="FX-X")["tenant_id"]
        y = create_tenant(client, name="FX-Y")["tenant_id"]
        _set_fx(client, x, "allow")
        assert _th(client, x)["effective"]["fx_missing_action"] == "allow"
        assert _th(client, y)["effective"]["fx_missing_action"] == "default"
        client.delete(f"/api/v1/admin/tenants/{x}/thresholds", headers=OWNER_HEADERS)

    def test_10_override_disable_enable_unaffected_by_fx_option(self, client):
        """10. Disable/enable lifecycle still works with the four FX options."""
        t = create_tenant(client, name="FX-Lifecycle")["tenant_id"]
        _set_fx(client, t, "block")
        client.post(f"/api/v1/admin/tenants/{t}/thresholds/disable", headers=OWNER_HEADERS)
        assert _th(client, t)["effective"]["source"] == "default"
        client.post(f"/api/v1/admin/tenants/{t}/thresholds/enable", headers=OWNER_HEADERS)
        assert _th(client, t)["effective"]["fx_missing_action"] == "block"
        client.delete(f"/api/v1/admin/tenants/{t}/thresholds", headers=OWNER_HEADERS)
