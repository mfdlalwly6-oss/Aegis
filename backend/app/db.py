"""AEGIS database layer — PostgreSQL only.

`Database` is ALWAYS the PostgreSQL backend (app.pgdb.PGDatabase). There is no
SQLite path, no SQLite fallback, and no file-backed database. Repositories and
services import `Database` from here and receive the PostgreSQL implementation.
Running without a reachable PostgreSQL / psycopg fails fast with a clear error.
"""

from __future__ import annotations

try:
    from app.pgdb import PGDatabase
except ImportError as exc:  # psycopg missing — PostgreSQL is required
    raise RuntimeError(
        "psycopg is not installed. AEGIS requires PostgreSQL (psycopg). "
        "Install psycopg to run the platform or its tests."
    ) from exc

Database = PGDatabase  # noqa: F811
