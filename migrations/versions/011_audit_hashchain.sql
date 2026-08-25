-- 011_audit_hashchain — tamper-evident audit trail (hash chain) + decision trace enrichment.
-- Each audit entry chains to the previous via SHA-256(prev_hash || canonical payload).
-- Deleting/editing any historical row breaks verification from that point on.

ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS prev_hash TEXT;
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS entry_hash TEXT;
CREATE INDEX IF NOT EXISTS idx_audit_hash ON audit_log(entry_hash);

-- DecisionTrace completeness: rule + model + config versions captured at decision time
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS rule_set_version TEXT;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS model_version TEXT;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS config_version TEXT;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS request_id TEXT;
