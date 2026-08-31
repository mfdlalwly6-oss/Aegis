# AEGIS Deployment Guide — PostgreSQL, Migrations & `MIGRATION_DEFERRED`

This documents the **actual** behavior of `backend/app/pgdb.py` (`PGDatabase.migrate()`),
verified live. It is not a theoretical description.

## Environments

AEGIS runs the same codebase in two first-class environments:

| | Local (Docker) | Railway |
|---|---|---|
| Backend | `docker compose up -d --build aegis` (service `aegis-platform`, port 8000) | Railway service from the same Dockerfile |
| Database | `aegis-postgres` container (`postgres:16-alpine`) | Railway PostgreSQL plugin |
| Connection | `AEGIS_DATABASE_URL=postgresql://aegis:***@postgres:5432/aegis` | Railway-provided `DATABASE_URL` (mapped to `AEGIS_DATABASE_URL`) |

PostgreSQL is the only supported database in both environments. There is no SQLite path.

## How migrations run

At startup, `PGDatabase.migrate()`:

1. Creates `schema_migrations(name TEXT PRIMARY KEY, applied_at TEXT, sha256 TEXT)` if missing.
2. Iterates `migrations/versions/*.sql` **in filename order**.
3. Skips any file already recorded in `schema_migrations` (idempotent).
4. Executes the SQL, records `name + applied_at + sha256`, prints `MIGRATION_APPLIED <file>`.

## `MIGRATION_DEFERRED` — owner-only migrations

### When it happens

The application connects as the **least-privileged role `aegis_app`** (created by
`008_rls.sql`, holds `SELECT/INSERT/UPDATE/DELETE` + `CREATE ON SCHEMA public` only).
Tables created by the bootstrap superuser (`aegis`) — e.g. `tenants`, `decisions`,
`investigators` — **cannot be ALTERed by `aegis_app`** (`must be owner of table …`).

Any migration file whose name ends with **`_owner_alters.sql`** contains such
owner-only statements. If the connected role lacks `rolsuper OR rolcreatedb`,
`migrate()` does **not** run it and prints:

```
MIGRATION_DEFERRED 020_decision_confidence_owner_alters.sql — owner-only; apply manually:
  docker exec aegis-postgres psql -U aegis -d aegis -f /migrations/versions/<file>
```

### What still works after deferral

**Startup never crashes on a deferred owner migration.** The application boots
normally. Every feature not depending on the deferred column/table works
immediately; the specific feature (e.g. `decisions.confidence`,
`investigators.last_logout_at`) activates once the owner applies the file.

### What the PostgreSQL owner must run

```bash
# local Docker
cat migrations/versions/019_owner_alters.sql | docker exec -i aegis-postgres psql -U aegis -d aegis

# Railway (use the public proxy URL from the Postgres service)
psql "$RAILWAY_DATABASE_PUBLIC_URL" -f migrations/versions/019_owner_alters.sql
```

Then record it so the app stops deferring:

```sql
INSERT INTO schema_migrations (name, applied_at, sha256)
VALUES ('019_owner_alters.sql', now()::text, 'manual-owner')
ON CONFLICT (name) DO NOTHING;
```

### Verify it succeeded

```sql
SELECT name FROM schema_migrations WHERE name LIKE '%_owner_alters.sql' ORDER BY name;
-- and, e.g. for 020:
SELECT column_name FROM information_schema.columns
WHERE table_name='decisions' AND column_name='confidence';
```

### Safety rules (production)

- **Never** run `*_owner_alters.sql` as `aegis_app` — it will fail; that is expected.
- **Never** grant `aegis_app` ownership of core tables to "make migrations easier" —
  ownership separation is a deliberate RLS/least-privilege control.
- Owner migrations are idempotent (`ADD COLUMN IF NOT EXISTS`) — re-running is safe,
  but apply them deliberately, during a controlled maintenance step, and record them.
- Deferred migrations are visible in startup logs; treat an unexpected
  `MIGRATION_DEFERRED` as an operational to-do, not an error to silence.
