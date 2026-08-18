"""SQLite database layer — real persistent storage with migrations.
Thread-safe via check_same_thread=False + explicit transactions.
Swappable to PostgreSQL later: all access goes through app/repositories/.
"""
from __future__ import annotations

import sqlite3
import threading
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
    deleted_at     TEXT
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
    updated_at  TEXT NOT NULL
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
    updated_at  TEXT NOT NULL
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
    list_type  TEXT NOT NULL,     -- sanctions | pep | high_risk_country
    value      TEXT NOT NULL,
    meta_json  TEXT NOT NULL DEFAULT '{}',
    UNIQUE(list_type, value)
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
"""

_SCHEMA_002 = """
CREATE TABLE IF NOT EXISTS investigators (
    investigator_id TEXT PRIMARY KEY,
    email          TEXT NOT NULL UNIQUE,
    name           TEXT NOT NULL,
    password_hash  TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'active',
    created_at     TEXT NOT NULL,
    last_login_at  TEXT
);

ALTER TABLE alerts ADD COLUMN notes_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE alerts ADD COLUMN resolution TEXT;
ALTER TABLE cases  ADD COLUMN resolution TEXT;
"""

_MIGRATIONS: list[tuple[str, str]] = [
    ("001_init", _SCHEMA),
    ("002_investigator_workflow", _SCHEMA_002),
]


class Database:
    """Minimal SQLite wrapper with migration runner."""

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
            from datetime import datetime, timezone
            for name, sql in _MIGRATIONS:
                applied = conn.execute(
                    "SELECT 1 FROM schema_migrations WHERE name=?", (name,)
                ).fetchone()
                if applied:
                    continue
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
                    (name, datetime.now(timezone.utc).isoformat()),
                )
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

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
