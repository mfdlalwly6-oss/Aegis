-- 005_money_fx — multi-currency money model + FX infrastructure (PostgreSQL).
-- Fully additive on the 001 baseline: new tables (currencies, fx_rates,
-- account_profiles) + nullable columns on transactions & decisions.
-- Legacy rows keep their original (amount, currency) untouched; reference
-- fields stay NULL (= LEGACY_DATA semantics, never invented rates).
-- Historical parity with SQLite migration 005.

CREATE TABLE IF NOT EXISTS currencies (
    code         TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    minor_unit   INTEGER NOT NULL DEFAULT 2,
    round_unit   NUMERIC(28,12) NOT NULL DEFAULT 1000,
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL,
    CONSTRAINT chk_ccy_minor CHECK (minor_unit >= 0)
);

CREATE TABLE IF NOT EXISTS fx_rates (
    rate_id      TEXT PRIMARY KEY,
    base_ccy     TEXT NOT NULL,
    quote_ccy    TEXT NOT NULL,
    rate         NUMERIC(28,12) NOT NULL,
    rate_type    TEXT NOT NULL DEFAULT 'mid',
    source       TEXT NOT NULL,
    region       TEXT NOT NULL DEFAULT 'global',
    spread_pct   NUMERIC(12,8),
    fetched_at   TEXT NOT NULL,
    valid_from   TEXT NOT NULL,
    valid_to     TEXT,
    created_at   TEXT NOT NULL,
    CONSTRAINT chk_fx_rate CHECK (rate > 0)
);
CREATE INDEX IF NOT EXISTS idx_fx_lookup ON fx_rates(base_ccy, quote_ccy, region, valid_from);
CREATE INDEX IF NOT EXISTS idx_fx_region ON fx_rates(region, source);

CREATE TABLE IF NOT EXISTS account_profiles (
    tenant_id    TEXT NOT NULL,
    account_id   TEXT NOT NULL,
    tx_count     INTEGER NOT NULL DEFAULT 0,
    total_ref    NUMERIC(28,12) NOT NULL DEFAULT 0,
    avg_ref      NUMERIC(28,12),
    median_ref   NUMERIC(28,12),
    currency_basket_json TEXT NOT NULL DEFAULT '{}',
    beneficiary_set_json TEXT NOT NULL DEFAULT '[]',
    region_set_json      TEXT NOT NULL DEFAULT '[]',
    device_set_json      TEXT NOT NULL DEFAULT '[]',
    first_seen   TEXT,
    last_seen    TEXT,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (tenant_id, account_id)
);

-- transactions: reference money + FX proof + financial-event semantics.
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS reference_amount NUMERIC(28,12);
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS reference_currency TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS fx_snapshot_id TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS fx_status TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS region TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS event_type TEXT NOT NULL DEFAULT 'transfer';
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS direction TEXT NOT NULL DEFAULT 'out';
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS is_internal INTEGER NOT NULL DEFAULT 0;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS linked_tx_id TEXT;

-- decisions: immutable audit snapshot of what the engine saw at decision time.
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS tx_snapshot_json TEXT;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS features_snapshot_json TEXT;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS fx_proof_json TEXT;

CREATE INDEX IF NOT EXISTS idx_tx_sender_ts ON transactions(tenant_id, sender_account_id, ts);
CREATE INDEX IF NOT EXISTS idx_tx_ref ON transactions(tenant_id, reference_amount);
