-- Decision confidence: explicit, interpretable, persisted, non-retroactive.
--
-- confidence = fraction of NOMINAL policy weight contributed by fully-healthy
-- components at decision time (degraded counts half, unavailable zero). It is
-- computed from component_health (status + weight_applied) captured at decision
-- time, so a failed/degraded engine NEVER makes the decision look more
-- confident without justification. Stored verbatim with the decision; never
-- recomputed on old rows (historical integrity).
--
-- aegis_app does NOT own `decisions` (owner = aegis), so this ALTER must run as
-- the table owner. The app's migration runner (pgdb) defers *_owner_alters.sql
-- to the owner instead of crashing startup. See docs/DEPLOY.md.
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS confidence REAL;

-- Index for confidence-based triage / reporting queries (owner scope).
CREATE INDEX IF NOT EXISTS idx_decisions_confidence ON decisions(tenant_id, confidence);
