"""Component tests — rules, graph, AML, ML fallback."""

from datetime import UTC, datetime

from app.graph.engine import GraphEngine
from app.ml.ensemble import EnsembleScorer
from app.models.schemas import BehaviorSignals, DeviceContext, Transaction


def _tx(**kw):
    base = {
        "tx_id": "t1",
        "tenant_id": "t",
        "amount": 100.0,
        "currency": "USD",
        "sender_account_id": "a",
        "beneficiary_account_id": "b",
        "timestamp": datetime.now(UTC),
    }
    base.update(kw)
    return Transaction(**base)


def test_rule_engine_evaluates_velocity():
    from app.rules.engine import RuleEngine

    engine = RuleEngine(
        [
            {
                "id": "T1",
                "name": "test",
                "severity": "high",
                "score": 0.5,
                "when": {">": [{"var": "features.velocity.tx_per_min_card"}, 5]},
            }
        ]
    )
    hits = engine.evaluate(_tx(), {"velocity": {"tx_per_min_card": 9}})
    assert len(hits) == 1
    assert hits[0].rule_id == "T1"


def test_rule_engine_disabled_rule():
    from app.rules.engine import RuleEngine

    engine = RuleEngine(
        [
            {
                "id": "T2",
                "name": "off",
                "severity": "high",
                "score": 0.5,
                "enabled": False,
                "when": {">": [{"var": "features.velocity.tx_per_min_card"}, 0]},
            }
        ]
    )
    assert engine.evaluate(_tx(), {"velocity": {"tx_per_min_card": 99}}) == []


def test_graph_shared_device():
    g = GraphEngine()
    g.add_transaction(_tx(tx_id="x1", sender_account_id="acct_1", device=DeviceContext(device_id="dev_a")))
    g.add_transaction(_tx(tx_id="x2", sender_account_id="acct_2", device=DeviceContext(device_id="dev_a")))
    sig = g.score(_tx(tx_id="x3", sender_account_id="acct_3", device=DeviceContext(device_id="dev_a")))
    assert sig.shared_device_count >= 2
    assert sig.score > 0


def test_graph_no_data_returns_zero():
    g = GraphEngine()
    sig = g.score(_tx())
    assert sig.score == 0.0


def test_aml_sanctions_hit(client):
    import asyncio

    from app.aml.service import AMLService
    from app.repositories.watchlist_repo import WatchlistRepository

    wl = WatchlistRepository(client.app.state.registry.db)
    aml = AMLService(wl)
    tx = _tx(beneficiary_country="IR")
    sig = asyncio.get_event_loop().run_until_complete(
        aml.screen(tx, {"velocity": {}, "amount_flags": {}, "device": {}, "beneficiary": {}})
    )
    assert sig.sanctions_hit is True
    assert sig.score >= 0.5


def test_ml_fallback_is_labeled():
    scorer = EnsembleScorer(models_dir="/nonexistent")
    assert not scorer.ready
    score, reports = scorer.score([0.0] * 20)
    assert reports[0].model_name == "heuristic_fallback"
    assert "NOT_TRAINED_ML" in reports[0].reason_codes


def test_behavior_score_in_orchestrator():
    from app.services.orchestrator import DecisionOrchestrator

    o = DecisionOrchestrator(
        rules=None,
        ml=None,
        graph=None,
        aml_service=None,
        features=None,
        transactions=None,
        decisions=None,
        alerts=None,
        cases=None,
        audit=None,
        events=None,
        notifications=None,
    )
    low = _tx(behavior=BehaviorSignals(biometric_match_score=0.1, keystroke_entropy=0.5))
    high = _tx(behavior=BehaviorSignals(biometric_match_score=0.99))
    assert o._behavior_score(low) > o._behavior_score(high)


def test_audit_hash_chain_and_tamper_detection(tmp_path, monkeypatch):
    """Audit log must chain entries; tampering with a row must break verification."""
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))
    from app.repositories.audit_repo import AuditRepository
    from tests.conftest import make_test_db

    db = make_test_db(monkeypatch)
    db.migrate()
    repo = AuditRepository(db)
    repo.log("t1", "owner", "test.event", "tx", "tx1", "req1", {"k": "v"})
    repo.log("t1", "owner", "test.event2", "tx", "tx2", "req2", {"k": "v2"})
    ok = repo.verify_chain()
    assert ok["ok"] is True and ok["checked"] == 2
    # tamper: change historical metadata
    db.execute(
        "UPDATE audit_log SET metadata_json=? WHERE id=(SELECT MIN(id) FROM audit_log)",
        (json.dumps({"k": "tampered"}, sort_keys=True),),
    )
    bad = repo.verify_chain()
    assert bad["ok"] is False and bad["reason"] == "entry_hash_mismatch"
    db.close()


import json
