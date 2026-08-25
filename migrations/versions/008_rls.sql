-- 008_rls — PostgreSQL Row-Level Security for tenant isolation.
-- Strategy: dedicated non-owner role (aegis_app) + per-session GUC (app.tenant_id).
-- Tables WITHOUT tenant_id (currencies, fx_rates, watchlist, schema_migrations,
-- model_registry) are platform-global: RLS stays OFF for them.
-- rules is hybrid: NULL tenant_id = platform-wide default (visible to all).

-- 1. Application role (separate from owner so RLS actually applies)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aegis_app') THEN
        CREATE ROLE aegis_app LOGIN PASSWORD 'AegisApp2026Dev';
    END IF;
END $$;
GRANT CONNECT ON DATABASE aegis TO aegis_app;
GRANT USAGE ON SCHEMA public TO aegis_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aegis_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO aegis_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO aegis_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO aegis_app;

-- 2. Enable RLS on tenant-scoped tables
ALTER TABLE tenants        ENABLE ROW LEVEL SECURITY;
ALTER TABLE users          ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions   ENABLE ROW LEVEL SECURITY;
ALTER TABLE decisions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts         ENABLE ROW LEVEL SECURITY;
ALTER TABLE cases          ENABLE ROW LEVEL SECURITY;
ALTER TABLE investigators  ENABLE ROW LEVEL SECURITY;
ALTER TABLE account_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhooks_seen  ENABLE ROW LEVEL SECURITY;
ALTER TABLE rules          ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log      ENABLE ROW LEVEL SECURITY;

-- 3. Policies: rows visible only when app.tenant_id matches row tenant_id.
--    Empty/unset GUC => '' => matches nothing (deny by default).
--    Platform role operations (GUC = 'platform') see tenant_id='platform' rows only.
CREATE POLICY tenant_isolation ON tenants
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_isolation ON users
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_isolation ON transactions
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_isolation ON decisions
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_isolation ON alerts
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_isolation ON cases
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_isolation ON investigators
    USING (tenant_id = current_setting('app.tenant_id', true)
           OR tenant_id = 'platform')
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)
                OR tenant_id = 'platform');

CREATE POLICY tenant_isolation ON account_profiles
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_isolation ON webhooks_seen
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- rules: platform defaults (NULL) readable by every tenant; tenant rules only by owner
CREATE POLICY rules_isolation ON rules
    USING (tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id', true));

-- audit_log: tenant rows scoped; NULL tenant rows (platform events) platform-only
CREATE POLICY audit_isolation ON audit_log
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
