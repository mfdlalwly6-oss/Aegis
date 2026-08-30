"""SQLite database layer — real persistent storage with forward-only migrations.
Thread-safe via check_same_thread=False + explicit transactions.
Swappable to PostgreSQL later: all access goes through app/repositories/.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC
from pathlib import Path

from app.core.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id      TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    type           TEXT NOT NULL DEFAULT 'wallet',
    country        TEXT NOT NULL DEFAULT 'YE',
    plan           TEXT NOT NULL DEFAULT 'sandbox',
    contact_email  TEXT,
    contact_phone  TEXT,
    api_key        TEXT NOT NULL UNIQUE,
    hmac_secret    TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'active',
    policy_json    TEXT NOT NULL DEFAULT '{}',
    created_at     TEXT NOT NULL,
    secret_rotated_at TEXT,
    deleted_at     TEXT,
    investigator_limit INTEGER NOT NULL DEFAULT 5,
    timezone       TEXT NOT NULL DEFAULT 'Asia/Aden',
    review_message TEXT
);

CREATE TABLE IF NOT EXISTS users (
    user_id        TEXT PRIMARY KEY,
    tenant_id      TEXT NOT NULL REFERENCES tenants(tenant_id),
    email          TEXT NOT NULL,
    name           TEXT NOT NULL,
    role           TEXT NOT NULL DEFAULT 'viewer',
    password_hash  TEXT,
    api_key        TEXT UNIQUE,
    status         TEXT NOT NULL DEFAULT 'active',
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    tx_id          TEXT PRIMARY KEY,
    tenant_id      TEXT NOT NULL REFERENCES tenants(tenant_id),
    ts             TEXT NOT NULL,
    channel        TEXT NOT NULL DEFAULT 'wallet',
    amount         REAL NOT NULL,
    currency       TEXT NOT NULL DEFAULT 'USD',
    sender_account_id    TEXT NOT NULL,
    sender_user_id       TEXT,
    beneficiary_account_id TEXT NOT NULL,
    beneficiary_user_id    TEXT,
    beneficiary_country    TEXT,
    merchant_id    TEXT,
    merchant_name  TEXT,
    device_id      TEXT,
    ip             TEXT,
    ip_country     TEXT,
    raw_json       TEXT NOT NULL,
    features_json  TEXT NOT NULL DEFAULT '{}',
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tx_tenant ON transactions(tenant_id, ts);
CREATE INDEX IF NOT EXISTS idx_tx_sender ON transactions(tenant_id, sender_account_id, ts);
CREATE INDEX IF NOT EXISTS idx_tx_device ON transactions(tenant_id, device_id);
CREATE INDEX IF NOT EXISTS idx_tx_ip ON transactions(tenant_id, ip);
CREATE INDEX IF NOT EXISTS idx_tx_benef ON transactions(tenant_id, beneficiary_account_id);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id    TEXT PRIMARY KEY,
    tx_id          TEXT NOT NULL REFERENCES transactions(tx_id),
    tenant_id      TEXT NOT NULL,
    ts             TEXT NOT NULL,
    decision       TEXT NOT NULL,
    risk_score     REAL NOT NULL,
    risk_band      TEXT NOT NULL,
    latency_ms     REAL NOT NULL,
    rule_score     REAL NOT NULL DEFAULT 0,
    ml_score       REAL NOT NULL DEFAULT 0,
    graph_score    REAL NOT NULL DEFAULT 0,
    aml_score      REAL NOT NULL DEFAULT 0,
    behavior_score REAL NOT NULL DEFAULT 0,
    rules_json     TEXT NOT NULL DEFAULT '[]',
    ml_json        TEXT NOT NULL DEFAULT '[]',
    graph_json     TEXT NOT NULL DEFAULT '{}',
    aml_json       TEXT NOT NULL DEFAULT '{}',
    top_reasons_json TEXT NOT NULL DEFAULT '[]',
    typology       TEXT,
    reasoning_ar   TEXT,
    ai_model       TEXT,
    idempotency_key TEXT UNIQUE,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dec_tenant ON decisions(tenant_id, ts);
CREATE INDEX IF NOT EXISTS idx_dec_tx ON decisions(tx_id);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id    TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    tx_id       TEXT,
    decision_id TEXT,
    severity    TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'open',
    assignee    TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    notes_json  TEXT NOT NULL DEFAULT '[]',
    resolution  TEXT
);
CREATE INDEX IF NOT EXISTS idx_al_tenant ON alerts(tenant_id, status);

CREATE TABLE IF NOT EXISTS cases (
    case_id     TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',
    priority    TEXT NOT NULL DEFAULT 'medium',
    narrative   TEXT,
    tx_ids_json     TEXT NOT NULL DEFAULT '[]',
    alert_ids_json  TEXT NOT NULL DEFAULT '[]',
    notes_json      TEXT NOT NULL DEFAULT '[]',
    assignee    TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    resolution  TEXT
);
CREATE INDEX IF NOT EXISTS idx_case_tenant ON cases(tenant_id, status);

CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    tenant_id    TEXT,
    actor        TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    resource     TEXT,
    resource_id  TEXT,
    request_id   TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_log(tenant_id, ts);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_log(event_type);

CREATE TABLE IF NOT EXISTS rules (
    rule_id      TEXT PRIMARY KEY,
    tenant_id    TEXT,           -- NULL = platform-wide default rule
    name         TEXT NOT NULL,
    severity     TEXT NOT NULL,
    score        REAL NOT NULL,
    enabled      INTEGER NOT NULL DEFAULT 1,
    tags_json    TEXT NOT NULL DEFAULT '[]',
    description  TEXT,
    when_json    TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rules_tenant ON rules(tenant_id);

CREATE TABLE IF NOT EXISTS webhooks_seen (
    idempotency_key TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    tx_id       TEXT NOT NULL,
    first_seen  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id  TEXT NOT NULL DEFAULT 'platform',
    list_type  TEXT NOT NULL,     -- sanctions | pep | high_risk_country
    value      TEXT NOT NULL,
    meta_json  TEXT NOT NULL DEFAULT '{}',
    UNIQUE(tenant_id, list_type, value)
);

CREATE TABLE IF NOT EXISTS model_registry (
    model_name   TEXT NOT NULL,
    version      TEXT NOT NULL,
    path         TEXT,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    trained_at   TEXT,
    is_active    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (model_name, version)
);

CREATE TABLE IF NOT EXISTS investigators (
    investigator_id TEXT PRIMARY KEY,
    tenant_id      TEXT NOT NULL DEFAULT 'platform',
    email          TEXT NOT NULL UNIQUE,
    name           TEXT NOT NULL,
    password_hash  TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'active',
    created_at     TEXT NOT NULL,
    last_login_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_inv_tenant ON investigators(tenant_id, status);
"""

