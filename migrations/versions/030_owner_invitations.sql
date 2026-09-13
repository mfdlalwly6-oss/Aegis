-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 030 — Institution-owner invitations + password-reset tokens
--
-- invitations: secure onboarding for institution owners. Stores ONLY the
-- SHA-256 hash of the invite token (never the raw token). Single-use,
-- expiring (default 72h), revocable.
--
-- password_reset_tokens: same security model for forgot-password flow.
-- Hashed, expiring, single-use. Responses never reveal whether an email
-- exists (generic 200).
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS invitations (
  invitation_id  TEXT PRIMARY KEY,
  tenant_id      TEXT NOT NULL,
  user_id        TEXT NOT NULL,
  email          TEXT NOT NULL,
  token_hash     TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'pending',   -- pending|accepted|revoked|expired
  invited_by     TEXT NOT NULL DEFAULT 'owner',
  expires_at     TEXT NOT NULL,
  accepted_at    TEXT,
  created_at     TEXT NOT NULL,
  CONSTRAINT chk_inv_status CHECK (status IN ('pending','accepted','revoked','expired'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_invitations_token_hash ON invitations (token_hash);
CREATE INDEX IF NOT EXISTS idx_invitations_tenant ON invitations (tenant_id);
CREATE INDEX IF NOT EXISTS idx_invitations_user ON invitations (user_id);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
  reset_id    TEXT PRIMARY KEY,
  tenant_id   TEXT NOT NULL,
  user_id     TEXT NOT NULL,
  email       TEXT NOT NULL,
  token_hash  TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'pending',      -- pending|used|expired
  expires_at  TEXT NOT NULL,
  used_at     TEXT,
  created_at  TEXT NOT NULL,
  CONSTRAINT chk_reset_status CHECK (status IN ('pending','used','expired'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_reset_token_hash ON password_reset_tokens (token_hash);
CREATE INDEX IF NOT EXISTS idx_reset_user ON password_reset_tokens (user_id);
