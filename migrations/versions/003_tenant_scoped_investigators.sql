-- 003_tenant_scoped_investigators — historical migration.
-- No-op on a fresh PostgreSQL baseline (001 already includes these columns).
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'platform';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS investigator_limit INTEGER NOT NULL DEFAULT 5;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'Asia/Aden';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS review_message TEXT;