# Migration 003: tenant-scoped investigators + tenant limits + report fields.
# Runs only once thanks to schema_migrations bookkeeping. Safe on existing DBs.
_SCHEMA_003 = """
ALTER TABLE investigators ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'platform';
CREATE INDEX IF NOT EXISTS idx_inv_tenant ON investigators(tenant_id, status);

ALTER TABLE tenants ADD COLUMN investigator_limit INTEGER NOT NULL DEFAULT 5;
ALTER TABLE tenants ADD COLUMN timezone TEXT NOT NULL DEFAULT 'Asia/Aden';
ALTER TABLE tenants ADD COLUMN review_message TEXT;
"""

# Migration 005: multi-currency money model + FX infrastructure + financial events.
# Fully additive: new tables (currencies, fx_rates, account_profiles) + new nullable/
# defaulted columns on transactions & decisions. Existing rows keep their original
# (amount, currency) untouched; legacy rows get fx_status='LEGACY_DATA' semantics via
# NULL reference fields (never invented historical rates).
_MONEY_FX_DDL = """
CREATE TABLE IF NOT EXISTS currencies (
    code         TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    minor_unit   INTEGER NOT NULL DEFAULT 2,
    round_unit   REAL NOT NULL DEFAULT 1000,
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fx_rates (
    rate_id      TEXT PRIMARY KEY,
    base_ccy     TEXT NOT NULL,
    quote_ccy    TEXT NOT NULL,
    rate         REAL NOT NULL,
    rate_type    TEXT NOT NULL DEFAULT 'mid',
    source       TEXT NOT NULL,
    region       TEXT NOT NULL DEFAULT 'global',
    spread_pct   REAL,
    fetched_at   TEXT NOT NULL,
    valid_from   TEXT NOT NULL,
    valid_to     TEXT,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fx_lookup ON fx_rates(base_ccy, quote_ccy, region, valid_from);
CREATE INDEX IF NOT EXISTS idx_fx_region ON fx_rates(region, source);

CREATE TABLE IF NOT EXISTS account_profiles (
    tenant_id    TEXT NOT NULL,
    account_id   TEXT NOT NULL,
    tx_count     INTEGER NOT NULL DEFAULT 0,
    total_ref    REAL NOT NULL DEFAULT 0,
    avg_ref      REAL,
    median_ref   REAL,
    currency_basket_json TEXT NOT NULL DEFAULT '{}',
    beneficiary_set_json TEXT NOT NULL DEFAULT '[]',
    region_set_json      TEXT NOT NULL DEFAULT '[]',
    device_set_json      TEXT NOT NULL DEFAULT '[]',
    first_seen   TEXT,
    last_seen    TEXT,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (tenant_id, account_id)
);
"""

