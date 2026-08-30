-- Four-eyes (dual-approval) for high-severity alerts.
--
-- Four-eyes principle: a high/critical alert can never be marked resolved by a
-- single investigator. The first resolve request creates a pending approval
-- (requested_by); a DIFFERENT investigator approves (approved_by != requested_by)
-- before the alert transitions to a resolved terminal state. Enforcement lives
-- in the backend (investigator.py), not the UI.
--
-- NOTE: the investigators.last_logout_at column moved to 019_owner_alters.sql.
-- aegis_app (the app role) cannot ALTER investigators — it does not own that
-- table — so this migration stays aegis_app-safe (it only CREATEs its own
-- table, which aegis_app may own via the 010 schema-CREATE grant).
CREATE TABLE IF NOT EXISTS alert_approvals (
    approval_id  TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL,
    alert_id     TEXT NOT NULL,
    resolution   TEXT NOT NULL,               -- intended terminal resolution
    note         TEXT NOT NULL DEFAULT '',
    requested_by TEXT NOT NULL,               -- investigator email (requester)
    approved_by  TEXT,                        -- different investigator email
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    created_at   TEXT NOT NULL,
    decided_at   TEXT
);
-- one open request per alert
CREATE UNIQUE INDEX IF NOT EXISTS uq_alert_approvals_open
    ON alert_approvals(alert_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_alert_approvals_tenant ON alert_approvals(tenant_id, status);

ALTER TABLE alert_approvals ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS alert_approvals_isolation ON alert_approvals;
CREATE POLICY alert_approvals_isolation ON alert_approvals
  USING (current_setting('app.tenant_id', true) = 'platform'
         OR tenant_id = current_setting('app.tenant_id', true))
  WITH CHECK (current_setting('app.tenant_id', true) = 'platform'
         OR tenant_id = current_setting('app.tenant_id', true));
