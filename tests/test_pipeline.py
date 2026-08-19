"""End-to-end pipeline tests — webhook → decision → DB → alerts → isolation."""
from tests.conftest import create_tenant, merchant_token, sign


def _post_tx(client, tenant, tx_id, amount, extra=None):
    tx = {"tx_id": tx_id, "amount": amount,
          "sender_account_id": "acct_sender", "beneficiary_account_id": "acct_recv"}
    if extra:
        tx.update(extra)
    sig, body = sign(tenant["hmac_secret"], {"transaction": tx})
    return client.post("/api/v1/wallet/webhook",
                       headers={"Content-Type": "application/json",
                                "X-API-Key": tenant["api_key"],
                                "X-Wallet-Signature": sig},
                       content=body)


def test_full_pipeline_creates_decision_and_audit(client):
    tenant = create_tenant(client)
    r = _post_tx(client, tenant, "tx_pipe_1", 500)
    assert r.status_code == 200
    d = r.json()
    assert d["decision"] in ("allow", "challenge", "review", "block")

    tx = client.get("/api/v1/transactions/tx_pipe_1", headers=client.owner_headers)
    assert tx.status_code == 200
    assert tx.json()["decision"]["decision"] == d["decision"]

    audit = client.get("/api/v1/admin/audit?event_type=transaction.scored",
                       headers=client.owner_headers)
    assert audit.status_code == 200
    assert any(a["resource_id"] == "tx_pipe_1" for a in audit.json())


def test_high_risk_transaction_creates_alert_and_case(client):
    tenant = create_tenant(client)
    r = _post_tx(client, tenant, "tx_risk_1", 95000,
                 {"metadata": {"emulator": True, "seconds_since_password_change": 60}})
    assert r.status_code == 200
    d = r.json()
    assert d["decision"] in ("review", "block", "challenge")
    assert d.get("alert_id")

    alerts = client.get("/api/v1/alerts/", headers=client.owner_headers).json()
    assert any(a["alert_id"] == d["alert_id"] for a in alerts)


def test_sanctioned_country_blocks(client):
    tenant = create_tenant(client)
    r = _post_tx(client, tenant, "tx_sanct_1", 1000,
                 {"beneficiary_country": "IR"})
    assert r.status_code == 200
    assert r.json()["decision"] == "block"


def test_tenant_isolation(client):
    t1 = create_tenant(client, "Wallet A")
    t2 = create_tenant(client, "Wallet B")
    _post_tx(client, t1, "tx_iso_1", 200)

    tok1 = merchant_token(client, t1)
    tok2 = merchant_token(client, t2)
    d1 = client.get("/api/v1/admin/merchant/decisions",
                    headers={"Authorization": f"Bearer {tok1}"}).json()
    d2 = client.get("/api/v1/admin/merchant/decisions",
                    headers={"Authorization": f"Bearer {tok2}"}).json()
    assert any(d["tx_id"] == "tx_iso_1" for d in d1)
    assert all(d["tenant_id"] != t1["tenant_id"] for d in d2)

    s1 = client.get("/api/v1/admin/merchant/stats",
                    headers={"Authorization": f"Bearer {tok1}"}).json()
    s2 = client.get("/api/v1/admin/merchant/stats",
                    headers={"Authorization": f"Bearer {tok2}"}).json()
    assert s1["total_decisions"] >= 1
    assert s2["total_decisions"] == 0


def test_persistence_across_registry_reinit(client, tmp_path, monkeypatch):
    """Decisions survive a fresh registry init against the same DB file."""
    tenant = create_tenant(client)
    _post_tx(client, tenant, "tx_persist_1", 750)

    from app.main import app
    from fastapi.testclient import TestClient
    with TestClient(app) as c2:
        tx = c2.get("/api/v1/transactions/tx_persist_1", headers=client.owner_headers)
        assert tx.status_code == 200
        assert tx.json()["decision"]["risk_score"] >= 0