_MIGRATIONS: list[tuple[str, list[str]]] = [
    ("001_init", [_SCHEMA]),
    (
        "002_investigator_workflow",
        [
            "ALTER TABLE alerts ADD COLUMN notes_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE alerts ADD COLUMN resolution TEXT",
            "ALTER TABLE cases ADD COLUMN resolution TEXT",
        ],
    ),
    (
        "003_tenant_scoped_investigators",
        [
            "ALTER TABLE investigators ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'platform'",
            "ALTER TABLE tenants ADD COLUMN investigator_limit INTEGER NOT NULL DEFAULT 5",
            "ALTER TABLE tenants ADD COLUMN timezone TEXT NOT NULL DEFAULT 'Asia/Aden'",
            "ALTER TABLE tenants ADD COLUMN review_message TEXT",
        ],
    ),
    (
        "005_money_fx",
        [
            _MONEY_FX_DDL,
            # transactions: reference money + FX proof + financial-event semantics.
            # All nullable — legacy rows stay valid, original (amount, currency) untouched.
            "ALTER TABLE transactions ADD COLUMN reference_amount REAL",
            "ALTER TABLE transactions ADD COLUMN reference_currency TEXT",
            "ALTER TABLE transactions ADD COLUMN fx_snapshot_id TEXT",
            "ALTER TABLE transactions ADD COLUMN fx_status TEXT",
            "ALTER TABLE transactions ADD COLUMN region TEXT",
            "ALTER TABLE transactions ADD COLUMN event_type TEXT NOT NULL DEFAULT 'transfer'",
            "ALTER TABLE transactions ADD COLUMN direction TEXT NOT NULL DEFAULT 'out'",
            "ALTER TABLE transactions ADD COLUMN is_internal INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE transactions ADD COLUMN linked_tx_id TEXT",
            # decisions: immutable audit snapshot of what the engine saw at decision time.
            "ALTER TABLE decisions ADD COLUMN tx_snapshot_json TEXT",
            "ALTER TABLE decisions ADD COLUMN features_snapshot_json TEXT",
            "ALTER TABLE decisions ADD COLUMN fx_proof_json TEXT",
            # speed up per-account velocity/aggregation on the reference value.
            "CREATE INDEX IF NOT EXISTS idx_tx_sender_ts ON transactions(tenant_id, sender_account_id, ts)",
            "CREATE INDEX IF NOT EXISTS idx_tx_ref ON transactions(tenant_id, reference_amount)",
        ],
    ),
    (
        "011_audit_hashchain",
        [
            "ALTER TABLE audit_log ADD COLUMN prev_hash TEXT",
            "ALTER TABLE audit_log ADD COLUMN entry_hash TEXT",
            "ALTER TABLE decisions ADD COLUMN rule_set_version TEXT",
            "ALTER TABLE decisions ADD COLUMN model_version TEXT",
            "ALTER TABLE decisions ADD COLUMN config_version TEXT",
            "ALTER TABLE decisions ADD COLUMN request_id TEXT",
        ],
    ),
    (
        # Watchlist v2 (mirrors migrations/versions/014_watchlist_v2.sql for the
        # SQLite test path; _apply_statements skips duplicate columns safely).
        "014_watchlist_v2",
        [
            "ALTER TABLE watchlist ADD COLUMN entity_kind TEXT NOT NULL DEFAULT 'entity'",
            "ALTER TABLE watchlist ADD COLUMN aliases_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE watchlist ADD COLUMN dob TEXT",
            "ALTER TABLE watchlist ADD COLUMN country TEXT",
            "ALTER TABLE watchlist ADD COLUMN identifiers_json TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE watchlist ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'",
            "ALTER TABLE watchlist ADD COLUMN external_id TEXT",
            "ALTER TABLE watchlist ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
            "ALTER TABLE watchlist ADD COLUMN valid_from TEXT",
            "ALTER TABLE watchlist ADD COLUMN valid_to TEXT",
            "ALTER TABLE watchlist ADD COLUMN created_at TEXT",
            "ALTER TABLE watchlist ADD COLUMN updated_at TEXT",
            "ALTER TABLE watchlist ADD COLUMN deactivated_at TEXT",
            """CREATE TABLE IF NOT EXISTS watchlist_sync_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id   TEXT NOT NULL DEFAULT 'platform',
                provider    TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'running',
                started_at  TEXT NOT NULL,
                finished_at TEXT,
                added       INTEGER NOT NULL DEFAULT 0,
                updated     INTEGER NOT NULL DEFAULT 0,
                removed     INTEGER NOT NULL DEFAULT 0,
                error       TEXT,
                detail_json TEXT NOT NULL DEFAULT '{}'
            );""",
        ],
    ),
    (
        # Component health evidence on decisions (mirrors 015_component_health.sql).
        "015_component_health",
        [
            "ALTER TABLE decisions ADD COLUMN component_health_json TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE decisions ADD COLUMN degraded_mode INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE decisions ADD COLUMN degraded_reason TEXT",
        ],
    ),
]


