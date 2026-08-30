-- Watchlist v2: custom types, lifecycle (enable/disable), provenance (source/external_id),
-- validity window (valid_from/valid_to), secondary matching attributes (aliases/dob/country/identifiers),
-- trigram fuzzy search, and a provider sync audit table. All additive; no data loss.

-- 1) allow 'custom' list_type (plus any future types we add deliberately)
ALTER TABLE watchlist DROP CONSTRAINT IF EXISTS chk_watchlist_type;
ALTER TABLE watchlist ADD CONSTRAINT chk_watchlist_type
  CHECK (list_type = ANY (ARRAY['sanctions','pep','high_risk_country','custom']));

-- 2) new columns (idempotent)
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS entity_kind TEXT NOT NULL DEFAULT 'entity';      -- person|organization|account|country|other
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS aliases_json TEXT NOT NULL DEFAULT '[]';          -- JSON array of alias names
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS dob TEXT;                                          -- ISO date (persons)
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS country TEXT;                                      -- nationality / jurisdiction
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS identifiers_json TEXT NOT NULL DEFAULT '{}';       -- JSON object of id schemes
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual';             -- manual|csv|<provider>
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS external_id TEXT;                                  -- provider's stable id
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';             -- active|disabled
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS valid_from TEXT;                                   -- ISO timestamp
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS valid_to TEXT;                                     -- ISO timestamp (null=open)
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS created_at TEXT NOT NULL DEFAULT to_char(now() AT TIME ZONE 'utc','YYYY-MM-DD"T"HH24:MI:SS"Z"');
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS updated_at TEXT NOT NULL DEFAULT to_char(now() AT TIME ZONE 'utc','YYYY-MM-DD"T"HH24:MI:SS"Z"');
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS deactivated_at TEXT;

-- 3) trigram extension + fuzzy index on normalized value (for name matching)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_watchlist_value_trgm ON watchlist USING gin (value gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_watchlist_status ON watchlist(status);
CREATE INDEX IF NOT EXISTS idx_watchlist_tenant ON watchlist(tenant_id);

-- 4) provider sync audit (per-tenant, RLS-isolated like watchlist)
CREATE TABLE IF NOT EXISTS watchlist_sync_log (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id     TEXT NOT NULL DEFAULT 'platform',
  provider      TEXT NOT NULL,
  started_at    TEXT NOT NULL,
  finished_at   TEXT,
  status        TEXT NOT NULL DEFAULT 'running',   -- running|ok|failed
  added         INTEGER NOT NULL DEFAULT 0,
  updated       INTEGER NOT NULL DEFAULT 0,
  removed       INTEGER NOT NULL DEFAULT 0,
  error         TEXT,
  detail_json   TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_wsl_tenant ON watchlist_sync_log(tenant_id);
ALTER TABLE watchlist_sync_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS watchlist_sync_isolation ON watchlist_sync_log;
CREATE POLICY watchlist_sync_isolation ON watchlist_sync_log
  USING (current_setting('app.tenant_id', true) = 'platform' OR tenant_id IN ('platform', current_setting('app.tenant_id', true)))
  WITH CHECK (current_setting('app.tenant_id', true) = 'platform' OR tenant_id = current_setting('app.tenant_id', true));
