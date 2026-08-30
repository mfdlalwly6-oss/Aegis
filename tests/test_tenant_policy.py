"""TASK 10 — deterministic tenant policy resolution."""

from app.models.schemas import Decision
from app.services.orchestrator import DecisionOrchestrator


class _Tenants:
    def __init__(self, policies):
        self.policies = policies

    def get_policy(self, tenant_id):
        return self.policies.get(tenant_id, {})


def _orch(policies):
    return DecisionOrchestrator(
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
        tenants=_Tenants(policies),
    )


def test_tenant_thresholds_are_scoped_and_change_decision():
    o = _orch(
        {
            "a": {"thresholds": {"challenge": 0.2, "review": 0.3, "block": 0.8}},
            "b": {"thresholds": {"challenge": 0.2, "review": 0.7, "block": 0.9}},
        }
    )
    assert o._decide(0.5, False, o._resolve_policy("a")) == Decision.REVIEW
    assert o._decide(0.5, False, o._resolve_policy("b")) == Decision.CHALLENGE


def test_missing_or_malformed_policy_uses_safe_defaults():
    """Malformed values are clamped into the safe windows (never passed through),
    and the result always stays ordered — fail-closed by design."""
    o = _orch({"bad": {"thresholds": {"review": "nope", "block": -1}}})
    from app.services.policy_engine import THRESHOLD_BOUNDS

    missing = o._resolve_policy("missing")
    bad = o._resolve_policy("bad")
    for resolved in (missing, bad):
        th = resolved["thresholds"]
        for key, (lo, hi) in THRESHOLD_BOUNDS.items():
            assert lo <= th[key] <= hi
        assert th["challenge"] <= th["review"] <= th["block"]
    # A malformed block (-1) must never weaken protection below the default block.
    assert bad["thresholds"]["block"] >= THRESHOLD_BOUNDS["block"][0]


def test_hard_sanctions_block_and_invalid_threshold_order_is_ignored():
    o = _orch({"bad": {"thresholds": {"challenge": 0.9, "review": 0.2, "block": 0.1}}})
    policy = o._resolve_policy("bad")
    assert (
        policy["thresholds"]["challenge"] <= policy["thresholds"]["review"] <= policy["thresholds"]["block"]
    )
    assert o._decide(0.0, True, policy) == Decision.BLOCK