_SCHEMA_011 = """
ALTER TABLE audit_log ADD COLUMN prev_hash TEXT;
ALTER TABLE audit_log ADD COLUMN entry_hash TEXT;
ALTER TABLE decisions ADD COLUMN rule_set_version TEXT;
ALTER TABLE decisions ADD COLUMN model_version TEXT;
ALTER TABLE decisions ADD COLUMN config_version TEXT;
ALTER TABLE decisions ADD COLUMN request_id TEXT;
"""


def _apply_statements(conn: sqlite3.Connection, statements: list[str]) -> None:
    """Apply DDL defensively — ALTER ADD COLUMN is skipped when the column exists,
    so re-runs and pre-existing schemas never break (forward-only, idempotent)."""
    for sql in statements:
        stmt = sql.strip()
        if stmt.upper().startswith("ALTER TABLE") and "ADD COLUMN" in stmt.upper():
            tokens = stmt.split()
            try:
                table, col = tokens[2], tokens[5]
            except IndexError:
                conn.executescript(sql)
                continue
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if col in cols:
                continue
        try:
            # executescript: _SCHEMA is one string containing MANY statements
            # (SQLite rejects multi-statement strings via execute()).
            conn.executescript(sql)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" in str(exc):
                continue  # legacy DB that already carries the column — safe skip
            raise


