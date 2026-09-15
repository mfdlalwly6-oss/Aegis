"""Regression tests for Arena issues — self-contained unit tests (no DB, no server).

Covers:
  A2 — EventBus tenant scoping (tenant subscriber never sees other tenants).
  A3 — GraphEngine tenant isolation (devices/IPs/fraud-marks/insights/edges).
  A8 — Settings refuses default secrets outside development.

A1 (unauth /decisions/recent), A4 (four-eyes side door), A5 (suspended
tenant webhook 403), A6 (idempotency namespacing), A7 (ContextVar tenant
pinning) require the FastAPI app + PostgreSQL and are verified by the E2E
suite on the server (see DEPLOY_ARENA.md).
"""

import asyncio
import importlib
import os
import sys
from types import ModuleType, SimpleNamespace

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
for _cand in (
    os.path.join(_HERE, "..", "backend"),
    os.path.join(_HERE, "..", "..", "backend"),
    os.path.join(_HERE, ".."),
):
    _cand = os.path.abspath(_cand)
    if os.path.isdir(os.path.join(_cand, "app")):
        if _cand not in sys.path:
            sys.path.insert(0, _cand)
        break

# This sandbox copy of the repo contains only the files touched by the Arena
# fixes — app/models/schemas.py lives on the server. If the real module is
# absent, inject a minimal stand-in (GraphSignal/Transaction) so the GraphEngine
# unit tests can run here. On the server the REAL schemas module is imported.
try:
    import app.models.schemas  # noqa: F401
except ModuleNotFoundError:
    _pkg = ModuleType("app.models")
    _mod = ModuleType("app.models.schemas")
    from pydantic import BaseModel

    class _GraphSignal(BaseModel):
        score: float = 0.0
        reason: str | None = None
        shared_device_count: int = 0
        shared_ip_count: int = 0
        linked_accounts: int = 0
        hops_to_known_fraud: int | None = None
        ring_size: int | None = None
        pagerank_score: float | None = None

    class _Transaction(BaseModel):
        tenant_id: str | None = None

    _mod.GraphSignal = _GraphSignal
    _mod.Transaction = _Transaction
    _pkg.schemas = _mod
    sys.modules.setdefault("app.models", _pkg)
    sys.modules["app.models.schemas"] = _mod


def _tx(sender, tenant=None, device=None, ip=None, tx_id=None, benef="B0"):
    """Duck-typed Transaction stub — score()/add_transaction() only touch
    tx_id, sender_account_id, beneficiary_account_id, tenant_id, device."""
    return SimpleNamespace(
        tx_id=tx_id or f"tx-{sender}-{abs(hash((sender, tenant, tx_id)))}",
        sender_account_id=sender,
        beneficiary_account_id=benef,
        tenant_id=tenant,
        device=SimpleNamespace(device_id=device, ip=ip) if (device or ip) else None,
    )


# ─────────────────────────── A2: EventBus ───────────────────────────


class TestEventBusTenantScoping:
    def _bus_with(self):
        from app.streaming import EventBus

        bus = EventBus()
        qa = bus.subscribe("tn_A")
        qb = bus.subscribe("tn_B")
        qp = bus.subscribe(None)  # platform scope sees everything
        return bus, qa, qb, qp

    def test_tenant_never_sees_other_tenant_events(self):
        bus, qa, qb, _qp = self._bus_with()

        async def run():
            await bus.publish("decision.created", {"tenant_id": "tn_A", "v": 1})
            await bus.publish("decision.created", {"tenant_id": "tn_B", "v": 2})
            await bus.publish("decision.created", {"tenant_id": "tn_A", "v": 3})

        asyncio.run(run())
        # tenant A queue: only A events (v1, v3)
        a_vals = [qa.get_nowait()["payload"]["v"], qa.get_nowait()["payload"]["v"]]
        assert a_vals == [1, 3]
        with pytest.raises(asyncio.QueueEmpty):
            qa.get_nowait()
        # tenant B queue: only B events (v2)
        assert qb.get_nowait()["payload"]["v"] == 2
        with pytest.raises(asyncio.QueueEmpty):
            qb.get_nowait()

    def test_platform_scope_sees_all(self):
        bus, _qa, _qb, qp = self._bus_with()

        async def run():
            await bus.publish("decision.created", {"tenant_id": "tn_A", "v": 1})
            await bus.publish("decision.created", {"tenant_id": "tn_B", "v": 2})

        asyncio.run(run())
        vals = [qp.get_nowait()["payload"]["v"], qp.get_nowait()["payload"]["v"]]
        assert vals == [1, 2]

    def test_unsubscribed_queue_stops_receiving(self):
        from app.streaming import EventBus

        bus = EventBus()
        q = bus.subscribe("tn_A")
        bus.unsubscribe(q)

        async def run():
            await bus.publish("decision.created", {"tenant_id": "tn_A"})

        asyncio.run(run())
        assert q.empty()


# ─────────────────────────── A3: GraphEngine ───────────────────────────


