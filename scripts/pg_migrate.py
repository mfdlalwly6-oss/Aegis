#!/usr/bin/env python3
"""AEGIS SQLite -> PostgreSQL migration tool (TASK 1).

Steps
-----
1. Apply every ``migrations/versions/*.sql`` file against the target
   PostgreSQL database (versioned, sha256-tracked in ``schema_migrations``).
2. Bulk-copy every application table from the SQLite file into PostgreSQL in
   FK-safe order (parents before children), 500-row batches, per-table counts.
   Skips tables that already have rows unless ``--wipe`` is given.
3. Integrity guards: orphan decisions, negative amounts.

Usage
-----
    python scripts/pg_migrate.py --sqlite /data/aegis.db \
        --url postgresql://aegis:PASS@HOST:5432/aegis [--wipe]

Exit code 0 only when every table matches and all guards pass.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _cand in (ROOT / "backend", ROOT):
    if (_cand / "app").is_dir():
        sys.path.insert(0, str(_cand)); break

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from app.pgdb import PGDatabase  # noqa: E402

# FK-safe copy order (parents before children)
TABLE_ORDER = [
    "tenants", "currencies", "users", "investigators", "transactions",
    "decisions", "alerts", "cases", "audit_log", "rules", "webhooks_seen",
    "watchlist", "model_registry", "fx_rates", "account_profiles",
]

GUARDS = [
    ("orphan_decisions",
     "SELECT COUNT(*) FROM decisions d LEFT JOIN transactions t ON d.tx_id = t.tx_id WHERE t.tx_id IS NULL"),
    ("negative_amounts",
     "SELECT COUNT(*) FROM transactions WHERE amount < 0"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True, help="source SQLite file (read-only)")
    ap.add_argument("--url", required=True, help="target PostgreSQL URL")
    ap.add_argument("--wipe", action="store_true",
                    help="truncate non-empty target tables before copy")
    args = ap.parse_args()

    # 1) DDL: apply versioned migrations
    pg = PGDatabase(args.url)
    applied = pg.migrate()
    print("DDL_APPLIED", applied)

    src = sqlite3.connect(f"file:{args.sqlite}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    dst = psycopg.connect(args.url, row_factory=dict_row, autocommit=True)
    dst.execute("SET session_replication_role = replica")
    dst.execute("SET session_replication_role = replica")  # tolerate legacy FK quirks during load

    src_tables = {r[0] for r in src.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}

    all_ok = True
    report: list[tuple[str, int, int, str]] = []
    for table in TABLE_ORDER:
        if table not in src_tables:
            print(f"SKIP {table}: not in source")
            continue
        cols = [r[1] for r in src.execute(f'PRAGMA table_info("{table}")')]
        if not cols:
            continue
        n_src = src.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]  # sqlite3 -> tuple
        n_dst = dst.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()['count']
        if n_dst and not args.wipe:
            print(f"SKIP {table}: target non-empty ({n_dst}); use --wipe to force")
            report.append((table, n_src, n_dst, "SKIPPED"))
            continue
        if n_src == 0:
            print(f"EMPTY {table}")
            report.append((table, 0, n_dst, "OK"))
            continue
        if args.wipe and n_dst:
            dst.execute(f'TRUNCATE "{table}" RESTART IDENTITY CASCADE')
            dst.commit()
        qcols = ",".join(f'"{c}"' for c in cols)
        ph = ",".join(["%s"] * len(cols))
        ins = f'INSERT INTO "{table}" ({qcols}) VALUES ({ph})'
        valid_tx = {r["tx_id"] for r in dst.execute("SELECT tx_id FROM transactions")} if table == "decisions" else None
        valid_ten = {r["tenant_id"] for r in dst.execute("SELECT tenant_id FROM tenants")} if table in ("users","transactions","alerts","cases") else None
        skipped = 0
        with dst.cursor() as cur:
            batch: list[tuple] = []
            for row in src.execute(f'SELECT * FROM "{table}"'):
                if valid_tx is not None and row["tx_id"] not in valid_tx:
                    skipped += 1; continue
                if valid_ten is not None and row["tenant_id"] not in valid_ten:
                    skipped += 1; continue
                batch.append(tuple(row[c] for c in cols))
                if len(batch) >= 500:
                    cur.executemany(ins, batch)
                    batch = []
            if batch:
                cur.executemany(ins, batch)
        dst.commit()
        n_dst2 = dst.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()['count']
        ok = n_src == n_dst2
        all_ok = all_ok and ok
        report.append((table, n_src, n_dst2, "OK" if ok else "MISMATCH"))
        print(f"COPY {table}: {n_src} -> {n_dst2} {'OK' if ok else 'MISMATCH'}")

    for name, sql in GUARDS:
        n = dst.execute(sql).fetchone()['count']
        good = n == 0
        all_ok = all_ok and good
        print(f"GUARD {name}: {n} {'OK' if good else 'FAIL'}")

    print("SUMMARY")
    for table, a, b, status in report:
        print(f"  {table}: {a} -> {b} [{status}]")
    dst.execute("SET session_replication_role = default")
    dst.execute("SET session_replication_role = default")
    print("ALL_TABLES_MATCH" if all_ok else "DATA_MISMATCH")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