class Database:
    """Minimal SQLite wrapper with forward-only migration runner."""

    def __init__(self, path: str | None = None):
        self.path = path or settings.db_path
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def migrate(self) -> None:
        with self._lock:
            conn = self._conn()
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            # Schema parity with PostgreSQL (006_pg_hardening adds sha256 NOT NULL there).
            # SQLite keeps it nullable so historical 2-column rows stay valid.
            _sm_cols = [
                r[1] for r in conn.execute("PRAGMA table_info(schema_migrations)").fetchall()
            ]
            if "sha256" not in _sm_cols:
                conn.execute("ALTER TABLE schema_migrations ADD COLUMN sha256 TEXT")
            from datetime import datetime

            for name, statements in _MIGRATIONS:
                applied = conn.execute(
                    "SELECT 1 FROM schema_migrations WHERE name=?", (name,)
                ).fetchone()
                if applied:
                    continue
                _apply_statements(conn, statements)
                conn.execute(
                    "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
                    (name, datetime.now(UTC).isoformat()),
                )
                conn.commit()
                print(f"MIGRATION_APPLIED {name}")

            # Defensive indexes — AFTER migrations, each guarded so a legacy
            # schema missing a column can never crash startup.
            for idx in (
                "CREATE INDEX IF NOT EXISTS idx_inv_tenant ON investigators(tenant_id, status)",
                "CREATE INDEX IF NOT EXISTS idx_al_tenant ON alerts(tenant_id, status)",
                "CREATE INDEX IF NOT EXISTS idx_case_tenant ON cases(tenant_id, status)",
                "CREATE INDEX IF NOT EXISTS idx_dec_tenant ON decisions(tenant_id, ts)",
                "CREATE INDEX IF NOT EXISTS idx_tx_tenant ON transactions(tenant_id, ts)",
                "CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_log(tenant_id, ts)",
                "CREATE INDEX IF NOT EXISTS idx_rules_tenant ON rules(tenant_id)",
            ):
                try:
                    conn.execute(idx)
                except sqlite3.OperationalError:
                    pass
            conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn().execute(sql, params)
            self._conn().commit()
            return cur

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            rows = self._conn().execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def query_one(self, sql: str, params: tuple = ()) -> dict | None:
        with self._lock:
            row = self._conn().execute(sql, params).fetchone()
            return dict(row) if row else None

    def set_tenant(self, tenant_id: str) -> None:
        """RLS no-op on SQLite (tests/dev)."""
        return None

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None


# ── PostgreSQL storage backend (TASK 1) ───────────────────────────────
# The repository layer imports `Database` from app.db. When the platform is
# configured with AEGIS_DB_DRIVER=postgres, `Database` resolves to the
# PostgreSQL backend (app.pgdb.PGDatabase) with zero repository changes.
# Import is guarded so SQLite mode keeps working without psycopg installed.
try:
    from app.pgdb import PGDatabase
except ImportError:  # psycopg not installed — SQLite mode only
    PGDatabase = None

# ── Driver resolution — PostgreSQL is the production database (TASK 1) ─────
# Default is now "postgres". SQLite is retained ONLY for hermetic unit tests,
# which set AEGIS_DB_DRIVER=sqlite explicitly (tests/conftest.py). Running the
# app in production without a valid PostgreSQL now fails fast with a clear
# error instead of silently falling back to a file-backed SQLite database.
_db_driver = getattr(settings, "DB_DRIVER", None) or getattr(settings, "db_driver", "postgres")
if _db_driver == "postgres":
    if PGDatabase is None:
        raise RuntimeError(
            "AEGIS_DB_DRIVER=postgres but psycopg is not installed. "
            "PostgreSQL is the production database; install psycopg or set "
            "AEGIS_DB_DRIVER=sqlite explicitly for isolated tests only."
        )
    if not getattr(settings, "DATABASE_URL", ""):
        raise RuntimeError(
            "AEGIS_DB_DRIVER=postgres but DATABASE_URL is empty. PostgreSQL is "
            "the production database; set DATABASE_URL (postgresql://...) to run."
        )
    Database = PGDatabase  # noqa: F811
