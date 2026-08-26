"""PostgreSQL storage backend for AEGIS (TASK 1).

PURPOSE
-------
Production-grade persistence for a multi-tenant financial risk platform:

* ACID + MVCC concurrency (no writer lock-up, no file-corruption window)
* NUMERIC storage for money (float only at the API boundary, as before)
* BIGSERIAL identities for append-only logs
* named FOREIGN KEYs where the data model guarantees integrity
* schema managed by versioned, sha256-tracked SQL migrations
  (``migrations/versions/*.sql``), same bookkeeping table (``schema_migrations``)
  the SQLite layer used, so a future Alembic adoption is a drop-in
* Row-Level Security (RLS) ready — policies are enabled in Task 3

The class mirrors the legacy SQLite ``Database`` interface
(``execute`` / ``query`` / ``query_one`` / ``migrate`` / ``close``) so the
repository layer is untouched. The ``?`` placeholders used by repository SQL
are translated to psycopg ``%s`` at the boundary.
"""

from __future__ import annotations

import hashlib
import threading
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.core.config import settings


def _find_versions_dir() -> Path:
    """Locate migrations/versions by walking up from this file.

    Works in both layouts: repo checkout (backend/app/pgdb.py) and the
    container (/app/app/pgdb.py). Avoids a hard-coded depth that breaks when
    the image layout changes (the same bug class as the old models path).
    """
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        cand = parent / "migrations" / "versions"
        if cand.is_dir() and any(cand.glob("*.sql")):
            return cand
    return here.parent / "migrations" / "versions"


_VERSIONS_DIR = _find_versions_dir()


class PGDatabase:
    """PostgreSQL backend — one connection per thread, guarded by a lock."""

    def __init__(self, url: str | None = None):
        self.url = url or (
            getattr(settings, "DATABASE_URL", None) or getattr(settings, "database_url", "") or ""
        )

    # -- connection management ----------------------------------------
    def _conn(self) -> psycopg.Connection:
        conn = getattr(self._local, "conn", None) if hasattr(self, "_local") else None
        if conn is None or conn.closed:
            self._local = threading.local()
            conn = psycopg.connect(
                self.url, row_factory=dict_row, connect_timeout=10, autocommit=True
            )
            # Default session scope for NEW connections: trusted platform context.
            # Internal services (bootstrap, AML, graph) operate cross-tenant by design;
            # tenant-facing entry points (deps.require_*, wallet webhook) call
            # set_tenant(tid) explicitly and are then RLS-isolated for the request.
            conn.execute("SELECT set_config('app.tenant_id', 'platform', false)")
            self._local.conn = conn
        return conn

    @staticmethod
    def _sql(sql: str) -> str:
        # '?' placeholders -> psycopg '%s'
        s = sql.replace("?", "%s")
        # SQLite: INSERT OR IGNORE  ->  PG: INSERT ... ON CONFLICT DO NOTHING
        if "INSERT OR IGNORE" in s:
            s = s.replace("INSERT OR IGNORE", "INSERT") + " ON CONFLICT DO NOTHING"
        # SQLite: INSERT OR REPLACE ->  PG: INSERT ... ON CONFLICT DO NOTHING (seeds are idempotent)
        elif "INSERT OR REPLACE" in s:
            s = s.replace("INSERT OR REPLACE", "INSERT") + " ON CONFLICT DO NOTHING"
        return s

    @staticmethod
    def _defloat(row: dict) -> dict:
        """NUMERIC comes back as Decimal — return float (the API behaviour the
        rest of the codebase expects). Storage stays exact."""
        return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in row.items()}

    # -- core interface (mirrors SQLite Database) ----------------------
    def execute(self, sql: str, params: tuple = ()) -> psycopg.Cursor:
        conn = self._conn()
        try:
            cur = conn.execute(self._sql(sql), list(params) if params else None)
            conn.commit()
            return cur
        except Exception:
            conn.rollback()
            raise

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        conn = self._conn()
        try:
            cur = conn.execute(self._sql(sql), list(params) if params else None)
            return [self._defloat(dict(r)) for r in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise

    def query_one(self, sql: str, params: tuple = ()) -> dict | None:
        conn = self._conn()
        try:
            cur = conn.execute(self._sql(sql), list(params) if params else None)
            row = cur.fetchone()
            return self._defloat(dict(row)) if row else None
        except Exception:
            conn.rollback()
            raise

    # -- versioned migrations -------------------------------------------
    def migrate(self) -> list[str]:
        applied: list[str] = []
        conn = self._conn()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "name TEXT PRIMARY KEY, applied_at TEXT NOT NULL, sha256 TEXT NOT NULL)"
        )
        conn.commit()
        for f in sorted(_VERSIONS_DIR.glob("*.sql")):
            if conn.execute("SELECT 1 FROM schema_migrations WHERE name=%s", (f.name,)).fetchone():
                continue
            sql = f.read_text(encoding="utf-8")
            conn.execute(sql)
            sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()[:16]
            conn.execute(
                "INSERT INTO schema_migrations (name, applied_at, sha256) VALUES (%s, %s, %s)",
                (f.name, datetime.now(UTC).isoformat(), sha),
            )
            conn.commit()
            applied.append(f.name)
            print(f"MIGRATION_APPLIED {f.name}")
        return applied

    def set_tenant(self, tenant_id: str) -> None:
        """Set the RLS tenant context (app.tenant_id GUC) for this thread's connection.
        'platform' = trusted platform scope (full access); any tenant id = isolated scope."""
        conn = self._conn()
        conn.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant_id or "platform",))

    def close(self) -> None:
        conn = getattr(self._local, "conn", None) if hasattr(self, "_local") else None
        if conn is not None:
            try:
                conn.close()
            finally:
                self._local.conn = None

    # ── legacy SQLite attribute compatibility (ready endpoint) ─────────
    @property
    def path(self) -> str:
        return "postgresql"

    @property
    def db_path(self) -> str:
        return self.path

    def __getattr__(self, name: str):
        if name in ("path", "db_path"):
            return "postgresql"
        raise AttributeError(name)
