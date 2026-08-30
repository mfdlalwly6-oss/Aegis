-- Per-tenant rule customization. Platform rules stay untouched in `rules`
-- (tenant_id IS NULL); a bank's customization lives here and REPLACES the
-- platform rule for that tenant at evaluation time (or defines a tenant-only
-- rule when no platform rule with the same rule_id exists).
-- Additive only; existing rules data untouched.
CREATE TABLE IF NOT EXISTS rule_overrides (
    tenant_id   TEXT NOT NULL REFERENCES tenants(tenant_id),
    rule_id     TEXT NOT NULL,
    enabled     INTEGER,                 -- NULL = inherit platform rule's flag
    score       REAL,                    -- NULL = inherit
    severity    TEXT,                    -- NULL = inherit
    name        TEXT,                    -- NULL = inherit
    description TEXT,                    -- NULL = inherit
    when_json   TEXT,                    -- NULL = inherit (required for tenant-only rules)
    tags_json   TEXT,                    -- NULL = inherit
    created_by  TEXT NOT NULL DEFAULT 'owner',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (tenant_id, rule_id)
);
CREATE INDEX IF NOT EXISTS idx_rule_overrides_tenant ON rule_overrides(tenant_id);
