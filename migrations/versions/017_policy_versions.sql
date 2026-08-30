-- Policy versioning: every policy change for a tenant is an immutable,
-- numbered, attributed version. The ACTIVE version (or the latest) is what
-- update-time materializes into tenants.policy_json (the decision hot path
-- stays unchanged); history is never rewritten, so an old decision keeps its
-- policy_version and can be traced to the exact effective policy.
--
-- Architectural note (matches 016_rule_overrides): NO cross-table FOREIGN KEY.
-- After the RLS hardening (008/010) the app connects as role `aegis_app`, which
-- holds SELECT/INSERT/UPDATE/DELETE but NOT REFERENCES on `tenants` — so a FK
-- here would fail migrations with InsufficientPrivilege. Tenant linkage is
-- enforced at the repository layer instead, and row isolation is enforced by
-- RLS below (platform sees all; a tenant sees only its own versions).
CREATE TABLE IF NOT EXISTS policy_versions (
    tenant_id    TEXT NOT NULL,
    version      INTEGER NOT NULL,
    policy_json  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active',     -- active | disabled
    created_by   TEXT NOT NULL DEFAULT 'owner',
    created_at   TEXT NOT NULL,
    note         TEXT,
    PRIMARY KEY (tenant_id, version)
);
CREATE INDEX IF NOT EXISTS idx_policy_versions_tenant ON policy_versions(tenant_id);

-- Tenant isolation + platform access, same shape as 009/013.
ALTER TABLE policy_versions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS policy_versions_isolation ON policy_versions;
CREATE POLICY policy_versions_isolation ON policy_versions
  USING (current_setting('app.tenant_id', true) = 'platform'
         OR tenant_id = current_setting('app.tenant_id', true))
  WITH CHECK (current_setting('app.tenant_id', true) = 'platform'
         OR tenant_id = current_setting('app.tenant_id', true));
