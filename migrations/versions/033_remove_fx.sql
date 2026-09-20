-- 033: AEGIS no longer manages foreign exchange. Drop FX storage.
DROP TABLE IF EXISTS fx_rates CASCADE;
DROP TABLE IF EXISTS fx_reference_sets CASCADE;
ALTER TABLE transactions DROP COLUMN IF EXISTS reference_amount, DROP COLUMN IF EXISTS reference_currency, DROP COLUMN IF EXISTS fx_snapshot_id, DROP COLUMN IF EXISTS fx_status;
ALTER TABLE decisions DROP COLUMN IF EXISTS fx_proof_json;
