"""Watchlist v2 — matching engine, name screening, RBAC, lifecycle,
provider sync, and point-in-time decision evidence."""
from __future__ import annotations

import asyncio
import json

from app.aml.matching import match_name, normalize_name
from app.models.schemas import Transaction
from tests.conftest import OWNER_HEADERS, create_tenant


# ── matching engine (pure unit) ──────────────────────────────────────────────
def _entry(value, **kw):
    e = {"id": 1, "value": value, "aliases_json": "[]", "identifiers_json": "{}",
         "source": "manual", "tenant_id": "t1"}
    e.update(kw)
    if "aliases" in kw:
        e["aliases_json"] = json.dumps(kw["aliases"])
    if "identifiers" in kw:
        e["identifiers_json"] = json.dumps(kw["identifiers"])
    return e


def test_normalize_strips_diacritics_and_case():
    assert normalize_name("  Mohamed   Alí!! ") == "MOHAMED ALI"


def test_exact_and_alias_match():
    entries = [_entry("MOHAMED ALI HASSAN", aliases=["M. ALI HASSAN"])]
    assert match_name("mohamed ali hassan", entries)[0]["match_type"] == "exact"
    assert match_name("M. Ali Hassan", entries)[0]["match_type"] == "alias"


def test_fuzzy_partial_name_match():
    entries = [_entry("MOHAMED ALI HASSAN")]
    m = match_name("Mohamed Ali", entries, fuzzy_threshold=0.85)
    assert m and m[0]["match_type"] == "fuzzy" and m[0]["score"] >= 0.85


def test_no_false_positive_on_unrelated_name():
    entries = [_entry("MOHAMED ALI HASSAN", country="YE")]
    assert match_name("John Smith", entries, context={"country": "US"}) == []


def test_identifier_match_boosts_fuzzy():
    entries = [_entry("MOHAMED A HASSAN", identifiers={"passport": "P123"})]
    m = match_name("Mohamed Ali Hassan", entries,
                   context={"identifiers": {"passport": "P123"}}, fuzzy_threshold=0.80)
    assert m and "passport" in (m[0]["secondary"].get("identifiers") or [])


# ── API: RBAC + lifecycle (integration via TestClient) ───────────────────────
def _tx(tenant_id, **kw):
    base = dict(tx_id="tx_wl_1", tenant_id=tenant_id, amount=100.0, currency="USD",
                sender_account_id="s1", beneficiary_account_id="b1",
                beneficiary_country="YE")
    base.update(kw)
    return Transaction(**base)


def test_owner_adds_and_disables_entry(client):
    t = create_tenant(client, name="WL Owner Tenant")
    tid = t["tenant_id"]
    r = client.post(f"/api/v1/admin/tenants/{tid}/watchlist", headers=OWNER_HEADERS,
                    json={"list_type": "custom", "value": "Blocked Corp", "entity_kind": "organization"})
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["status"] == "active" and row["source"] == "manual"
    r2 = client.post(f"/api/v1/admin/watchlist/{row['id']}/status?tenant_id={tid}",
                     headers=OWNER_HEADERS, json={"status": "disabled"})
    assert r2.status_code == 200 and r2.json()["status"] == "disabled"
    repo = client.app.state.registry.watchlist_repo
    assert repo.list_active("custom", tid) == []


def test_owner_list_and_audit(client):
    t = create_tenant(client, name="WL Audit Tenant")
    tid = t["tenant_id"]
    client.post(f"/api/v1/admin/tenants/{tid}/watchlist", headers=OWNER_HEADERS,
                json={"list_type": "pep", "value": "Important Person", "entity_kind": "person",
                      "country": "YE"})
    r = client.get(f"/api/v1/admin/watchlist?tenant_id={tid}", headers=OWNER_HEADERS)
    assert r.status_code == 200 and r.json()["total"] >= 1
    audit = client.app.state.registry.db.query(
        "SELECT * FROM audit_log WHERE tenant_id=? AND event_type='watchlist.entry_added'", (tid,))
    assert audit, "audit event for watchlist entry creation must exist"


def test_invalid_list_type_rejected(client):
    t = create_tenant(client, name="WL BadType")
    r = client.post(f"/api/v1/admin/tenants/{t['tenant_id']}/watchlist", headers=OWNER_HEADERS,
                    json={"list_type": "nonsense", "value": "X"})
    assert r.status_code == 422


