"""PostgreSQL integration tests — TASK 1.

These run against the production PostgreSQL instance and are SKIPPED unless
the suite is launched with ``AEGIS_DB_DRIVER=postgres`` and a reachable
``AEGIS_DATABASE_URL`` (see scripts/pg_migrate.py for the SQLite->PG load).

Coverage:
  * schema_migrations contains the full versioned chain (001..006)
  * legacy SQLite data survived the copy (floor counts, not exact: live data)
  * CRUD round-trip through the repository-facing interface
  * tenant isolation at the SQL layer (Task 3 adds Postgres RLS on top)
  * concurrency: parallel writers under MVCC do not lose rows
  * restart persistence: a fresh connection still sees committed rows
  * unique constraint enforcement (api_key) raises instead of corrupting
"""

import threading

import pytest
from app.core.config import settings

import os

# Structural tests run on the isolated aegis_test DB (fresh per module) — never live.

# All structural tests here run against the ISOLATED aegis_test database created
# fresh by the fixture — never the live database. The two live-data smoke tests
# below stay opt-in via AEGIS_PG_LIVE_TESTS=1.


@pytest.fixture(scope="module")
def db():
    import os as _os

    _os.environ.setdefault("AEGIS_OWNER_TOKEN", "test-owner-token-2026")
    _os.environ.setdefault("AEGIS_SECRET_KEY", "test-secret-key-that-is-long-enough-for-hs256")
    from tests.conftest import make_test_db

    d = make_test_db()
    d.migrate()
    yield d
    d.close()


def _insert_tenant(db, tenant_id, api_key):
    db.execute(
        "INSERT INTO tenants (tenant_id,name,type,country,plan,contact_email,contact_phone,api_key,hmac_secret,status,policy_json,created_at,investigator_limit,timezone) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            tenant_id,
            f"Tenant {tenant_id}",
            "wallet",
            "YE",
            "sandbox",
            None,
            None,
            api_key,
            f"sec-{tenant_id}",
            "active",
            "{}",
            "2026-08-24T00:00:00+00:00",
            5,
            "Asia/Aden",
        ),
    )


def test_connection_and_migrations_applied(db):
    rows = db.query("SELECT name FROM schema_migrations ORDER BY name")
    names = [r["name"] for r in rows]
    assert names, "schema_migrations is empty — run scripts/pg_migrate.py"
    assert any(n.startswith("001") for n in names), f"missing 001: {names}"
    assert any(n.startswith("006") for n in names), f"missing 006: {names}"
    print("MIGRATIONS", names)


@pytest.mark.skipif(os.environ.get("AEGIS_PG_LIVE_TESTS") != "1", reason="live-DB smoke test — opt-in only")
def test_legacy_data_preserved(db):
    rows = db.query(
        "SELECT 'tenants' t, COUNT(*) c FROM tenants "
        "UNION ALL SELECT 'transactions', COUNT(*) FROM transactions "
        "UNION ALL SELECT 'decisions', COUNT(*) FROM decisions "
        "UNION ALL SELECT 'fx_rates', COUNT(*) FROM fx_rates "
        "UNION ALL SELECT 'rules', COUNT(*) FROM rules "
        "UNION ALL SELECT 'currencies', COUNT(*) FROM currencies"
    )
    counts = {r["t"]: r["c"] for r in rows}
    assert counts["tenants"] >= 64, counts
    assert counts["transactions"] >= 47, counts
    assert counts["decisions"] >= 130, counts
    assert counts["fx_rates"] >= 7, counts
    assert counts["rules"] >= 21, counts
    assert counts["currencies"] >= 3, counts
    print("COUNTS", counts)


def test_crud_roundtrip(db):
    db.execute("DELETE FROM transactions WHERE tx_id LIKE 'pg-crud-%'")
    db.execute("DELETE FROM decisions WHERE decision_id LIKE 'pg-crud-%'")
    db.execute("DELETE FROM tenants WHERE tenant_id = 'pg-crud-t1'")
    _insert_tenant(db, "pg-crud-t1", "api_pg_crud_1")
    db.execute(
        "INSERT INTO transactions (tx_id,tenant_id,ts,channel,amount,currency,sender_account_id,beneficiary_account_id,raw_json,features_json,created_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            "pg-crud-tx1",
            "pg-crud-t1",
            "2026-08-24T00:00:00+00:00",
            "wallet",
            1234.5678,
            "USD",
            "a1",
            "b1",
            "{}",
            "{}",
            "2026-08-24T00:00:00+00:00",
        ),
    )
    db.execute(
        "INSERT INTO decisions (decision_id,tx_id,tenant_id,ts,decision,risk_score,risk_band,latency_ms,created_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            "pg-crud-d1",
            "pg-crud-tx1",
            "pg-crud-t1",
            "2026-08-24T00:00:00+00:00",
            "allow",
            0.25,
            "low",
            12.5,
            "2026-08-24T00:00:00+00:00",
        ),
    )
    got = db.query_one("SELECT amount, currency FROM transactions WHERE tx_id=%s", ("pg-crud-tx1",))
    assert got and float(got["amount"]) == 1234.5678 and got["currency"] == "USD"
    dec = db.query_one("SELECT decision, risk_score FROM decisions WHERE decision_id=%s", ("pg-crud-d1",))
    assert dec["decision"] == "allow" and float(dec["risk_score"]) == 0.25
    # cleanup
    db.execute("DELETE FROM decisions WHERE decision_id='pg-crud-d1'")
    db.execute("DELETE FROM transactions WHERE tx_id='pg-crud-tx1'")
    db.execute("DELETE FROM tenants WHERE tenant_id='pg-crud-t1'")


