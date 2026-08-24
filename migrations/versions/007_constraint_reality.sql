-- 007_constraint_reality — align CHECK constraints with real operational states.
-- Soft-delete is a legitimate terminal state for tenants in a multi-tenant
-- platform (see tenants.deleted_at); excluding it blocked legitimate rows.
ALTER TABLE tenants DROP CONSTRAINT IF EXISTS chk_tenants_status;
ALTER TABLE tenants ADD CONSTRAINT chk_tenants_status
    CHECK (status IN ('active', 'suspended', 'closed', 'deleted'));