# ── name screening in the AML engine ─────────────────────────────────────────
def test_aml_name_sanctions_hit_with_evidence(client):
    reg = client.app.state.registry
    t = create_tenant(client, name="WL Screening Tenant")
    tid = t["tenant_id"]
    client.post(f"/api/v1/admin/tenants/{tid}/watchlist", headers=OWNER_HEADERS,
                json={"list_type": "sanctions", "value": "Evil Trader Ltd",
                      "entity_kind": "organization"})
    tx = _tx(tid, beneficiary_name="Evil Trader Ltd", beneficiary_country="YE")
    sig = asyncio.run(reg.aml_service.screen(tx, {"velocity": {}}))
    assert sig.sanctions_hit is True
    assert sig.watchlist_evidence, "evidence must be attached"
    ev = sig.watchlist_evidence[0]
    assert ev["list_type"] == "sanctions" and ev["value"] == "EVIL TRADER LTD"
    assert ev["entry_id"] and ev["source"] == "manual"


def test_aml_pep_screening_now_works(client):
    reg = client.app.state.registry
    t = create_tenant(client, name="WL PEP Tenant")
    tid = t["tenant_id"]
    client.post(f"/api/v1/admin/tenants/{tid}/watchlist", headers=OWNER_HEADERS,
                json={"list_type": "pep", "value": "Senior Official", "entity_kind": "person"})
    tx = _tx(tid, sender_name="Senior Official")
    sig = asyncio.run(reg.aml_service.screen(tx, {"velocity": {}}))
    assert sig.pep_hit is True


def test_aml_disabled_entry_not_matched(client):
    reg = client.app.state.registry
    t = create_tenant(client, name="WL Disabled Tenant")
    tid = t["tenant_id"]
    r = client.post(f"/api/v1/admin/tenants/{tid}/watchlist", headers=OWNER_HEADERS,
                    json={"list_type": "sanctions", "value": "Shadow Org"})
    eid = r.json()["id"]
    client.post(f"/api/v1/admin/watchlist/{eid}/status?tenant_id={tid}",
                headers=OWNER_HEADERS, json={"status": "disabled"})
    tx = _tx(tid, beneficiary_name="Shadow Org")
    sig = asyncio.run(reg.aml_service.screen(tx, {"velocity": {}}))
    assert sig.sanctions_hit is False


def test_country_screening_still_works(client):
    reg = client.app.state.registry
    tx = _tx("t_demo_country", beneficiary_country="SY")
    sig = asyncio.run(reg.aml_service.screen(tx, {"velocity": {}}))
    assert sig.sanctions_hit is True  # platform default list


# ── provider sync (stubbed provider) ─────────────────────────────────────────
def test_provider_sync_adds_then_soft_removes(client, monkeypatch):
    from app.services import watchlist_providers as wp

    class Stub(wp.WatchlistProvider):
        name = "stub"
        source = "provider:stub"
        rows = []

        async def fetch(self, cfg):
            return list(self.rows)

    stub = Stub()
    monkeypatch.setitem(wp.PROVIDERS, "stub", stub)
    t = create_tenant(client, name="WL Sync Tenant")
    tid = t["tenant_id"]

    stub.rows = [{"value": "Alpha One"}, {"value": "Beta Two"}]
    r = client.post(f"/api/v1/admin/tenants/{tid}/watchlist/sync", headers=OWNER_HEADERS,
                    json={"provider": "stub", "list_type": "custom"})
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 2

    stub.rows = [{"value": "Alpha One"}]
    r2 = client.post(f"/api/v1/admin/tenants/{tid}/watchlist/sync", headers=OWNER_HEADERS,
                     json={"provider": "stub", "list_type": "custom"})
    assert r2.json()["removed"] == 1
    repo = client.app.state.registry.watchlist_repo
    active = repo.list_active("custom", tid)
    assert [e["value"] for e in active] == ["ALPHA ONE"]
    log = client.get(f"/api/v1/admin/tenants/{tid}/watchlist/sync-log", headers=OWNER_HEADERS)
    assert log.status_code == 200 and len(log.json()["entries"]) == 2
    assert all(e["status"] == "ok" for e in log.json()["entries"])


def test_provider_sync_failure_logged_and_502(client, monkeypatch):
    from app.services import watchlist_providers as wp

    class BadStub(wp.WatchlistProvider):
        name = "badstub"
        source = "provider:bad"

        async def fetch(self, cfg):
            raise wp.ProviderError("boom")

    monkeypatch.setitem(wp.PROVIDERS, "badstub", BadStub())
    t = create_tenant(client, name="WL SyncFail Tenant")
    r = client.post(f"/api/v1/admin/tenants/{t['tenant_id']}/watchlist/sync",
                    headers=OWNER_HEADERS, json={"provider": "badstub", "list_type": "custom"})
    assert r.status_code == 502
    log = client.get(f"/api/v1/admin/tenants/{t['tenant_id']}/watchlist/sync-log",
                     headers=OWNER_HEADERS).json()["entries"]
    assert log and log[0]["status"] == "failed" and "boom" in (log[0]["error"] or "")


