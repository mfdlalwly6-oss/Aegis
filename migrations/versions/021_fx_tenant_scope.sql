-- 021_fx_tenant_scope.sql
-- Add per-tenant scoping to the append-only fx_rates store.
-- tenant_id NULL  => platform-wide rate (applies to every tenant)
-- tenant_id = X   => Tenant FX Override (applies ONLY to tenant X, outranks platform rates)
-- The store stays append-only: historical snapshots are never mutated.

ALTER TABLE fx_rates ADD COLUMN IF NOT EXISTS tenant_id TEXT;

-- Fast lookup for the resolver: (tenant, pair, validity window)
CREATE INDEX IF NOT EXISTS idx_fx_tenant_lookup
    ON fx_rates(tenant_id, base_ccy, quote_ccy, valid_from);
