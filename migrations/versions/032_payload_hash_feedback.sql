-- Stage3 recovery: idempotency payload hash + post-transaction feedback labels
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS payload_hash TEXT;

CREATE TABLE IF NOT EXISTS feedback (
    id          TEXT PRIMARY KEY,
    tx_id       TEXT NOT NULL,
    tenant_id   TEXT NOT NULL,
    outcome     TEXT NOT NULL,
    source      TEXT NOT NULL,
    occurred_at TEXT,
    confidence  REAL,
    case_id     TEXT,
    notes       TEXT,
    created_at  TEXT NOT NULL,
    UNIQUE(tx_id, outcome, source)
);
CREATE INDEX IF NOT EXISTS idx_feedback_tx ON feedback(tx_id);
CREATE INDEX IF NOT EXISTS idx_feedback_tenant ON feedback(tenant_id);