# ── match-result taxonomy (no/potential/confirmed) ──────────────────────────
def test_evidence_match_result_confirmed_on_exact(client):
    reg = client.app.state.registry
    t = create_tenant(client, name="WL Taxonomy Exact")
    tid = t["tenant_id"]
    client.post(f"/api/v1/admin/tenants/{tid}/watchlist", headers=OWNER_HEADERS,
                json={"list_type": "sanctions", "value": "Blocked Corp", "entity_kind": "organization"})
    tx = _tx(tid, beneficiary_name="Blocked Corp")
    sig = asyncio.run(reg.aml_service.screen(tx, {"velocity": {}}))
    ev = [e for e in sig.watchlist_evidence if e["list_type"] == "sanctions"]
    assert ev and ev[0]["match_result"] == "confirmed"


def test_evidence_match_result_potential_on_bare_fuzzy(client):
    reg = client.app.state.registry
    t = create_tenant(client, name="WL Taxonomy Fuzzy")
    tid = t["tenant_id"]
    client.post(f"/api/v1/admin/tenants/{tid}/watchlist", headers=OWNER_HEADERS,
                json={"list_type": "pep", "value": "Mohamed Ali Hassan", "entity_kind": "person"})
    # partial fuzzy without corroborating attributes → potential, never confirmed
    tx = _tx(tid, sender_name="Mohamed Ali")
    sig = asyncio.run(reg.aml_service.screen(tx, {"velocity": {}}))
    ev = [e for e in sig.watchlist_evidence if e["list_type"] == "pep"]
    assert ev, "fuzzy PEP candidate should be recorded"
    assert ev[0]["match_result"] == "potential"
    assert ev[0]["match_type"] == "fuzzy"


def test_evidence_country_match_is_confirmed(client):
    reg = client.app.state.registry
    t = create_tenant(client, name="WL Taxonomy Country")
    tid = t["tenant_id"]
    tx = _tx(tid, beneficiary_country="IR")
    sig = asyncio.run(reg.aml_service.screen(tx, {"velocity": {}}))
    ev = [e for e in sig.watchlist_evidence if e.get("match_type") == "country_exact"]
    assert ev and all(e["match_result"] == "confirmed" for e in ev)


def test_evidence_persists_verbatim_in_decision_aml_json(client):
    """Historical integrity: evidence recorded at decision time survives in
    decisions.aml_json even after the entry is disabled afterwards."""
    import hashlib
    import hmac as _hmac
    import json as _json
    t = create_tenant(client, name="WL Persist Tenant")
    tid = t["tenant_id"]
    client.post(f"/api/v1/admin/tenants/{tid}/watchlist", headers=OWNER_HEADERS,
                json={"list_type": "sanctions", "value": "Persist Trader", "entity_kind": "organization"})
    body = {"tx_id": "WL_PERSIST_TX_1", "amount": 500.0, "currency": "USD",
            "sender_account_id": "a1", "beneficiary_account_id": "b1",
            "context": {"beneficiary": {"name": "Persist Trader", "country": "YE"}}}
    raw = _json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()
    sig = _hmac.new(t["hmac_secret"].encode(), raw, hashlib.sha256).hexdigest()
    r = client.post("/api/v1/wallet/webhook", content=raw, headers={
        "Content-Type": "application/json", "x-api-key": t["api_key"],
        "x-wallet-signature": sig, "x-idempotency-key": "WL_PERSIST_TX_1"})
    assert r.status_code == 200, r.text
    assert r.json()["decision"] == "block"
    # disable the entry AFTER the decision
    entries = client.get(f"/api/v1/admin/watchlist?tenant_id={tid}", headers=OWNER_HEADERS).json()["entries"]
    eid = [e for e in entries if e["value"] == "PERSIST TRADER"][0]["id"]
    client.post(f"/api/v1/admin/watchlist/{eid}/status?tenant_id={tid}", headers=OWNER_HEADERS,
                json={"status": "disabled"})
    # decision evidence must still contain the original match, verbatim
    dec = client.get(f"/api/v1/admin/tenants/{tid}/decisions", headers=OWNER_HEADERS).json()
    row = [d for d in dec if d["tx_id"] == "WL_PERSIST_TX_1"][0]
    aml = _json.loads(row["aml_json"]) if isinstance(row.get("aml_json"), str) else (row.get("aml_json") or {})
    ev = (aml.get("watchlist_evidence") or [])
    assert ev, "aml_json must keep watchlist evidence verbatim"
    assert ev[0]["value"] == "PERSIST TRADER" and ev[0]["match_result"] == "confirmed"
    assert ev[0]["list_snapshot_at"], "point-in-time snapshot timestamp required"
