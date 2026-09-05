-- 023_fx_architecture.sql
-- §11/§12/§27: versioned reference-set rates + DB-enforced FX invariants.
--
-- fx_reference_versions: append-only rate history per reference set.
--   Editing a set inserts a NEW version row (effective now); the old version is
--   closed (effective_to). Historical decisions are NEVER re-priced because each
--   decision stores its own immutable fx snapshot — this table proves the rate
--   timeline of the set itself for audit & display.
-- fx_reference_members.tenant_id UNIQUE: a tenant belongs to AT MOST ONE
--   reference set (enforced at DB level, not just in code).
-- fx_rates.active: lets the platform keep exactly ONE active general rate per
--   pair/region while preserving history (old rows flipped to active=0).

CREATE TABLE IF NOT EXISTS fx_reference_versions (
    version_id    TEXT PRIMARY KEY,
    set_id        TEXT NOT NULL REFERENCES fx_reference_sets(set_id),
    usd_yer       NUMERIC(28,12) NOT NULL CHECK (usd_yer > 0),
    sar_yer       NUMERIC(28,12) NOT NULL CHECK (sar_yer > 0),
    effective_from TEXT NOT NULL,
    effective_to   TEXT,
    created_by     TEXT NOT NULL DEFAULT 'owner'
);
CREATE INDEX IF NOT EXISTS idx_fx_ref_versions_set ON fx_reference_versions(set_id);
CREATE INDEX IF NOT EXISTS idx_fx_ref_versions_open ON fx_reference_versions(set_id, effective_to);

-- One active reference set per tenant (DB invariant, not just repo logic).
-- First collapse any accidental duplicate memberships, keeping the newest row
-- per tenant (PostgreSQL: ctid is the physical row id; rowid is SQLite-only),
-- then add the unique index on tenant_id alone (a tenant may not appear twice
-- across all sets).
DELETE FROM fx_reference_members
WHERE ctid NOT IN (
    SELECT MAX(ctid) FROM fx_reference_members GROUP BY tenant_id
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_fx_ref_members_tenant ON fx_reference_members(tenant_id);

-- Active flag on fx_rates so exactly one general rate per (base,quote,region)
-- can be 'current' while history is preserved. tenant override rows keep their
-- own active flag. Default 1 = active for existing rows.
ALTER TABLE fx_rates ADD COLUMN IF NOT EXISTS active INTEGER NOT NULL DEFAULT 1;
CREATE INDEX IF NOT EXISTS idx_fx_rates_pair_active
    ON fx_rates(base_ccy, quote_ccy, region, tenant_id, active);
