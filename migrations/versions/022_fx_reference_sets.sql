-- 022_fx_reference_sets.sql
-- 4-tier FX model: Manual Override > Institution > Reference Set > General.
-- fx_reference_sets: named reference rate sets (USD/YER + SAR/YER) that can be
--   assigned to many institutions and edited in place (members preserved).
-- fx_reference_members: set<->tenant assignment; a tenant belongs to at most one
--   active set (enforced in repo by auto-reassignment, with audit).
-- General rates remain fx_rates rows with tenant_id IS NULL (source-ranked).

CREATE TABLE IF NOT EXISTS fx_reference_sets (
    set_id       TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    usd_yer      NUMERIC(28,12) NOT NULL CHECK (usd_yer > 0),
    sar_yer      NUMERIC(28,12) NOT NULL CHECK (sar_yer > 0),
    active       INTEGER NOT NULL DEFAULT 1,
    created_by   TEXT NOT NULL DEFAULT 'owner',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fx_reference_members (
    set_id     TEXT NOT NULL REFERENCES fx_reference_sets(set_id),
    tenant_id  TEXT NOT NULL,
    added_by   TEXT NOT NULL DEFAULT 'owner',
    added_at   TEXT NOT NULL,
    PRIMARY KEY (set_id, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_fx_ref_members_tenant ON fx_reference_members(tenant_id);
CREATE INDEX IF NOT EXISTS idx_fx_ref_sets_active ON fx_reference_sets(active);
