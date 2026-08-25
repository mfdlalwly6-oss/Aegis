-- Tenant-scoped imported watchlists; existing seed entries remain platform defaults.
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'platform';
ALTER TABLE watchlist DROP CONSTRAINT IF EXISTS watchlist_list_type_value_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_watchlist_tenant_type_value ON watchlist(tenant_id, list_type, value);
ALTER TABLE watchlist ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS watchlist_isolation ON watchlist;
CREATE POLICY watchlist_isolation ON watchlist
  USING (current_setting('app.tenant_id', true) = 'platform' OR tenant_id IN ('platform', current_setting('app.tenant_id', true)))
  WITH CHECK (current_setting('app.tenant_id', true) = 'platform' OR tenant_id = current_setting('app.tenant_id', true));
