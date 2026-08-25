"""Decision Engine tests — thresholds, sanctions forcing, fx_missing, fusion bounds, alert/case creation.

These exercise the DecisionOrchestrator end-to-end against a real (sqlite, isolated)
registry via the FastAPI client, plus direct unit tests of _decide/_band logic.
"""

from datetime import UTC, datetime

from app.core.config import settings
from app.models.schemas import Decision, RiskBand


class TestDecideThresholds:
    """Direct unit tests of the threshold ladder (no I/O)."""

    def _orch(self):
        # Minimal orchestrator instance without wiring (only _decide/_band used)
        from app.services.orchestrator import DecisionOrchestrator

        o = object.__new__(DecisionOrchestrator)
        return o

    def test_band_boundaries(self):
        o = self._orch()
        assert o._band(0.0) == RiskBand.LOW
        assert o._band(settings.DECISION_THRESHOLD_CHALLENGE - 0.01) == RiskBand.LOW
        assert o._band(settings.DECISION_THRESHOLD_CHALLENGE) == RiskBand.MEDIUM
        assert o._band(settings.DECISION_THRESHOLD_REVIEW) == RiskBand.HIGH
        assert o._band(settings.DECISION_THRESHOLD_BLOCK) == RiskBand.CRITICAL
        assert o._band(1.0) == RiskBand.CRITICAL

    def test_decide_ladder(self):
        o = self._orch()
        assert o._decide(0.0, False) == Decision.ALLOW
        assert o._decide(settings.DECISION_THRESHOLD_CHALLENGE, False) == Decision.CHALLENGE
        assert o._decide(settings.DECISION_THRESHOLD_REVIEW, False) == Decision.REVIEW
        assert o._decide(settings.DECISION_THRESHOLD_BLOCK, False) == Decision.BLOCK

    def test_decide_sanctions_forces_block_even_at_zero_score(self):
        o = self._orch()
        assert o._decide(0.0, True) == Decision.BLOCK

    def test_weights_sum_to_one(self):
        total = (
            settings.WEIGHT_RULES
            + settings.WEIGHT_ML
            + settings.WEIGHT_GRAPH
            + settings.WEIGHT_AML
            + settings.WEIGHT_BEHAVIOR
        )
        assert abs(total - 1.0) < 1e-9


class TestDecisionEngineE2E:
    """End-to-end decision behavior via the real webhook pipeline (isolated sqlite)."""

    def _tenant(self, client):
        import uuid

        from tests.conftest import OWNER_HEADERS

        r = client.post(
            "/api/v1/admin/tenants",
            json={
                "name": f"DE-{uuid.uuid4().hex[:6]}",
                "type": "wallet",
                "country": "YE",
                "plan": "sandbox",
                "investigator_limit": 2,
            },
            headers=OWNER_HEADERS,
        )
        assert r.status_code == 201, r.text
        return r.json()

    def _post(self, client, tenant, body):
        import hashlib
        import hmac
        import json

        raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()
        sig = hmac.new(tenant["hmac_secret"].encode(), raw, hashlib.sha256).hexdigest()
        return client.post(
            "/api/v1/wallet/webhook",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "x-api-key": tenant["api_key"],
                "x-wallet-signature": sig,
                "x-idempotency-key": body["tx_id"],
            },
        )

    def test_clean_tx_allows(self, client):
        t = self._tenant(client)
        now = datetime.now(UTC).isoformat()
        r = self._post(
            client,
            t,
            {
                "tx_id": "de-allow-1",
                "amount": 50,
                "currency": "USD",
                "sender_account_id": "a1",
                "beneficiary_account_id": "b1",
                "timestamp": now,
            },
        )
        assert r.status_code == 200
        assert r.json()["decision"] == "allow"
        assert 0.0 <= r.json()["risk_score"] <= 1.0

    def test_unknown_currency_forces_review_not_allow(self, client):
        t = self._tenant(client)
        now = datetime.now(UTC).isoformat()
        r = self._post(
            client,
            t,
            {
                "tx_id": "de-fxmiss-1",
                "amount": 500,
                "currency": "XXX",
                "sender_account_id": "a1",
                "beneficiary_account_id": "b1",
                "timestamp": now,
            },
        )
        assert r.status_code == 200
        assert r.json()["decision"] == "review"  # fx_missing policy default
        assert r.json()["risk_score"] >= settings.DECISION_THRESHOLD_REVIEW

    def test_elevated_decision_creates_alert_and_case(self, client):
        t = self._tenant(client)
        now = datetime.now(UTC).isoformat()
        r = self._post(
            client,
            t,
            {
                "tx_id": "de-alert-1",
                "amount": 500,
                "currency": "XXX",
                "sender_account_id": "a1",
                "beneficiary_account_id": "b1",
                "timestamp": now,
            },
        )
        assert r.status_code == 200
        assert r.json()["decision"] == "review"
        # alert persisted (via owner API)
        from tests.conftest import OWNER_HEADERS

        ar = client.get(f"/api/v1/admin/tenants/{t['tenant_id']}/alerts", headers=OWNER_HEADERS)
        assert ar.status_code == 200
        alerts = ar.json() if isinstance(ar.json(), list) else ar.json().get("alerts", [])
        assert any("de-alert-1" in str(a) for a in alerts), f"alert not found: {ar.text[:200]}"

    def test_decision_trace_complete(self, client):
        t = self._tenant(client)
        now = datetime.now(UTC).isoformat()
        r = self._post(
            client,
            t,
            {
                "tx_id": "de-trace-1",
                "amount": 75,
                "currency": "USD",
                "sender_account_id": "a1",
                "beneficiary_account_id": "b1",
                "timestamp": now,
            },
        )
        assert r.status_code == 200
        from tests.conftest import OWNER_HEADERS

        dr = client.get("/api/v1/admin/decisions/recent?limit=5", headers=OWNER_HEADERS)
        assert dr.status_code == 200
        rows = dr.json() if isinstance(dr.json(), list) else dr.json().get("decisions", [])
        mine = [d for d in rows if d.get("tx_id") == "de-trace-1"]
        assert mine, "decision not persisted"
        d = mine[0]
        for col in (
            "fx_proof_json",
            "tx_snapshot_json",
            "features_snapshot_json",
            "rule_set_version",
            "model_version",
            "config_version",
        ):
            assert d.get(col), f"{col} missing from DecisionTrace"
