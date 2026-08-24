-- 006_pg_hardening — integrity guards & query indexes (Task 1 hardening).
-- NOTE: Row-Level Security (RLS) policies arrive in Task 3; tenant-scoped
-- tables below are RLS-ready (owner = aegis) but not yet policy-enforced.
-- DecisionTrace hash-chaining arrives in Task 4 (see comments on decisions/audit_log).

ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_tx_amount;
ALTER TABLE transactions ADD CONSTRAINT chk_tx_amount CHECK (amount >= 0);

CREATE INDEX IF NOT EXISTS idx_dec_idem ON decisions(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_tx_currency ON transactions(tenant_id, currency);
CREATE INDEX IF NOT EXISTS idx_watchlist_type ON watchlist(list_type);
CREATE INDEX IF NOT EXISTS idx_webhook_tenant ON webhooks_seen(tenant_id);

COMMENT ON TABLE decisions IS 'Immutable decision records — append-only; no UPDATE/DELETE outside explicit admin migration';
COMMENT ON TABLE audit_log IS 'Append-only audit trail — integrity hash-chain arrives with DecisionTrace (Task 4)';
COMMENT ON TABLE transactions IS 'Financial events — original amount/currency preserved; reference fields are FX-normalized for cross-currency analytics';
