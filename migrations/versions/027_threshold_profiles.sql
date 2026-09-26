-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 027 — Decision-threshold profiles (platform default + per-tenant)
--
-- Mirrors the weight_profiles design (Migration 026) for decision thresholds:
-- a single platform default row (scope='default') plus optional per-tenant
-- overrides (scope='tenant'). An ACTIVE tenant override wins; otherwise the
-- default row is used live (inheritance, no value copying). Disabling or
-- deleting an override reverts the tenant to the default instantly.
--
-- Safety bounds + ordering (challenge < review < block) are enforced in code
-- (policy_engine) AND here via CHECK constraints as a second line of defense.
-- fx_missing_action can never be a silent allow.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS threshold_profiles (
  profile_id   TEXT PRIMARY KEY,
  scope        TEXT NOT NULL DEFAULT 'tenant',           -- 'default' | 'tenant'
  tenant_id    TEXT,                                     -- NULL for default row
  challenge    NUMERIC(5,4) NOT NULL DEFAULT 0.35,
  review       NUMERIC(5,4) NOT NULL DEFAULT 0.60,
  block        NUMERIC(5,4) NOT NULL DEFAULT 0.80,
  fx_missing_action TEXT NOT NULL DEFAULT 'review',      -- 'review' | 'block'
  active       INTEGER NOT NULL DEFAULT 1,
  created_by   TEXT NOT NULL DEFAULT 'owner',
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL,
  note         TEXT,
  CONSTRAINT uq_threshold_profiles_scope UNIQUE (scope, tenant_id),
  CONSTRAINT chk_th_challenge CHECK (challenge >= 0.20 AND challenge <= 0.50),
  CONSTRAINT chk_th_review    CHECK (review    >= 0.40 AND review    <= 0.75),
  CONSTRAINT chk_th_block     CHECK (block     >= 0.60 AND block     <= 0.95),
  CONSTRAINT chk_th_order     CHECK (review >= challenge AND block >= review),
  CONSTRAINT chk_th_fx        CHECK (fx_missing_action IN ('review','block'))
);

CREATE INDEX IF NOT EXISTS idx_threshold_profiles_tenant
  ON threshold_profiles (tenant_id);

-- Seed the single platform default row (idempotent).
INSERT INTO threshold_profiles
  (profile_id, scope, tenant_id, challenge, review, block, fx_missing_action, active, created_by, created_at, updated_at)
SELECT 'thp_default','default',NULL, 0.35, 0.60, 0.80, 'review', 1, 'system',
       to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.FF6"Z"'),
       to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.FF6"Z"')
WHERE NOT EXISTS (SELECT 1 FROM threshold_profiles WHERE scope='default');
