"""Regression tests for AuditRepository.verify_chain (TASK 4).

Production bug reproduced: historical rows written by the per-tenant writer era
produced non-linear links (row 756) and a chain restart (row 758), which the old
verifier falsely reported as tampering.

Guarantees locked in:
  - tampering with a row's content -> entry_hash_mismatch (hard fail)
  - orphan prev_hash (references a hash that never existed) -> hard fail
  - non-linear historical links -> ok with warnings (NOT a failure)
  - chain restart (GENESIS mid-history) -> ok with warning
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))

from app.repositories.audit_repo import AuditRepository, _entry_hash, utcnow


def _mk_db(tmp_path, monkeypatch):
    """Isolated PostgreSQL test Database (PostgreSQL-only — AEGIS decision)."""
    from tests.conftest import make_test_db

    db = make_test_db(monkeypatch)
    db.migrate()  # constructor does NOT auto-run migrations — audit_log must exist
    return db


def _log(repo, tenant, event, meta=None):
    repo.log(tenant, "tester", event, "tx", "tx_1", None, meta or {})


def test_verify_chain_ok_on_clean_history(tmp_path, monkeypatch):
    repo = AuditRepository(_mk_db(tmp_path, monkeypatch))
    _log(repo, "tn_a", "e1")
    _log(repo, "tn_a", "e2")
    _log(repo, "tn_b", "e3")
    res = repo.verify_chain()
    assert res["ok"] is True
    assert res["checked"] == 3
    assert res["warning_count"] == 0


def test_verify_chain_detects_tampering(tmp_path, monkeypatch):
    db = _mk_db(tmp_path, monkeypatch)
    repo = AuditRepository(db)
    _log(repo, "tn_a", "e1")
    _log(repo, "tn_a", "e2")
    db.execute("UPDATE audit_log SET metadata_json=? WHERE id=1", ('{"forged": true}',))
    res = repo.verify_chain()
    assert res["ok"] is False
    assert res["reason"] == "entry_hash_mismatch"
    assert res["row_id"] == 1


def test_verify_chain_detects_orphan_prev_hash(tmp_path, monkeypatch):
    """Orphan = prev_hash references a hash that never existed. The row's own
    entry_hash is internally consistent (passes content check), so the linkage
    check must be the one that catches it — a fabricated/deleted-history row."""
    db = _mk_db(tmp_path, monkeypatch)
    repo = AuditRepository(db)
    _log(repo, "tn_a", "e1")
    ghost_prev = "deadbeef" * 8
    ts = utcnow()
    meta = json.dumps({}, sort_keys=True)
    entry = _entry_hash(ghost_prev, ts, "tn_a", "x", "e2", "tx", "tx_1", None, meta)
    db.execute(
        "INSERT INTO audit_log (ts,tenant_id,actor,event_type,resource,resource_id,"
        "request_id,metadata_json,prev_hash,entry_hash) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (ts, "tn_a", "x", "e2", "tx", "tx_1", None, meta, ghost_prev, entry),
    )
    res = repo.verify_chain()
    assert res["ok"] is False
    assert res["reason"] == "orphan_prev_hash"


def test_verify_chain_tolerates_historical_non_linear_link(tmp_path, monkeypatch):
    db = _mk_db(tmp_path, monkeypatch)
    repo = AuditRepository(db)
    _log(repo, "tn_a", "e1")
    _log(repo, "tn_a", "e2")
    rows = db.query("SELECT entry_hash FROM audit_log ORDER BY id")
    first_hash = rows[0]["entry_hash"]
    ts = utcnow()
    meta = json.dumps({}, sort_keys=True)
    entry = _entry_hash(first_hash, ts, "tn_a", "tester", "e3", "tx", "tx_1", None, meta)
    db.execute(
        "INSERT INTO audit_log (ts,tenant_id,actor,event_type,resource,resource_id,"
        "request_id,metadata_json,prev_hash,entry_hash) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (ts, "tn_a", "tester", "e3", "tx", "tx_1", None, meta, first_hash, entry),
    )
    res = repo.verify_chain()
    assert res["ok"] is True
    assert res["warning_count"] == 1
    assert res["warnings"][0]["type"] == "non_linear_link"


def test_verify_chain_tolerates_chain_restart(tmp_path, monkeypatch):
    db = _mk_db(tmp_path, monkeypatch)
    repo = AuditRepository(db)
    _log(repo, "tn_a", "e1")
    ts = utcnow()
    meta = json.dumps({}, sort_keys=True)
    entry = _entry_hash("GENESIS", ts, "tn_b", "tester", "e2", "tx", "tx_1", None, meta)
    db.execute(
        "INSERT INTO audit_log (ts,tenant_id,actor,event_type,resource,resource_id,"
        "request_id,metadata_json,prev_hash,entry_hash) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (ts, "tn_b", "tester", "e2", "tx", "tx_1", None, meta, "GENESIS", entry),
    )
    res = repo.verify_chain()
    assert res["ok"] is True
    assert any(w["type"] == "chain_restart" for w in res["warnings"])
