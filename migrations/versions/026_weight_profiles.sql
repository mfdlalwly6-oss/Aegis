-- Migration 026: Risk Weights management (default + per-tenant overrides)
-- Idempotent: safe to run multiple times.
--
-- weight_profiles holds ONE platform default row (scope="default", tenant_id=NULL)
-- plus optional per-tenant override rows (scope="tenant", tenant_id=<id>).
-- Resolution rule: active tenant override wins; otherwise the default row.
-- Overrides are never copied per tenant — tenants without an override simply
-- have no row and inherit the default live.

CREATE TABLE IF NOT EXISTS weight_profiles (
    profile_id   TEXT PRIMARY KEY,
    scope        TEXT NOT NULL DEFAULT 'tenant' CHECK (scope IN ('default','tenant')),
    tenant_id    TEXT DEFAULT NULL,               -- NULL only for the default row
    rules        NUMERIC(6,4) NOT NULL DEFAULT 0.35,
    ml           NUMERIC(6,4) NOT NULL DEFAULT 0.25,
    graph        NUMERIC(6,4) NOT NULL DEFAULT 0.15,
    aml          NUMERIC(6,4) NOT NULL DEFAULT 0.15,
    behavior     NUMERIC(6,4) NOT NULL DEFAULT 0.10,
    active       INTEGER NOT NULL DEFAULT 1,      -- 0 => disabled override (falls back to default)
    created_by   TEXT NOT NULL DEFAULT 'owner',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    note         TEXT DEFAULT NULL,
    UNIQUE(scope, tenant_id),
    CHECK (ABS((rules + ml + graph + aml + behavior) - 1.0) < 0.0001)
);

CREATE INDEX IF NOT EXISTS idx_weight_profiles_tenant ON weight_profiles(tenant_id);

-- Seed the single default row (idempotent INSERT ... ON CONFLICT DO NOTHING).
INSERT INTO weight_profiles (profile_id, scope, tenant_id, rules, ml, graph, aml, behavior, active, created_by, created_at, updated_at)
SELECT 'wp_default', 'default', NULL, 0.35, 0.25, 0.15, 0.15, 0.10, 1, 'system',
       to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.FF6"Z"'),
       to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.FF6"Z"')
WHERE NOT EXISTS (SELECT 1 FROM weight_profiles WHERE scope='default');