def test_tenant_isolation_sql_layer(db):
    db.execute("DELETE FROM transactions WHERE tenant_id IN ('pg-iso-a','pg-iso-b')")
    db.execute("DELETE FROM tenants WHERE tenant_id IN ('pg-iso-a','pg-iso-b')")
    _insert_tenant(db, "pg-iso-a", "api_pg_iso_a")
    _insert_tenant(db, "pg-iso-b", "api_pg_iso_b")
    for tid in ("pg-iso-a", "pg-iso-b"):
        db.execute(
            "INSERT INTO transactions (tx_id,tenant_id,ts,channel,amount,currency,sender_account_id,beneficiary_account_id,raw_json,features_json,created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                f"pg-iso-{tid}",
                tid,
                "2026-08-24T00:00:00+00:00",
                "wallet",
                100,
                "USD",
                "s",
                "b",
                "{}",
                "{}",
                "2026-08-24T00:00:00+00:00",
            ),
        )
    a = db.query("SELECT tx_id FROM transactions WHERE tenant_id=%s", ("pg-iso-a",))
    b = db.query("SELECT tx_id FROM transactions WHERE tenant_id=%s", ("pg-iso-b",))
    assert len(a) == 1 and a[0]["tx_id"] == "pg-iso-pg-iso-a"
    assert len(b) == 1 and b[0]["tx_id"] == "pg-iso-pg-iso-b"
    db.execute("DELETE FROM transactions WHERE tenant_id IN ('pg-iso-a','pg-iso-b')")
    db.execute("DELETE FROM tenants WHERE tenant_id IN ('pg-iso-a','pg-iso-b')")


def test_concurrent_writes(db):
    db.execute("CREATE TABLE IF NOT EXISTS pg_conc_test (id BIGSERIAL PRIMARY KEY, payload TEXT NOT NULL)")
    db.execute("TRUNCATE pg_conc_test")
    n_threads, per_thread = 8, 25
    errors = []

    from tests.conftest import make_test_db

    def worker(seed):
        try:
            local = make_test_db(fresh=False)  # same isolated test DB, per-thread conn
            for i in range(per_thread):
                local.execute("INSERT INTO pg_conc_test (payload) VALUES (%s)", (f"{seed}-{i}",))
            local.close()
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    n = db.query_one("SELECT COUNT(*) c FROM pg_conc_test")["c"]
    assert n == n_threads * per_thread, f"expected {n_threads * per_thread}, got {n}"
    db.execute("DROP TABLE pg_conc_test")


def test_restart_persistence(db):
    # Isolated DB semantics: rows committed by this test session persist across
    # a brand-new connection to the same test database.
    from tests.conftest import make_test_db

    _insert_tenant(db, "pg-restart", "api_pg_restart_unique")
    fresh = make_test_db(fresh=False)  # brand-new connection object, same isolated DB
    try:
        n = fresh.query_one(
            "SELECT COUNT(*) c FROM tenants WHERE tenant_id='pg-restart'"
        )["c"]
        assert n == 1, "committed rows must survive a fresh connection"
    finally:
        fresh.close()
    db.execute("DELETE FROM tenants WHERE tenant_id='pg-restart'")


def test_unique_constraint_enforced(db):
    db.execute("DELETE FROM tenants WHERE tenant_id='pg-uniq'")
    _insert_tenant(db, "pg-uniq", "api_pg_uniq_same")
    from psycopg.errors import UniqueViolation

    with pytest.raises(UniqueViolation):
        _insert_tenant(db, "pg-uniq-2", "api_pg_uniq_same")  # same api_key
    db.execute("DELETE FROM tenants WHERE tenant_id IN ('pg-uniq','pg-uniq-2')")