class TestGraphTenantIsolation:
    def test_shared_device_not_counted_across_tenants(self):
        from app.graph.engine import GraphEngine

        g = GraphEngine()
        # Tenant B: two senders share device D-shared.
        g.add_transaction(_tx("S_b1", tenant="tn_B", device="D-shared", tx_id="txB1"))
        g.add_transaction(_tx("S_b2", tenant="tn_B", device="D-shared", tx_id="txB2"))
        # Tenant A: same raw device id — must NOT see B's usage count.
        sig_a = g.score(_tx("S_a1", tenant="tn_A", device="D-shared", tx_id="txA1"))
        assert sig_a.shared_device_count == 0
        assert sig_a.score <= 0.0001
        # Tenant B DOES see the shared device (2nd user of D-shared).
        sig_b = g.score(_tx("S_b1", tenant="tn_B", device="D-shared", tx_id="txB3"))
        assert sig_b.shared_device_count == 1

    def test_fraud_mark_is_tenant_scoped(self):
        from app.graph.engine import GraphEngine

        g = GraphEngine()
        # Same account id exists in BOTH tenants.
        g.add_transaction(_tx("ACC", tenant="tn_A", tx_id="txA1", benef="X_A"))
        g.add_transaction(_tx("ACC", tenant="tn_B", tx_id="txB1", benef="X_B"))
        g.mark_fraud("X_A", tenant_id="tn_A")  # fraud marked in A only

        # A: ACC -> (tx node txA1) -> X_A = 2 hops (engine counts NODES,
        # not edges: account→transaction→beneficiary) within the boost window.
        sig_a = g.score(_tx("ACC", tenant="tn_A", tx_id="txA2", benef="Y_A"))
        assert sig_a.hops_to_known_fraud == 2
        assert sig_a.score >= 0.30

        # B: same ids, but A's fraud mark is invisible -> no hops, no boost.
        sig_b = g.score(_tx("ACC", tenant="tn_B", tx_id="txB2", benef="Y_B"))
        assert sig_b.hops_to_known_fraud is None
        assert sig_b.score < 0.30

    def test_insights_filtered_by_tenant(self):
        from app.graph.engine import GraphEngine

        g = GraphEngine()
        g.add_transaction(_tx("S_a1", tenant="tn_A", device="D-a", tx_id="txA1"))
        g.add_transaction(_tx("S_a2", tenant="tn_A", device="D-a", tx_id="txA2"))
        g.add_transaction(_tx("S_b1", tenant="tn_B", device="D-b", tx_id="txB1"))
        g.add_transaction(_tx("S_b2", tenant="tn_B", device="D-b", tx_id="txB2"))
        g.mark_fraud("S_a1", tenant_id="tn_A")

        ins_a = g.insights(tenant_id="tn_A")
        ins_b = g.insights(tenant_id="tn_B")
        assert [d["device_id"] for d in ins_a["shared_devices"]] == ["D-a"]
        assert [d["device_id"] for d in ins_b["shared_devices"]] == ["D-b"]
        assert ins_a["known_fraud_accounts"] != []
        assert ins_b["known_fraud_accounts"] == []

    def test_account_context_scoped(self):
        from app.graph.engine import GraphEngine

        g = GraphEngine()
        g.add_transaction(
            _tx("S_a1", tenant="tn_A", device="D-a", ip="1.1.1.1", tx_id="txA1")
        )
        ctx_b = g.account_context("S_a1", tenant_id="tn_B")
        assert ctx_b["in_graph"] is False
        ctx_a = g.account_context("S_a1", tenant_id="tn_A")
        assert ctx_a["in_graph"] is True
        assert ctx_a["devices"] == ["D-a"]

    def test_edges_never_cross_tenants(self):
        from app.graph.engine import GraphEngine

        g = GraphEngine()
        g.add_transaction(_tx("ACC", tenant="tn_A", tx_id="txA1", benef="Z_A"))
        g.add_transaction(_tx("ACC", tenant="tn_B", tx_id="txB1", benef="Z_B"))
        # Any detected community must be single-tenant: account ACC exists
        # twice, namespaced — no ring may mix t:tn_A with t:tn_B members.
        for ring in g.find_rings(min_size=2):
            tenants = {m.split("|")[0] for m in ring["members"] if m.startswith("t:")}
            assert len(tenants) <= 1


# ─────────────────────────── A8: secret guard ───────────────────────────


class TestConfigSecretGuard:
    def test_production_rejects_default_secret_key(self, monkeypatch):
        from app.core import config as cfg

        importlib.reload(cfg)
        monkeypatch.delenv("AEGIS_SECRET_KEY", raising=False)
        monkeypatch.delenv("AEGIS_OWNER_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            cfg.Settings(ENV="production", _env_file=None)

    def test_production_rejects_default_owner_token(self, monkeypatch):
        from app.core import config as cfg

        importlib.reload(cfg)
        monkeypatch.setenv("AEGIS_SECRET_KEY", "R" * 40)
        monkeypatch.delenv("AEGIS_OWNER_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="OWNER_TOKEN"):
            cfg.Settings(ENV="production", _env_file=None)

    def test_production_accepts_real_secrets(self, monkeypatch):
        from app.core import config as cfg

        importlib.reload(cfg)
        monkeypatch.setenv("AEGIS_SECRET_KEY", "R" * 40)
        monkeypatch.setenv("AEGIS_OWNER_TOKEN", "real-owner-token-from-vault")
        s = cfg.Settings(ENV="production", _env_file=None)
        assert s.OWNER_TOKEN == "real-owner-token-from-vault"

    def test_dev_defaults_still_boot(self, monkeypatch):
        from app.core import config as cfg

        importlib.reload(cfg)
        monkeypatch.delenv("AEGIS_SECRET_KEY", raising=False)
        monkeypatch.delenv("AEGIS_OWNER_TOKEN", raising=False)
        s = cfg.Settings(ENV="development", _env_file=None)
        assert s.ENV == "development"
