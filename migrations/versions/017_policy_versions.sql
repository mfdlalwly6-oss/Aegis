-- Policy versioning: every policy change for a tenant is an immutable,
-- numbered, attributed version. The ACTIVE version (or the latest) is what
-- update-time materializes into tenants.policy_json (the decision hot path
-- stays unchanged); history is never rewritten, so an old decision keeps its
-- policy_version and can be traced to the exact effective policy.
CREATE TABLE IF NOT EXISTS policy_versions (
    tenant_id    TEXT NOT NULL REFERENCES tenants(tenant_id),
    version      INTEGER NOT NULL,
    policy_json  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active',     -- active | disabled
    created_by   TEXT NOT NULL DEFAULT 'owner',
    created_at   TEXT NOT NULL,
    note         TEXT,
    PRIMARY KEY (tenant_id, version)
);
CREATE INDEX IF NOT EXISTS idx_policy_versions_tenant ON policy_versions(tenant_id);
