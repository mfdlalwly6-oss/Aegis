-- 025_currency_lifecycle.sql
-- §14/§21/§22: full currency registry lifecycle. The currencies table already
-- exists (005_money_fx) with code/name/minor_unit/round_unit/active/created_at.
-- This migration is purely additive and idempotent — no data is dropped and
-- historical transactions/decisions are never touched.

-- Display symbol (e.g. $, ﷼) — NULL when unknown (never guessed).
ALTER TABLE currencies ADD COLUMN IF NOT EXISTS symbol TEXT;

-- Decimal places for formatting (0 for YER/JPY, 2 for USD/SAR). Distinct from
-- minor_unit (the NAME of the smallest unit). NULL-safe default keeps old rows valid.
ALTER TABLE currencies ADD COLUMN IF NOT EXISTS decimal_places INTEGER;

-- Row update timestamp for audit/display.
ALTER TABLE currencies ADD COLUMN IF NOT EXISTS updated_at TEXT;

-- Backfill decimal_places from minor_unit where it was being (mis)used as the
-- decimal count, only when still NULL.
UPDATE currencies SET decimal_places = minor_unit WHERE decimal_places IS NULL;

-- updated_at falls back to created_at for existing rows.
UPDATE currencies SET updated_at = created_at WHERE updated_at IS NULL;
